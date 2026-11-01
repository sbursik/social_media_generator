"""Animate an image with MiniMax H3 — on the local GPU by default, or via a paid cloud API.

Backends (--backend, or VIDEO_BACKEND in .env):
    local    H3 open weights in ComfyUI, no API key or credits (default)
    comfyui  H3 Max cloud API node in ComfyUI, billed to Comfy.org credits
    direct   MiniMax API with no ComfyUI, see tools/direct_api.py (default if BACKEND=direct)

Usage:
    uv run tools/comfyui_video.py --image scene1.png --prompt "..." --output scene1.mp4
    uv run tools/comfyui_video.py --image scene1.png --prompt "..." --duration 5 --upscale --output scene1.mp4
"""

import argparse
import copy
import os
import random
import shutil
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from comfyui_client import WORKFLOWS_DIR, h3_size, load_workflow, run_workflow, copy_image_to_input

WORKFLOW_PATH = WORKFLOWS_DIR / "api_minimax_h3_max_r2v.json"
LOCAL_WORKFLOW_PATH = WORKFLOWS_DIR / "local_minimax_h3_i2v_turbo.json"

LOCAL_MEGAPIXELS = 0.9


def local_size(ratio: str, image_path: Path) -> tuple[int, int, int, int]:
    """Pick H3 render and crop sizes for an aspect ratio ("adaptive" follows the image)."""
    if ratio == "adaptive":
        with Image.open(image_path) as img:
            aspect = img.width / img.height
    else:
        w, h = ratio.split(":")
        aspect = int(w) / int(h)
    return h3_size(aspect, LOCAL_MEGAPIXELS)


def local_frames(duration: int) -> int:
    """Convert seconds to a frame count on H3's 17k+5 grid at 24 fps, snapping up."""
    frames = max(5, duration * 24)
    return frames + (5 - frames % 17) % 17


def build_local_workflow(
    image_path: Path,
    prompt: str,
    duration: int = 5,
    ratio: str = "9:16",
    seed: int | None = None,
) -> dict:
    wf = load_workflow(LOCAL_WORKFLOW_PATH)
    width, height, crop_w, crop_h = local_size(ratio, image_path)
    print(f"  Rendering {width}x{height} locally (cropped to {crop_w}x{crop_h}), {local_frames(duration)} frames")

    wf["114"]["inputs"]["image"] = copy_image_to_input(image_path)
    wf["115"]["inputs"].update(width=width, height=height)
    wf["104"]["inputs"].update(prompt=prompt, width=width, height=height, length=local_frames(duration))
    wf["93"]["inputs"].update(width=crop_w, height=crop_h, x=(width - crop_w) // 2, y=(height - crop_h) // 2)
    wf["15"]["inputs"]["noise_seed"] = seed if seed is not None else random.randint(0, 2**32 - 1)
    return wf


def build_workflow(
    image_path: Path,
    prompt: str,
    duration: int = 5,
    resolution: str = "768P",
    ratio: str = "9:16",
    upscale_2k: bool = False,
    enhance_prompt: bool = False,
    seed: int | None = None,
) -> dict:
    workflow = load_workflow(WORKFLOW_PATH)
    wf = copy.deepcopy(workflow)

    # Copy image into ComfyUI input folder
    image_filename = copy_image_to_input(image_path)

    seed_val = seed if seed is not None else random.randint(0, 2**32 - 1)

    # Node 6: source image
    wf["6"]["inputs"]["image"] = image_filename

    # Node 4: MiniMax H3 Max Reference to Video
    wf["4"]["inputs"]["model.duration"] = duration
    wf["4"]["inputs"]["model.resolution"] = resolution
    wf["4"]["inputs"]["model.ratio"] = ratio
    wf["7"]["inputs"]["model.ratio"] = ratio
    wf["4"]["inputs"]["seed"] = seed_val

    # Node 14: prompt text
    wf["14"]["inputs"]["value"] = prompt

    # Node 18: boolean — use prompt enhancer (MiniMax H3 Context IR)
    wf["18"]["inputs"]["value"] = enhance_prompt

    # Node 19: boolean — upscale to 2K after generation
    wf["19"]["inputs"]["value"] = upscale_2k

    return wf


def main():
    default_backend = os.environ.get("VIDEO_BACKEND") or (
        "direct" if os.environ.get("BACKEND") == "direct" else "local")
    parser = argparse.ArgumentParser(description="Animate an image with MiniMax H3 (local GPU or cloud)")
    parser.add_argument("--image", required=True, help="Input image path")
    parser.add_argument("--prompt", required=True, help="Motion description prompt")
    parser.add_argument("--duration", type=int, default=5, choices=[5, 10], help="Video duration in seconds")
    parser.add_argument("--ratio", default="9:16", choices=["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16", "21:9"], help="Output aspect ratio (default: 9:16)")
    parser.add_argument("--resolution", default="768P", choices=["768P", "1080P"], help="Output resolution (cloud only)")
    parser.add_argument("--upscale", action="store_true", help="Upscale to 2K after generation (cloud only)")
    parser.add_argument("--enhance", action="store_true", help="Use MiniMax prompt enhancer (cloud only)")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--output", required=True, help="Output video path (e.g. scene1.mp4)")
    parser.add_argument("--backend", choices=["local", "comfyui", "direct"], default=default_backend,
                        help="local GPU (default), comfyui cloud node, or direct MiniMax API (env: VIDEO_BACKEND)")
    args = parser.parse_args()

    if args.backend == "local" and (args.upscale or args.enhance or args.resolution != "768P"):
        parser.error("--upscale, --enhance and --resolution 1080P need a cloud backend (--backend comfyui or direct)")

    image_path = Path(args.image).resolve()
    if not image_path.exists():
        print(f"ERROR: Image not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Animating {image_path.name}: {args.prompt[:60]}...")
    if args.backend == "direct":
        if args.resolution != "768P":
            parser.error("MiniMax H3 Max via the direct API supports 768P only (use --upscale for 2K)")
        from direct_api import minimax_video
        minimax_video(image_path, args.prompt, args.duration, args.resolution, args.ratio,
                      args.upscale, args.enhance, Path(args.output))
        print(f"Saved: {args.output}")
        return

    if args.backend == "local":
        workflow = build_local_workflow(image_path, args.prompt, args.duration, args.ratio, args.seed)
        # Allow for model loading and for ComfyUI working through other queued jobs
        timeout = 1800
    else:
        workflow = build_workflow(
            image_path,
            args.prompt,
            duration=args.duration,
            resolution=args.resolution,
            ratio=args.ratio,
            upscale_2k=args.upscale,
            enhance_prompt=args.enhance,
            seed=args.seed,
        )
        # MiniMax generation can take a while — allow 10 minutes
        timeout = 600
    output_files = run_workflow(workflow, timeout=timeout)

    if not output_files:
        print("ERROR: No output files returned from ComfyUI", file=sys.stderr)
        sys.exit(1)

    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output_files[0], dest)
    print(f"Saved: {dest}")


if __name__ == "__main__":
    main()
