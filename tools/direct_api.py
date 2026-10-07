"""Direct API backend — Gemini and MiniMax called straight, no ComfyUI needed.

Used by comfyui_image.py / comfyui_video.py when BACKEND=direct (or --backend direct),
e.g. on a Windows machine without ComfyUI installed.

Config (environment or a .env file in the repo root):
    GEMINI_API_KEY   Google AI Studio key (https://aistudio.google.com/apikey)
    MINIMAX_API_KEY  MiniMax platform key (https://platform.minimax.io)
"""

import base64
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview")  # Nano Banana 2

MINIMAX_URL = "https://api.minimax.io/v2"
MINIMAX_VIDEO_MODEL = "MiniMax-H3-Max"


def require_key(name: str) -> str:
    key = os.environ.get(name)
    if not key:
        sys.exit(f"ERROR: {name} is not set — add it to .env (see .env.example)")
    return key


def gemini_image(prompt: str, aspect: str, resolution: str, seed: int, output: Path):
    """Text → image with Gemini Nano Banana 2."""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": aspect, "imageSize": resolution},
            "seed": seed % 2**31,
        },
    }
    resp = requests.post(GEMINI_URL.format(model=GEMINI_IMAGE_MODEL), json=body, timeout=180,
                         headers={"x-goog-api-key": require_key("GEMINI_API_KEY")})
    if resp.status_code != 200:
        sys.exit(f"ERROR: Gemini rejected the request ({resp.status_code}): {resp.text[:1000]}")

    for cand in resp.json().get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            if "inlineData" in part:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(base64.b64decode(part["inlineData"]["data"]))
                return
        if cand.get("finishReason") not in (None, "STOP"):
            sys.exit(f"ERROR: Gemini returned no image (finishReason={cand['finishReason']})")
    sys.exit(f"ERROR: Gemini returned no image: {resp.text[:1000]}")


def _minimax(method: str, path: str, **kwargs) -> dict:
    headers = {"Authorization": f"Bearer {require_key('MINIMAX_API_KEY')}"}
    resp = requests.request(method, f"{MINIMAX_URL}/{path}", headers=headers, timeout=120, **kwargs)
    if resp.status_code != 200:
        sys.exit(f"ERROR: MiniMax rejected the request ({resp.status_code}): {resp.text[:1000]}")
    return resp.json()


def _wait(task_id: str, timeout: int) -> dict:
    """Poll a MiniMax task until it finishes; return the task."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = _minimax("GET", f"query/video_generation/{task_id}")["task"]
        if task["status"] == "succeeded":
            return task
        if task["status"] in ("failed", "cancelled"):
            err = task.get("error", {})
            sys.exit(f"ERROR: MiniMax task {task['status']}: {err.get('message', err)}")
        time.sleep(10)
    raise TimeoutError(f"MiniMax task {task_id} did not complete within {timeout}s")


def minimax_video(image: Path, prompt: str, duration: int, resolution: str, ratio: str,
                  upscale_2k: bool, enhance_prompt: bool, output: Path, timeout: int = 900):
    """Image → video with MiniMax H3 Max, mirroring workflows/api_minimax_h3_max_r2v.json."""
    image_uri = f"data:image/png;base64,{base64.b64encode(image.read_bytes()).decode()}"
    ref = {"type": "image_url", "image_url": {"url": image_uri}, "role": "reference_image"}

    if enhance_prompt:
        # H3 Context IR rewrites the prompt with the reference image in view
        task_id = _minimax("POST", "h3_context_ir", json={
            "model": "MiniMax-H3", "content": [{"type": "text", "text": prompt}, ref],
            "duration": duration, "ratio": ratio,
        })["task_id"]
        prompt = _wait(task_id, 300)["content"]["prompt"]
        print(f"  Enhanced prompt: {prompt[:100]}...")

    task_id = _minimax("POST", "video_generation", json={
        "model": MINIMAX_VIDEO_MODEL,
        "content": [{"type": "text", "text": prompt}, ref],
        "resolution": resolution, "duration": duration, "ratio": ratio,
        "extra": {"prompt_expansion_mode": "balanced"},
    })["task_id"]
    print(f"  Queued MiniMax task {task_id}")
    task = _wait(task_id, timeout)

    if upscale_2k:
        task_id = _minimax("POST", "video_regeneration", json={
            "model": "MiniMax-H3", "source_task_id": task_id, "resolution": "2K", "aigc_watermark": False,
        })["task_id"]
        print(f"  Queued 2K upscale {task_id}")
        task = _wait(task_id, timeout)

    resp = requests.get(task["content"]["url"], timeout=300)
    resp.raise_for_status()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(resp.content)
