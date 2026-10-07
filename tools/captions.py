#!/usr/bin/env python3
"""
Burn TikTok-style word-highlighted captions into a video.

Word timings come from faster-whisper run on the voiceover. If the narration
text is supplied, the script's exact words are used and whisper only provides
timing (avoids misheard words).

Usage:
    uv run tools/captions.py \
      --video projects/my-video/final.mp4 \
      --audio projects/my-video/voiceover_padded.wav \
      --file projects/my-video/narration.txt \
      --output projects/my-video/final_captioned.mp4 \
      --title "Ketchup Was Fish Sauce"   # optional: title card on the opening frames
"""

import argparse
import difflib
import re
import subprocess
import sys
from pathlib import Path

FONTS_DIR = Path(__file__).parent.parent / "fonts"
FONT_NAME = "Montserrat ExtraBold"


def transcribe_words(audio: Path, model_size: str) -> list[dict]:
    from faster_whisper import WhisperModel

    print(f"Transcribing {audio.name} (whisper {model_size})...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    # condition_on_previous_text=False stops whisper from dropping the tail of
    # long narrations (it once lost the final ~15 words of a 53s voiceover).
    segments, _ = model.transcribe(str(audio), word_timestamps=True, language="en",
                                   condition_on_previous_text=False)
    words = []
    for seg in segments:
        for w in seg.words:
            words.append({"text": w.word.strip(), "start": w.start, "end": w.end})
    return words


def norm(word: str) -> str:
    return re.sub(r"[^a-z0-9']", "", word.lower())


def align_to_script(heard: list[dict], script: str) -> list[dict]:
    """Map whisper timings onto the script's own words."""
    script_words = script.split()
    a = [norm(w["text"]) for w in heard]
    b = [norm(w) for w in script_words]
    timed: list[dict | None] = [None] * len(script_words)

    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                timed[j1 + k] = {"start": heard[i1 + k]["start"], "end": heard[i1 + k]["end"]}
        elif op == "replace":
            # Spread the heard span evenly across the script words
            start, end = heard[i1]["start"], heard[i2 - 1]["end"]
            step = (end - start) / (j2 - j1)
            for k in range(j2 - j1):
                timed[j1 + k] = {"start": start + k * step, "end": start + (k + 1) * step}

    # Script words whisper missed entirely: squeeze between neighbours
    for i, t in enumerate(timed):
        if t is None:
            prev_end = next((timed[p]["end"] for p in range(i - 1, -1, -1) if timed[p]), 0.0)
            next_start = next((timed[n]["start"] for n in range(i + 1, len(timed)) if timed[n]), prev_end + 0.3)
            timed[i] = {"start": prev_end, "end": max(next_start, prev_end + 0.05)}

    return [{"text": w, **t} for w, t in zip(script_words, timed)]


def chunk_words(words: list[dict], max_words: int, max_gap: float = 0.45) -> list[list[dict]]:
    """Group words into short caption lines, breaking on punctuation and pauses."""
    chunks, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        ends_phrase = re.search(r"[.,!?;:…]$", w["text"])
        gap = nxt is not None and nxt["start"] - w["end"] > max_gap
        if len(cur) >= max_words or ends_phrase or gap or nxt is None:
            chunks.append(cur)
            cur = []
    return chunks


def ass_time(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def build_ass(chunks: list[list[dict]], width: int, height: int, font_size: int,
              margin_v: int, highlight: str, title: str | None = None,
              title_duration: float = 3.0) -> str:
    # ASS colours are &HAABBGGRR
    hl = f"&H00{highlight[4:6]}{highlight[2:4]}{highlight[0:2]}&".upper()
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{FONT_NAME},{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,6,3,2,80,80,{margin_v},1
Style: Title,{FONT_NAME},{int(font_size * 1.3)},{hl},{hl},&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,8,4,8,90,90,{int(height * 0.17)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    if title:
        # Visible from frame 0 so it's on the cover frame, then fades out
        txt = title.upper().replace("{", "(").replace("}", ")")
        lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(title_duration)},Title,,0,0,0,,{{\\fad(0,400)}}{txt}")
    for ci, chunk in enumerate(chunks):
        # Hold each line until the next one starts (no flicker between lines)
        chunk_end = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else chunk[-1]["end"] + 0.6
        for wi, w in enumerate(chunk):
            start = w["start"]
            end = chunk[wi + 1]["start"] if wi + 1 < len(chunk) else chunk_end
            parts = []
            for k, other in enumerate(chunk):
                txt = other["text"].upper().replace("{", "(").replace("}", ")")
                parts.append(f"{{\\c{hl}}}{txt}{{\\c&H00FFFFFF&}}" if k == wi else txt)
            lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Caption,,0,0,0,,{' '.join(parts)}")
    return header + "\n".join(lines) + "\n"


def video_size(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True,
    ).stdout.strip()
    w, h = out.split(",")
    return int(w), int(h)


def main():
    parser = argparse.ArgumentParser(description="Burn word-highlighted captions into a video")
    parser.add_argument("--video", required=True, help="Input video")
    parser.add_argument("--audio", required=True, help="Voiceover audio, aligned to the video timeline")
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--text", help="Narration text (exact wording for captions)")
    src.add_argument("--file", help="File containing narration text")
    parser.add_argument("--output", required=True, help="Output video path")
    parser.add_argument("--words", type=int, default=3, help="Max words per caption line (default: 3)")
    parser.add_argument("--font-size", type=int, default=86, help="Font size at 1080px width (default: 86)")
    parser.add_argument("--position", type=float, default=0.30,
                        help="Distance from bottom as fraction of height (default: 0.30, clears TikTok UI)")
    parser.add_argument("--highlight", default="FFD60A", help="Active word colour, hex RGB (default: FFD60A yellow)")
    parser.add_argument("--title", help="Short title shown at the top of the opening frames (cover frame)")
    parser.add_argument("--title-duration", type=float, default=3.0, help="Seconds the title stays up (default: 3)")
    parser.add_argument("--model", default="small.en", help="faster-whisper model (default: small.en)")
    args = parser.parse_args()

    video, audio, output = Path(args.video), Path(args.audio), Path(args.output)
    width, height = video_size(video)
    scale = width / 1080

    words = transcribe_words(audio, args.model)
    if not words:
        sys.exit("ERROR: no speech detected in audio")
    script = args.text or (Path(args.file).read_text() if args.file else None)
    if script:
        words = align_to_script(words, script)
    # Whisper stretches a word over leading silence (e.g. the 1s pad, so the first
    # caption appeared at 0.00s); no spoken word is this long, so trim its start.
    for w in words:
        if w["end"] - w["start"] > 1.0:
            w["start"] = w["end"] - 0.6

    chunks = chunk_words(words, args.words)
    ass_path = output.with_suffix(".ass")
    ass_path.write_text(build_ass(chunks, width, height, int(args.font_size * scale),
                                  int(height * args.position), args.highlight,
                                  args.title, args.title_duration))
    print(f"  {len(words)} words → {len(chunks)} caption lines ({ass_path.name})")

    print(f"Burning captions → {output.name}")
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(video),
         "-vf", f"ass={ass_path}:fontsdir={FONTS_DIR}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "copy", str(output)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"ERROR: ffmpeg failed\n{result.stderr[-2000:]}")
    print(f"Done: {output}")


if __name__ == "__main__":
    main()
