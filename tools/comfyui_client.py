"""Shared ComfyUI API client — submit workflows, poll for results."""

import copy
import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path

COMFYUI_URL = "http://127.0.0.1:8188"
COMFYUI_OUTPUT = Path.home() / "ComfyUI" / "output"
COMFYUI_INPUT = Path.home() / "ComfyUI" / "input"


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
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["prompt_id"]


def poll_history(prompt_id: str, timeout: int = 300, interval: int = 3) -> dict:
    """Poll /history until the job completes or timeout is reached."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"{COMFYUI_URL}/history/{prompt_id}"
            ) as resp:
                data = json.loads(resp.read())
                if prompt_id in data:
                    return data[prompt_id]
        except urllib.error.URLError:
            pass
        time.sleep(interval)
    raise TimeoutError(f"ComfyUI job {prompt_id} did not complete within {timeout}s")


def get_output_files(history: dict) -> list[Path]:
    """Extract output file paths from a completed history entry."""
    files = []
    outputs = history.get("outputs", {})
    for node_output in outputs.values():
        for key in ("images", "videos", "gifs"):
            for item in node_output.get(key, []):
                subfolder = item.get("subfolder", "")
                filename = item["filename"]
                base = COMFYUI_OUTPUT / subfolder if subfolder else COMFYUI_OUTPUT
                files.append(base / filename)
    return files


def copy_image_to_input(src: Path) -> str:
    """Copy an image into ComfyUI's input folder and return the filename."""
    COMFYUI_INPUT.mkdir(parents=True, exist_ok=True)
    dest = COMFYUI_INPUT / src.name
    dest.write_bytes(src.read_bytes())
    return src.name


def run_workflow(workflow: dict, timeout: int = 300) -> list[Path]:
    """Submit a workflow, wait for completion, return output file paths."""
    prompt_id = queue_prompt(workflow)
    print(f"  Queued job {prompt_id}")
    history = poll_history(prompt_id, timeout=timeout)
    return get_output_files(history)
