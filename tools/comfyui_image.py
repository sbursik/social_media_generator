"""Generate an image via ComfyUI using the Gemini Nano Banana 2 workflow.

Usage:
    uv run tools/comfyui_image.py --prompt "..." --output out.png
    uv run tools/comfyui_image.py --prompt "..." --aspect 9:16 --output out.png
"""

import argparse
import copy
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from comfyui_client import WORKFLOWS_DIR, load_workflow, run_workflow

WORKFLOW_PATH = WORKFLOWS_DIR / "api_google_nano_banana2_text_to_image.json"

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


def main():
    parser = argparse.ArgumentParser(description="Generate image via ComfyUI Gemini workflow")
    parser.add_argument("--prompt", required=True, help="Image description")
    parser.add_argument("--aspect", default="9:16", choices=list(ASPECT_MAP.keys()), help="Aspect ratio (default: 9:16)")
    parser.add_argument("--resolution", default="1K", choices=["1K", "2K"], help="Output resolution")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument("--output", required=True, help="Output image path (e.g. scene1.png)")
    args = parser.parse_args()

    print(f"Generating image: {args.prompt[:60]}...")
    workflow = build_workflow(args.prompt, args.aspect, args.resolution, args.seed)
    output_files = run_workflow(workflow, timeout=120)

    if not output_files:
        print("ERROR: No output files returned from ComfyUI", file=sys.stderr)
        sys.exit(1)

    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output_files[0], dest)
    print(f"Saved: {dest}")


if __name__ == "__main__":
    main()
