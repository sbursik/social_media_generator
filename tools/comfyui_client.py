"""Shared ComfyUI API client — submit workflows, poll for results.

Talks to ComfyUI purely over HTTP, so it works with any install location
(portable, desktop app, or a ComfyUI on another machine).

Config (environment or a .env file in the repo root):
    COMFYUI_URL    ComfyUI server (default: http://127.0.0.1:8188)
    COMFY_API_KEY  Comfy.org API key, needed for API nodes (Gemini, MiniMax)
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / "workflows"

load_dotenv(REPO_ROOT / ".env")
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")


def load_workflow(path: str | Path) -> dict:
    with open(path) as f:
        return json.load(f)


def queue_prompt(workflow: dict) -> str:
    """Submit a workflow to ComfyUI and return the prompt_id."""
    body = {"prompt": workflow}
    # API nodes (Gemini, MiniMax) need a Comfy.org key when submitted outside the web UI
    api_key = os.environ.get("COMFY_API_KEY")
    if api_key:
        body["extra_data"] = {"api_key_comfy_org": api_key}
    try:
        resp = requests.post(f"{COMFYUI_URL}/prompt", json=body, timeout=30)
    except requests.ConnectionError:
        sys.exit(f"ERROR: cannot reach ComfyUI at {COMFYUI_URL} — is it running?")
    if resp.status_code != 200:
        sys.exit(f"ERROR: ComfyUI rejected the workflow ({resp.status_code}): {resp.text[:1000]}")
    return resp.json()["prompt_id"]


def poll_history(prompt_id: str, timeout: int = 300, interval: int = 3) -> dict:
    """Poll /history until the job completes or timeout is reached."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=30).json()
            if prompt_id in data:
                return data[prompt_id]
        except requests.RequestException:
            pass
        time.sleep(interval)
    raise TimeoutError(f"ComfyUI job {prompt_id} did not complete within {timeout}s")


def report_errors(history: dict):
    """Print ComfyUI's execution error, if the job failed."""
    for kind, msg in history.get("status", {}).get("messages", []):
        if kind == "execution_error":
            print(f"ComfyUI error in {msg.get('node_type')}: {msg.get('exception_message', '').strip()}",
                  file=sys.stderr)
            if "login" in msg.get("exception_message", "").lower():
                print("  → set COMFY_API_KEY (see README)", file=sys.stderr)


def get_output_files(history: dict) -> list[Path]:
    """Download a completed job's outputs to a temp dir and return their paths."""
    report_errors(history)
    out_dir = Path(tempfile.mkdtemp(prefix="comfyui_"))
    files = []
    for node_output in history.get("outputs", {}).values():
        for key in ("images", "videos", "gifs"):
            for item in node_output.get(key, []):
                params = {"filename": item["filename"], "subfolder": item.get("subfolder", ""),
                          "type": item.get("type", "output")}
                resp = requests.get(f"{COMFYUI_URL}/view", params=params, timeout=300)
                resp.raise_for_status()
                dest = out_dir / item["filename"]
                dest.write_bytes(resp.content)
                files.append(dest)
    return files


def copy_image_to_input(src: Path) -> str:
    """Upload an image to ComfyUI's input folder and return its name there."""
    with open(src, "rb") as f:
        resp = requests.post(f"{COMFYUI_URL}/upload/image",
                             files={"image": (src.name, f, "image/png")},
                             data={"overwrite": "true"}, timeout=120)
    resp.raise_for_status()
    info = resp.json()
    return f"{info['subfolder']}/{info['name']}" if info.get("subfolder") else info["name"]


def run_workflow(workflow: dict, timeout: int = 300) -> list[Path]:
    """Submit a workflow, wait for completion, return output file paths."""
    prompt_id = queue_prompt(workflow)
    print(f"  Queued job {prompt_id}")
    history = poll_history(prompt_id, timeout=timeout)
    return get_output_files(history)
