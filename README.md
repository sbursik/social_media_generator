# Social Media Video Generator

Turn a concept into a finished short-form vertical video (TikTok, Reels, Shorts): scripted scenes, AI-generated images animated into clips, a narrated voiceover, background music, and word-highlighted captions — all synced to the narration.

| Step | Tool | Backend |
|---|---|---|
| Text → image | `tools/comfyui_image.py` | Gemini Nano Banana 2 (ComfyUI API node) |
| Image → video | `tools/comfyui_video.py` | MiniMax H3 Max (ComfyUI API node) |
| Voiceover | `tools/voiceover.py` | Kokoro ONNX (local, CPU) |
| Scene sync | `tools/sync_scenes.py` | faster-whisper + FFmpeg |
| Assembly + music | `tools/assemble.py` | FFmpeg |
| Captions | `tools/captions.py` | faster-whisper + libass |

## Prerequisites

- **Python 3.10+** and [**uv**](https://docs.astral.sh/uv/)
- **FFmpeg** built with libass (standard on Ubuntu/Debian/Homebrew builds) — check with `ffmpeg -filters | grep " ass "`
- **ComfyUI** (tested with v0.38.0) running locally or on your network. The Gemini and MiniMax nodes ship with ComfyUI as built-in API nodes — no custom nodes needed.
- **Comfy.org account with credits** and an API key from [platform.comfy.org](https://platform.comfy.org). Image and video generation are paid per call.

## Setup

```bash
git clone https://github.com/sbursik/social_media_generator.git
cd social_media_generator
uv sync

# API key + ComfyUI address
cp .env.example .env
# edit .env and set COMFY_API_KEY=...

# Kokoro TTS model files (~340 MB, kept out of git)
uv run python -c "
from huggingface_hub import hf_hub_download
hf_hub_download('fastrtc/kokoro-onnx', 'kokoro-v1.0.onnx', local_dir='.')
hf_hub_download('fastrtc/kokoro-onnx', 'voices-v1.0.bin', local_dir='.')
"
```

The first captions/sync run downloads the faster-whisper `small.en` model (~500 MB) automatically.

## Usage

### With Claude Code

Open Claude Code in the repo and ask for a video — e.g. *"make a 45 second TikTok about the dangers of AI"*. The bundled `social-video` skill (`.claude/skills/`) runs the full pipeline: script → images → clips → voiceover → sync → music → captions.

### Manually

See [`CLAUDE.md`](CLAUDE.md) for every command and option. In short:

```bash
uv run tools/comfyui_image.py --prompt "..." --aspect 9:16 --output projects/demo/scene1.png
uv run tools/comfyui_video.py --image projects/demo/scene1.png --prompt "slow push-in..." --output projects/demo/scene1.mp4
uv run tools/voiceover.py --file projects/demo/narration.txt --voice am_michael --output projects/demo/voiceover.wav
ffmpeg -i projects/demo/voiceover.wav -af "adelay=1000:all=1,apad=whole_dur=46.5" projects/demo/voiceover_padded.wav
uv run tools/sync_scenes.py --project projects/demo --audio projects/demo/voiceover_padded.wav --total 46.5
uv run tools/assemble.py --clips projects/demo/synced/scene*.mp4 --audio projects/demo/voiceover_padded.wav \
  --music audio_samples/background_music_00.wav --music-volume 0.2 --platform tiktok --output projects/demo/final.mp4
uv run tools/captions.py --video projects/demo/final.mp4 --audio projects/demo/voiceover_padded.wav \
  --file projects/demo/narration.txt --output projects/demo/final_captioned.mp4
```

`sync_scenes.py` reads per-scene narration from `projects/<slug>/SCRIPT.md` — see `CLAUDE.md` for the format.

## Repo layout

```
tools/            CLI tools (all run from the repo root with `uv run`)
workflows/        ComfyUI API-format workflows used by the image/video tools
audio_samples/    Background music tracks
fonts/            Montserrat ExtraBold for captions (SIL OFL, see fonts/OFL.txt)
.claude/skills/   Claude Code skill for the end-to-end workflow
projects/         Your generated videos (git-ignored)
```

## Configuration

Set in `.env` (git-ignored) or the environment:

| Variable | Default | Purpose |
|---|---|---|
| `COMFY_API_KEY` | — | Comfy.org key for the Gemini/MiniMax API nodes (required) |
| `COMFYUI_URL` | `http://127.0.0.1:8188` | ComfyUI server address |

## Troubleshooting

- **`Please login first to use this node`** — `COMFY_API_KEY` isn't set in `.env`.
- **`Error processing file '/home/runner/.../espeak-ng-data/phontab'`** (voiceover) — espeak-ng can't handle long install paths (>~160 chars). Clone to a shorter path, or put the venv somewhere short: `UV_PROJECT_ENVIRONMENT=~/.venvs/smg uv sync`.
- **Captions missing or in the wrong font** — FFmpeg needs libass; fonts are loaded from `fonts/`.
