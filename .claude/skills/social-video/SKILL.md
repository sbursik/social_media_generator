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

#### Hooks (every video)

Viewers decide in the first 1–2 seconds whether to keep watching, so plan the hooks before the scenes:

- **Title hook**: the on-screen title (2–6 words) makes a surprising claim or opens a curiosity gap. It shouldn't just name the topic. Patterns that work:
  - Myth flip: "Pizza Wasn't Italian" / "Ketchup Was Fish Sauce"
  - Unexpected origin: "The Chicago Hot Dog Was a Depression Meal"
  - Direct stakes: "Your Job Is Next"
  - Hidden truth: "AI Lies With a Straight Face"
  Not "The History of Pizza" or "AI and Jobs".
- **Hook line**: a short white teaser under the title (3–6 words) that adds a second open loop, e.g. "And it's never had ketchup", "It wasn't even red", "Watch till the end". It's burned in with `captions.py --hook`.
- **Opening narration (scene 1, first ~3s)**: lead with the most surprising true claim. No greetings, no "Did you know", no setup. Then open a loop the video only closes near the end, e.g. "...and the reason why is stranger than you think." Write down the payoff scene in SCRIPT.md so it really gets paid off.
- **Opening visual (scene 1)**: the most striking image in the video. Put the subject in close-up with motion from frame 0 (pour, sprinkle, crack, reveal). No slow establishing shots.
- **Re-hook halfway through**: put a one-line turn around 40–50% of the runtime ("But that's not the strangest part.", "Then it all went wrong.") so viewers don't drop off mid-video.
- **Honesty**: every hook must be true and paid off in the video. No fake stats, no promises the video doesn't keep (strict sourcing still applies). Clickbait that doesn't pay off kills retention and gets comments calling it out.

Write `projects/<slug>/SCRIPT.md` with this structure:

```markdown
# <Title>

Platform: tiktok | Duration: ~30s | Tone: cinematic

## Hooks
- **Title:** <2–6 word on-screen title — surprising claim / curiosity gap>
- **Hook line:** <3–6 word teaser under the title>
- **Opening line:** <scene 1 narration — boldest true claim + open loop>
- **Payoff:** <which scene closes the open loop>
- **Re-hook:** <mid-video turn line, ~40–50% in>

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
  --hook "It wasn't even red" \
  --output projects/<slug>/final_captioned.mp4
```

Options: `--words 3` (words per line), `--font-size 86`, `--position 0.30` (fraction from bottom), `--highlight FFD60A`, `--title-duration 3`.

Always pass `--title` and `--hook` from the SCRIPT.md Hooks section. The title shows in yellow in the upper third from frame 0, so it's on the cover frame. The hook line sits under it in smaller white text. Both fade out after 3s (`--title-duration`).

### Step 8 — Social post copy

Write `projects/<slug>/POST.txt` with ready-to-paste posting text (format: `templates/POST.example.txt`):

- **TikTok / Reels caption** — the first line is the hook (opening claim or title hook; it's the only part shown before "more"), then a 1–2 sentence teaser that hints at the payoff without giving it away, a question to drive comments, then 6–8 hashtags incl. the channel tag
- **YouTube Shorts** — title ≤100 chars ending in `#shorts`. Front-load the hook in the first ~40 chars (that's what shows in the feed), e.g. "Ketchup Was Fish Sauce 🐟 (not tomato) #shorts", not "The History of Ketchup". Then a short description with a follow CTA and comma-separated tags
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
