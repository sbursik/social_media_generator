"""Assemble video clips + voiceover into a final social media video using FFmpeg.

Usage:
    # Assemble clips in order with a single voiceover track
    uv run tools/assemble.py --clips scene1.mp4 scene2.mp4 scene3.mp4 \\
                              --audio voiceover.wav --output final.mp4

    # With background music mixed in
    uv run tools/assemble.py --clips scene1.mp4 scene2.mp4 \\
                              --audio voiceover.wav --music bg.mp3 --music-volume 0.15 \\
                              --output final.mp4

    # Specify target platform aspect ratio (adds letterbox/pillarbox if needed)
    uv run tools/assemble.py --clips scene1.mp4 --audio vo.wav \\
                              --platform tiktok --output final.mp4
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

# Platform presets: (width, height)
PLATFORMS = {
    "tiktok":    (1080, 1920),  # 9:16
    "reels":     (1080, 1920),  # 9:16
    "shorts":    (1080, 1920),  # 9:16
    "square":    (1080, 1080),  # 1:1
    "landscape": (1920, 1080),  # 16:9
}


def run(cmd: list[str], desc: str = ""):
    print(f"  {desc or ' '.join(cmd[:3])}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg error:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result


def concat_clips(clips: list[Path], output: Path, width: int, height: int):
    """Concatenate clips, scaling/padding each to target dimensions."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        list_path = Path(f.name)
        for clip in clips:
            f.write(f"file '{clip.resolve()}'\n")

    # Scale and pad each clip to exact dimensions, then concat
    inputs = []
    filter_parts = []
    for i, clip in enumerate(clips):
        inputs += ["-i", str(clip)]
        filter_parts.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}];"
        )

    n = len(clips)
    concat_v = "".join(f"[v{i}]" for i in range(n))
    filter_complex = "".join(filter_parts) + f"{concat_v}concat=n={n}:v=1:a=0[vout]"

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-an",
        str(output),
    ]
    run(cmd, f"Concatenating {n} clips → {output.name}")


def mix_audio(voiceover: Path, music: Path | None, music_volume: float, duration: float, output: Path):
    """Mix voiceover with optional background music, trim to duration."""
    if music is None:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(voiceover),
            "-t", str(duration),
            "-c:a", "aac", "-b:a", "192k",
            str(output),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(voiceover),
            "-stream_loop", "-1", "-i", str(music),
            "-filter_complex",
            # normalize=0 keeps the voiceover at full level; music fades in/out
            f"[1:a]volume={music_volume},afade=t=in:d=1,"
            f"afade=t=out:st={max(duration - 2.5, 0)}:d=2.5[bg];"
            f"[0:a][bg]amix=inputs=2:duration=first:normalize=0[aout]",
            "-map", "[aout]",
            "-t", str(duration),
            "-c:a", "aac", "-b:a", "192k",
            str(output),
        ]
    run(cmd, "Mixing audio")


def get_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True,
    )
    import json
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def main():
    parser = argparse.ArgumentParser(description="Assemble video clips into a final social media video")
    parser.add_argument("--clips", nargs="+", required=True, help="Video clip paths in order")
    parser.add_argument("--audio", required=True, help="Voiceover audio file (.wav or .mp3)")
    parser.add_argument("--music", help="Optional background music file")
    parser.add_argument("--music-volume", type=float, default=0.15, help="Background music volume 0-1 (default: 0.15)")
    parser.add_argument("--platform", choices=list(PLATFORMS.keys()), default="tiktok", help="Target platform (default: tiktok)")
    parser.add_argument("--width", type=int, help="Override width (overrides --platform)")
    parser.add_argument("--height", type=int, help="Override height (overrides --platform)")
    parser.add_argument("--output", required=True, help="Output video path")
    args = parser.parse_args()

    clips = [Path(c) for c in args.clips]
    for c in clips:
        if not c.exists():
            print(f"ERROR: Clip not found: {c}", file=sys.stderr)
            sys.exit(1)

    audio = Path(args.audio)
    if not audio.exists():
        print(f"ERROR: Audio not found: {audio}", file=sys.stderr)
        sys.exit(1)

    music = Path(args.music) if args.music else None
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    w, h = PLATFORMS[args.platform]
    if args.width:
        w = args.width
    if args.height:
        h = args.height

    print(f"Assembling {len(clips)} clips at {w}x{h} for {args.platform}...")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Step 1: Concat video clips
        video_only = tmp_path / "video_only.mp4"
        concat_clips(clips, video_only, w, h)

        # Step 2: Get video duration
        duration = get_duration(video_only)

        # Step 3: Mix audio
        mixed_audio = tmp_path / "audio.aac"
        mix_audio(audio, music, args.music_volume, duration, mixed_audio)

        # Step 4: Combine video + audio
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_only),
            "-i", str(mixed_audio),
            "-c:v", "copy",
            "-c:a", "copy",
            "-shortest",
            str(output),
        ]
        run(cmd, f"Writing final video → {output.name}")

    print(f"\nDone: {output} ({duration:.1f}s, {w}x{h})")


if __name__ == "__main__":
    main()
