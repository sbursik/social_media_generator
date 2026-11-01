"""Generate an image — with MiniMax H3 on the local GPU by default, or via a paid cloud API.

Backends (--backend, or IMAGE_BACKEND in .env):
    local    H3 open weights in ComfyUI, no API key or credits (default)
    comfyui  Gemini Nano Banana 2 cloud API node in ComfyUI, billed to Comfy.org credits
    direct   Gemini API with no ComfyUI, see tools/direct_api.py (default if BACKEND=direct)

The local backend is a pseudo-image workflow: H3 generates a very short clip and one frame is kept.

Usage:
    uv run tools/comfyui_image.py --prompt "..." --output out.png
    uv run tools/comfyui_image.py --prompt "..." --aspect 9:16 --output out.png
"""

import argparse
import copy
import os
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from comfyui_client import WORKFLOWS_DIR, h3_size, load_workflow, run_workflow

WORKFLOW_PATH = WORKFLOWS_DIR / "api_google_nano_banana2_text_to_image.json"
LOCAL_WORKFLOW_PATH = WORKFLOWS_DIR / "local_minimax_h3_image.json"
LOCAL_MEGAPIXELS = 1.0

# Aspect ratio → model.aspect_ratio value used by GeminiNanoBanana2V2
ASPECT_MAP = {
    "1:1":  "1:1",
    "9:16": "9:16",
    "16:9": "16:9",
    "4:5":  "4:5",
    "3:4":  "3:4",
}


def build_workflow(prompt: str, aspect: str = "9:16", resolution: str = "1K", seed: int | None = None) -> dict:
    workflow = load_workflow(WORKFLOW_PATH)
    wf = copy.deepcopy(workflow)

    aspect_val = ASPECT_MAP.get(aspect, aspect)
    seed_val = seed if seed is not None else random.randint(0, 2**32 - 1)

    # Node 24 is the GeminiNanoBanana2V2 node
    wf["24"]["inputs"]["prompt"] = prompt
    wf["24"]["inputs"]["model.aspect_ratio"] = aspect_val
    wf["24"]["inputs"]["model.resolution"] = resolution
    wf["24"]["inputs"]["seed"] = seed_val

    return wf


def build_local_workflow(prompt: str, aspect: str = "9:16", seed: int | None = None) -> dict:
    wf = load_workflow(LOCAL_WORKFLOW_PATH)
    w, h = aspect.split(":")
    width, height, crop_w, crop_h = h3_size(int(w) / int(h), LOCAL_MEGAPIXELS)
    print(f"  Rendering {width}x{height} locally (cropped to {crop_w}x{crop_h})")

    wf["131"]["inputs"].update(prompt=prompt, width=width, height=height)
    wf["93"]["inputs"].update(width=crop_w, height=crop_h, x=(width - crop_w) // 2, y=(height - crop_h) // 2)
    wf["129"]["inputs"]["noise_seed"] = seed if seed is not None else random.randint(0, 2**32 - 1)
    return wf


def main():
    default_backend = os.environ.get("IMAGE_BACKEND") or (
        "direct" if os.environ.get("BACKEND") == "direct" else "local")
    parser = argparse.ArgumentParser(description="Generate an image with MiniMax H3 (local GPU) or Gemini (cloud)")
    parser.add_argument("--prompt", required=True, help="Image description")
    parser.add_argument("--aspect", default="9:16", choices=list(ASPECT_MAP.keys()), help="Aspect ratio (default: 9:16)")
    parser.add_argument("--resolution", default="1K", choices=["1K", "2K"], help="Output resolution (2K is cloud only)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument("--output", required=True, help="Output image path (e.g. scene1.png)")
    parser.add_argument("--backend", choices=["local", "comfyui", "direct"], default=default_backend,
                        help="local GPU (default), comfyui cloud node, or direct Gemini API (env: IMAGE_BACKEND)")
    args = parser.parse_args()

    if args.backend == "local" and args.resolution != "1K":
        parser.error("--resolution 2K needs a cloud backend (--backend comfyui or direct)")

    print(f"Generating image: {args.prompt[:60]}...")
    if args.backend == "direct":
        from direct_api import gemini_image
        seed = args.seed if args.seed is not None else random.randint(0, 2**31 - 1)
        gemini_image(args.prompt, ASPECT_MAP[args.aspect], args.resolution, seed, Path(args.output))
        print(f"Saved: {args.output}")
        return

    if args.backend == "local":
        workflow = build_local_workflow(args.prompt, args.aspect, args.seed)
        # Allow for model loading and for ComfyUI working through other queued jobs
        timeout = 900
    else:
        workflow = build_workflow(args.prompt, args.aspect, args.resolution, args.seed)
        timeout = 120
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
