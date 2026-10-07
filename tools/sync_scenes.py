#!/usr/bin/env python3
"""
Retime scene clips so each scene starts when its narration starts.

Reads per-scene narration from SCRIPT.md, gets word timings from the voiceover
(faster-whisper, via captions.py), then trims or slows each clip to fit its
slot. A clip that would need more than --max-slow is slowed to that limit and
then holds its last frame. A slow push-in zoom keeps holds from looking frozen.

Usage:
    uv run tools/sync_scenes.py \
      --project projects/my-video \
      --audio projects/my-video/voiceover_padded.wav \
      --total 46.5
Writes projects/my-video/synced/sceneN.mp4 — pass those to assemble.py.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from captions import align_to_script, transcribe_words  # noqa: E402


def clip_info(path: Path) -> tuple[float, int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height:format=duration", "-of", "default=nw=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    vals = dict(line.split("=") for line in out.strip().splitlines())
    return float(vals["duration"]), int(vals["width"]), int(vals["height"])


def scene_starts(script_md: Path, audio: Path, model: str) -> list[tuple[float, float]]:
    """(first word start, last word end) for each scene's narration."""
    lines = re.findall(r"\*\*Narration:\*\* (.*)", script_md.read_text(encoding="utf-8"))
    words = align_to_script(transcribe_words(audio, model), " ".join(lines))
    spans, i = [], 0
    for line in lines:
        n = len(line.split())
        spans.append((words[i]["start"], words[i + n - 1]["end"]))
        i += n
    return spans


def retime(src: Path, dst: Path, target: float, max_slow: float, zoom: float):
    dur, w, h = clip_info(src)
    filters = []
    if target <= dur:
        speed_note = "trim"
    else:
        factor = min(target / dur, max_slow)
        filters.append(f"setpts={factor:.4f}*PTS")
        if factor > 1.05:
            filters.append("minterpolate=fps=24:mi_mode=mci")
        hold = target - dur * factor
        if hold > 0.04:
            filters.append(f"tpad=stop_mode=clone:stop_duration={hold:.3f}")
        speed_note = f"slow {factor:.2f}x" + (f" + hold {hold:.1f}s" if hold > 0.04 else "")
    if zoom > 0:
        frames = int(target * 24) + 1
        filters.append(f"fps=24,zoompan=z='1+{zoom}*on/{frames}':x='iw/2-(iw/zoom/2)':"
                       f"y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps=24")
    filters.append("fps=24")
    cmd = ["ffmpeg", "-y", "-i", str(src), "-vf", ",".join(filters), "-t", f"{target:.3f}",
           "-an", "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ERROR retiming {src.name}\n{r.stderr[-1500:]}")
    print(f"  {src.name}: {dur:.2f}s → {target:.2f}s ({speed_note})")


def main():
    parser = argparse.ArgumentParser(description="Retime scene clips to match narration")
    parser.add_argument("--project", required=True, help="Project dir containing SCRIPT.md and sceneN.mp4")
    parser.add_argument("--audio", required=True, help="Voiceover on the final timeline (padded)")
    parser.add_argument("--total", type=float, required=True, help="Total video length in seconds")
    parser.add_argument("--lead", type=float, default=0.2, help="Cut to a scene this long before its first word")
    parser.add_argument("--max-slow", type=float, default=1.5, help="Max slow-motion factor before holding")
    parser.add_argument("--hold-zoom", type=float, default=0.08,
                        help="Push-in zoom amount for scenes that get a hold (0 disables)")
    parser.add_argument("--model", default="small.en", help="faster-whisper model")
    args = parser.parse_args()

    project = Path(args.project)
    spans = scene_starts(project / "SCRIPT.md", Path(args.audio), args.model)
    cuts = [0.0] + [max(s - args.lead, 0.0) for s, _ in spans[1:]] + [args.total]
    if spans[-1][1] > args.total:
        sys.exit(f"ERROR: narration ends at {spans[-1][1]:.2f}s, after --total {args.total}")

    out_dir = project / "synced"
    out_dir.mkdir(exist_ok=True)
    print(f"Retiming {len(spans)} scenes → {out_dir}/")
    for i in range(len(spans)):
        src = project / f"scene{i + 1}.mp4"
        target = cuts[i + 1] - cuts[i]
        dur, _, _ = clip_info(src)
        needs_hold = target > dur * args.max_slow
        retime(src, out_dir / src.name, target, args.max_slow, args.hold_zoom if needs_hold else 0)
    print("Done.")


if __name__ == "__main__":
    main()
