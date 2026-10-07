---
name: social-video
description: "Create short-form social media videos (TikTok, Reels, YouTube Shorts) using local ComfyUI for image and video generation, Kokoro TTS for voiceover, and FFmpeg for assembly. Run from the repo root."
---

# Social Video Skill

Create a complete social media video from a concept: scenes are written, images generated via ComfyUI (Gemini Nano Banana 2), animated via ComfyUI (MiniMax H3 Max) — or both via the direct APIs when `.env` has `BACKEND=direct` (no ComfyUI, e.g. on Windows) — narrated with Kokoro TTS, and assembled with FFmpeg.

## How to invoke

This skill is triggered when the user says things like:
- "create a video about..."
- "make a TikTok about..."
- "generate a Reel for..."
- "/video"

## Workflow

Read `CLAUDE.md` in the repo root first for full tool documentation.

### Step 1 — Gather requirements

Ask the user for:
- **Concept** — what is the video about?
- **Platform** — tiktok / reels / shorts / square / landscape (default: tiktok)
- **Duration** — target length in seconds (default: 30s)
- **Tone** — cinematic, energetic, calm, educational, etc.

If the user has already provided this, skip asking and proceed.

### Step 2 — Create project

```bash
mkdir -p projects/<slug>
```

Slug = lowercase hyphenated version of the concept (e.g. "mountain-sunset").

### Step 3 — Write script to SCRIPT.md

Plan 1 scene per ~5 seconds of video. Each scene needs:
- **Image prompt** — detailed visual description for Gemini (no text in image unless needed)
- **Motion prompt** — camera movement + action for MiniMax H3
- **Narration** — the spoken line(s) for this scene

Write `projects/<slug>/SCRIPT.md` with this structure:

```markdown
# <Title>

Platform: tiktok | Duration: ~30s | Tone: cinematic

## Narration (full script)
<full voiceover text, all scenes combined>

## Scenes

### Scene 1 (~5s)
**Image:** <detailed image generation prompt>
**Motion:** <animation prompt — camera, movement, atmosphere>
**Narration:** <spoken text for this scene>

### Scene 2 (~5s)
...
```

### Step 4 — Generate assets

For each scene, run sequentially (ComfyUI processes one job at a time):

```bash

# Image
uv run tools/comfyui_image.py \
  --prompt "<image prompt>" \
  --aspect 9:16 \
  --output projects/<slug>/scene1.png

# Video clip
uv run tools/comfyui_video.py \
  --image projects/<slug>/scene1.png \
  --prompt "<motion prompt>" \
  --duration 5 \
  --output projects/<slug>/scene1.mp4
```

### Step 5 — Generate voiceover

```bash
uv run tools/voiceover.py \
  --text "<full narration from SCRIPT.md>" \
  --voice af_heart \
  --output projects/<slug>/voiceover.wav
```

Then pad it: 1s of silence at the start (otherwise the first word is clipped) and silence at the end up to the total clip length (assembly trims to audio length):

```bash
ffmpeg -y -i projects/<slug>/voiceover.wav \
  -af "adelay=1000:all=1,apad=whole_dur=<total clip seconds>" \
  projects/<slug>/voiceover_padded.wav
```

### Step 6 — Sync scenes to narration, then assemble with background music

Scene narration lengths vary, so fixed 5s clips drift out of sync. Retime them first (trims, mild slow-mo, or slow-mo + held last frame with push-in zoom):

```bash
uv run tools/sync_scenes.py --project projects/<slug> \
  --audio projects/<slug>/voiceover_padded.wav --total <total seconds>
```

Then assemble using `projects/<slug>/synced/sceneN.mp4`. If one scene's narration is much longer than 5s × 1.5, consider generating that clip with `--duration 10` instead of relying on a long hold.

Pick a track from `audio_samples/` that fits the tone. If unsure, render one version per track (`final_music00.mp4`, ...) and let the user choose.

```bash
uv run tools/assemble.py \
  --clips projects/<slug>/synced/scene1.mp4 projects/<slug>/synced/scene2.mp4 ... \
  --audio projects/<slug>/voiceover_padded.wav \
  --music audio_samples/background_music_00.wav \
  --music-volume 0.2 \
  --platform tiktok \
  --output projects/<slug>/final.mp4
```

### Step 7 — Captions

Save the full narration to `projects/<slug>/narration.txt`, then:

```bash
uv run tools/captions.py \
  --video projects/<slug>/final.mp4 \
  --audio projects/<slug>/voiceover_padded.wav \
  --file projects/<slug>/narration.txt \
  --title "Ketchup Was Fish Sauce" \
  --output projects/<slug>/final_captioned.mp4
```

Options: `--words 3` (words per line), `--font-size 86`, `--position 0.30` (fraction from bottom), `--highlight FFD60A`, `--title-duration 3`.

Always pass `--title` with a short title (2–5 words, usually the SCRIPT.md heading). It shows in yellow in the upper third from frame 0, so it's on the cover frame, then fades out after 3s.

### Step 8 — Social post copy

Write `projects/<slug>/POST.txt` with ready-to-paste posting text (format: `templates/POST.example.txt`):

- **TikTok / Reels caption** — hook line (usually the video's first line), 1–2 sentence teaser, a question to drive comments, then 6–8 hashtags incl. the channel tag
- **YouTube Shorts** — title ≤100 chars ending in `#shorts`, short description with a follow CTA, comma-separated tags
- **Hashtag bank** — ~14 topic hashtags to rotate (3–6 per post)
- **Posting checklist** — turn ON the platform's AI-generated content label (TikTok "AI-generated content", YouTube "Altered or synthetic content", Instagram "AI info"); suggested cover frame with timestamp; pinned-comment idea

Keep claims consistent with the narration — no statistics the video doesn't make.

### Step 9 — Report

Tell the user:
- Output path: `projects/<slug>/final_captioned.mp4` (and uncaptioned `final.mp4`), plus `POST.txt`
- Total duration
- Any scenes that may need a re-run

## Error handling

- If a ComfyUI node says "Please login first": `COMFY_API_KEY` is missing — add it to `.env` in the repo root (see README)

- With `BACKEND=direct`: a missing `GEMINI_API_KEY` / `MINIMAX_API_KEY` stops the tool with a clear error; only 768P video is available (`--upscale` for 2K)
- If ComfyUI can't be reached: check it's running at `COMFYUI_URL` (default http://127.0.0.1:8188)
- If Kokoro fails with model not found: run the setup commands in CLAUDE.md
- If a video clip looks wrong: re-run just that scene's comfyui_video.py with a different seed or refined motion prompt
