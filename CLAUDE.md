# Social Media Video Generator

Local AI video production using ComfyUI (or the Gemini/MiniMax APIs directly — no ComfyUI needed, works on Windows). Creates short-form social media videos (TikTok, Reels, Shorts) from a concept.

## Stack

| Task | Tool | Backend |
|---|---|---|
| Text → Image | `tools/comfyui_image.py` | Gemini Nano Banana 2 via ComfyUI or direct API |
| Image → Video | `tools/comfyui_video.py` | MiniMax H3 Max via ComfyUI or direct API |
| Voiceover | `tools/voiceover.py` | Kokoro ONNX (local CPU) |
| Assembly | `tools/assemble.py` | FFmpeg |
| Scene sync | `tools/sync_scenes.py` | faster-whisper + FFmpeg |
| Captions | `tools/captions.py` | faster-whisper + libass (Montserrat ExtraBold in `fonts/`) |

## Requirements

- One image/video backend, chosen by `BACKEND` in `.env`:
  - `comfyui` (default): ComfyUI running at `http://127.0.0.1:8188` (or set `COMFYUI_URL`) plus a Comfy.org API key with credits as `COMFY_API_KEY`
  - `direct`: no ComfyUI; `GEMINI_API_KEY` (Google AI Studio) and `MINIMAX_API_KEY` (MiniMax platform), billed by those accounts. Video is 768P only (`--upscale` for 2K). Override per run with `--backend`
- `uv sync` run from the repo root to install Python deps
- Kokoro model files in the repo root (see Setup below)
- FFmpeg installed (already present on Linux; on Windows: `winget install ffmpeg`)

## Setup (first time only)

```bash
uv sync
cp .env.example .env   # then fill in COMFY_API_KEY

# Download Kokoro ONNX model files
uv run python -c "
from huggingface_hub import hf_hub_download
hf_hub_download('fastrtc/kokoro-onnx', 'kokoro-v1.0.onnx', local_dir='.')
hf_hub_download('fastrtc/kokoro-onnx', 'voices-v1.0.bin', local_dir='.')
"
```

### Windows

Same steps in PowerShell, after installing uv (`winget install astral-sh.uv`) and FFmpeg (`winget install ffmpeg`, then open a new terminal). Use `copy .env.example .env` and set `BACKEND=direct`. The multi-line commands below use bash `\` line breaks — in PowerShell, put them on one line or end lines with a backtick (`` ` ``) instead.

## Tool Usage

All tools run from the repo root with `uv run`:

```bash
# Generate a scene image (9:16 for vertical video)
uv run tools/comfyui_image.py \
  --prompt "Cinematic shot of a sunset over mountains, golden hour" \
  --aspect 9:16 \
  --output projects/my-video/scene1.png

# Animate the image into a 5-second video clip
uv run tools/comfyui_video.py \
  --image projects/my-video/scene1.png \
  --prompt "Camera slowly pans right, clouds drift, light god rays" \
  --duration 5 \
  --output projects/my-video/scene1.mp4

# Generate voiceover from text
uv run tools/voiceover.py \
  --text "Welcome to the most breathtaking view on earth." \
  --voice af_heart \
  --output projects/my-video/voiceover.wav

# Assemble final video
uv run tools/assemble.py \
  --clips projects/my-video/scene1.mp4 projects/my-video/scene2.mp4 \
  --audio projects/my-video/voiceover.wav \
  --music audio_samples/background_music_00.wav \
  --music-volume 0.2 \
  --platform tiktok \
  --output projects/my-video/final.mp4

# Retime clips so each scene starts on its narration line → projects/my-video/synced/
uv run tools/sync_scenes.py \
  --project projects/my-video \
  --audio projects/my-video/voiceover_padded.wav \
  --total 46.5
# then pass synced/sceneN.mp4 to assemble.py instead of sceneN.mp4

# Burn word-highlighted captions (script text used for exact wording)
uv run tools/captions.py \
  --video projects/my-video/final.mp4 \
  --audio projects/my-video/voiceover_padded.wav \
  --file projects/my-video/narration.txt \
  --title "Ketchup Was Fish Sauce" \
  --output projects/my-video/final_captioned.mp4
```

## Workflow for `/video`

1. Ask the user: concept, platform (tiktok/reels/shorts), approximate duration
2. Write a scene-by-scene script to `projects/<slug>/SCRIPT.md`
3. For each scene: generate image → animate to video clip
4. Generate voiceover from the full narration script (pad 1s of silence at the start so the first word isn't clipped)
5. Pick a background music track from `audio_samples/` (ask the user if unsure; can render one version per track to compare)
6. Retime clips with `tools/sync_scenes.py` so visuals match narration, then assemble `synced/` clips into final.mp4 with `--music`
7. Burn captions with `tools/captions.py --title "<short title>"` → final_captioned.mp4 (the title shows on the opening frames and the cover)
8. Write `POST.txt` with captions, Shorts title/description, hashtags, and posting checklist (incl. AI-content label)
9. Report the output path

## Project Structure

```
projects/<slug>/
├── SCRIPT.md           # Scene breakdown + narration
├── scene1.png          # Generated images
├── scene1.mp4          # Animated clips
├── scene2.png
├── scene2.mp4
├── voiceover.wav       # Full narration
├── narration.txt       # Narration text (for captions)
├── final.mp4           # Finished video
├── final_captioned.mp4 # With burned-in captions
└── POST.txt            # Captions, titles, hashtags, posting checklist
```

## Platform Specs

| Platform | Aspect | Resolution | Max Duration |
|---|---|---|---|
| TikTok | 9:16 | 1080×1920 | 10 min |
| Instagram Reels | 9:16 | 1080×1920 | 90 sec |
| YouTube Shorts | 9:16 | 1080×1920 | 60 sec |
| Square | 1:1 | 1080×1080 | varies |

## Background Music

Background tracks in `audio_samples/`:

| File | Length |
|---|---|
| `background_music_00.wav` | 58s |
| `background_music_01.wav` | 60s |
| `background_music_03.wav` | 174s |

Music loops if shorter than the video, fades in over 1s and out over the last 2.5s. `--music-volume 0.2` keeps it ~8–9 dB under the voiceover.

## Voiceover Voices

| Voice | Description |
|---|---|
| `af_heart` | American female, warm (default) |
| `af_bella` | American female, expressive |
| `am_adam` | American male, neutral |
| `am_michael` | American male, deep |
| `bf_emma` | British female |
| `bm_george` | British male |

## Notes

- Always run tools from the repo root (not subdirectories)
- ComfyUI workflows used by the tools live in `workflows/`; files move to/from ComfyUI over HTTP, so any install location works
- With `BACKEND=comfyui`, ComfyUI must be running before calling image/video tools
- MiniMax video generation can take 2–5 minutes per clip
- Assembly trims to the audio length — pad the voiceover with silence (`ffmpeg -af "adelay=1000:all=1,apad=whole_dur=<video length>"`) so the last clip isn't cut
- Kokoro generates ~150 words/minute at speed=1.0
- `voiceover.py` speaks years naturally (1852 → "eighteen fifty-two", 1850s → "eighteen fifties"); keep digits in the script so captions show "1852". Write quantities with commas ("1,500") so they aren't read as years
