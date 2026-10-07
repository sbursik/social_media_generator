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

Years (1000–2099) are spoken the natural way: 1852 -> "eighteen fifty-two",
1905 -> "nineteen oh five", 1850s -> "eighteen fifties", 2024 -> "twenty twenty-four".
Write quantities with a comma ("1,500 people") so they aren't read as years.
"""

import argparse
import re
import sys
from pathlib import Path

ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
        "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
        "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

# Standalone 4-digit years 1000–2099, optionally as a decade ("1850s").
# Comma-grouped quantities like "1,500" and prices like "$1500" are left alone.
YEAR_RE = re.compile(r"(?<![\d$£€,.])(1\d{3}|20\d{2})(s|'s)?(?!\d|[,.]\d)")


def two_digits(n: int) -> str:
    if n < 20:
        return ONES[n]
    return TENS[n // 10] + ("-" + ONES[n % 10] if n % 10 else "")


def plural(word: str) -> str:
    """'fifty' -> 'fifties', 'hundred' -> 'hundreds'."""
    return word[:-1] + "ies" if word.endswith("y") else word + "s"


def year_to_words(year: int, decade: bool = False) -> str:
    """1852 -> eighteen fifty-two, 1905 -> nineteen oh five, 2024 -> twenty twenty-four."""
    hi, lo = divmod(year, 100)
    if 2000 <= year < 2010:
        words = "two thousand" + (" " + ONES[lo] if lo else "")
    elif lo == 0:
        words = two_digits(hi) + " hundred"
    elif lo < 10:
        words = two_digits(hi) + " oh " + ONES[lo]
    else:
        words = two_digits(hi) + " " + two_digits(lo)
    if decade:
        head, _, last = words.rpartition(" ")
        words = (head + " " if head else "") + plural(last)
    return words


def speak_years(text: str) -> str:
    """Rewrite years so Kokoro says 'eighteen fifty-two', not 'one thousand eight hundred...'."""
    return YEAR_RE.sub(lambda m: year_to_words(int(m.group(1)), bool(m.group(2))), text)


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
    text = speak_years(text)
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
