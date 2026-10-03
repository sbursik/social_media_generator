"""Generate voiceover audio using Kokoro ONNX (CPU-friendly local TTS).

Usage:
    uv run tools/voiceover.py --text "Hello world" --output audio.wav
    uv run tools/voiceover.py --text "Hello world" --voice af_heart --output audio.wav
    uv run tools/voiceover.py --file script.txt --output audio.wav

Available voices (English):
    af_heart    — American female, warm (default)
    af_bella    — American female, expressive
    am_adam     — American male, neutral
    am_michael  — American male, deep
    bf_emma     — British female
    bm_george   — British male
"""

import argparse
import sys
from pathlib import Path


def list_voices():
    from kokoro_onnx import Kokoro
    k = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")
    print("Available voices:")
    for v in sorted(k.get_voices()):
        print(f"  {v}")


def generate(text: str, voice: str, output: Path, speed: float = 1.0):
    try:
        from kokoro_onnx import Kokoro
    except ImportError:
        print("ERROR: kokoro-onnx not installed. Run: uv sync", file=sys.stderr)
        sys.exit(1)

    import soundfile as sf

    print(f"Generating voiceover ({voice}, speed={speed})...")
    kokoro = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")
    samples, sample_rate = kokoro.create(text, voice=voice, speed=speed, lang="en-us")

    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), samples, sample_rate)
    print(f"Saved: {output}")

    # Return duration for timing sync
    duration = len(samples) / sample_rate
    print(f"Duration: {duration:.2f}s")
    return duration


def main():
    parser = argparse.ArgumentParser(description="Generate voiceover with Kokoro TTS")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text", help="Text to synthesize")
    group.add_argument("--file", help="Text file to synthesize")
    group.add_argument("--list-voices", action="store_true", help="List available voices")
    parser.add_argument("--voice", default="af_heart", help="Voice name (default: af_heart)")
    parser.add_argument("--speed", type=float, default=1.0, help="Speech speed multiplier (default: 1.0)")
    parser.add_argument("--output", help="Output .wav file path")
    args = parser.parse_args()

    if args.list_voices:
        list_voices()
        return

    if not args.output:
        parser.error("--output is required")

    if args.file:
        text = Path(args.file).read_text().strip()
    else:
        text = args.text

    generate(text, args.voice, Path(args.output), args.speed)


if __name__ == "__main__":
    main()
