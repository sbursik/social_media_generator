"""Animate an image via ComfyUI using the MiniMax H3 Max workflow.

Usage:
    uv run tools/comfyui_video.py --image scene1.png --prompt "..." --output scene1.mp4
    uv run tools/comfyui_video.py --image scene1.png --prompt "..." --duration 5 --upscale --output scene1.mp4
"""

import argparse
import copy
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from comfyui_client import load_workflow, run_workflow, copy_image_to_input

WORKFLOW_PATH = Path(__file__).parent.parent.parent / "ComfyUI" / "api_workflows" / "api_minimax_h3_max_r2v.json"


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
    parser = argparse.ArgumentParser(description="Animate an image via ComfyUI MiniMax H3 Max workflow")
    parser.add_argument("--image", required=True, help="Input image path")
    parser.add_argument("--prompt", required=True, help="Motion description prompt")
    parser.add_argument("--duration", type=int, default=5, choices=[5, 10], help="Video duration in seconds")
    parser.add_argument("--ratio", default="9:16", choices=["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16", "21:9"], help="Output aspect ratio (default: 9:16)")
    parser.add_argument("--resolution", default="768P", choices=["768P", "1080P"], help="Output resolution")
    parser.add_argument("--upscale", action="store_true", help="Upscale to 2K after generation")
    parser.add_argument("--enhance", action="store_true", help="Use MiniMax prompt enhancer")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--output", required=True, help="Output video path (e.g. scene1.mp4)")
    args = parser.parse_args()

    image_path = Path(args.image).resolve()
    if not image_path.exists():
        print(f"ERROR: Image not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Animating {image_path.name}: {args.prompt[:60]}...")
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
    output_files = run_workflow(workflow, timeout=600)

    if not output_files:
        print("ERROR: No output files returned from ComfyUI", file=sys.stderr)
        sys.exit(1)

    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output_files[0], dest)
    print(f"Saved: {dest}")


if __name__ == "__main__":
    main()
