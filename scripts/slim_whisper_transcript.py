#!/usr/bin/env python3
"""Slim down a whisper.cpp --output-json transcript before feeding it to an LLM.

whisper.cpp's raw JSON repeats every timestamp twice (a "HH:MM:SS,mmm" string
under "timestamps" and a millisecond int under "offsets"), plus a metadata
block (systeminfo/model/params) that has no summarization value. For a long
recording that overhead roughly doubles the token cost of reading the file.

This script keeps just "start-end text" per segment, one line each, and
optionally applies the TC offset baked into 掃帶歐印萬-style filenames (see
common/02-tc-offset-filename.md: first 6 digits of the filename = HH:MM:SS
starting timecode on the master tape) so the output already carries real
broadcast time instead of the segment-internal 00:00:00 base.

Usage:
    python scripts/slim_whisper_transcript.py transcript.json
    python scripts/slim_whisper_transcript.py transcript.json --offset 15:56:58
    python scripts/slim_whisper_transcript.py transcript.json --from-filename "CNN 155658 四點整節.mp4"
    python scripts/slim_whisper_transcript.py transcript.json -o slim.txt
"""

from __future__ import annotations

import argparse
import json
import re
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def offset_from_filename(name: str) -> str:
    """First 6 digits of the filename -> HH:MM:SS offset (common/02-tc-offset-filename.md)."""
    match = re.search(r"(\d{6})", name)
    if not match:
        return "00:00:00"
    digits = match.group(1)
    if digits == "000000":
        return "00:00:00"
    return f"{digits[0:2]}:{digits[2:4]}:{digits[4:6]}"


def parse_hms(hms: str) -> int:
    h, m, s = (int(part) for part in hms.split(":"))
    return h * 3600 + m * 60 + s


def format_hms(total_seconds: int) -> str:
    total_seconds %= 24 * 3600
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def ms_to_seconds(ms: int) -> int:
    # Round to nearest second; segment boundaries don't need sub-second precision
    # once they're being handed to an LLM for topic-level grouping.
    return round(ms / 1000)


def slim(transcript_path: str, offset_hms: str) -> list[str]:
    with open(transcript_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    offset_seconds = parse_hms(offset_hms)
    lines = []
    for seg in data.get("transcription", []):
        start = offset_seconds + ms_to_seconds(seg["offsets"]["from"])
        end = offset_seconds + ms_to_seconds(seg["offsets"]["to"])
        text = seg["text"].strip()
        if not text:
            continue
        lines.append(f"{format_hms(start)}-{format_hms(end)} {text}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("transcript_json", help="whisper.cpp --output-json output file")
    parser.add_argument("--offset", default=None, help="TC offset as HH:MM:SS (default 00:00:00)")
    parser.add_argument("--from-filename", default=None, help="derive offset from this filename's leading 6 digits instead of --offset")
    parser.add_argument("-o", "--output", default=None, help="write to this file instead of stdout")
    args = parser.parse_args()

    if args.from_filename:
        offset_hms = offset_from_filename(args.from_filename)
    elif args.offset:
        offset_hms = args.offset
    else:
        offset_hms = "00:00:00"

    lines = slim(args.transcript_json, offset_hms)
    output_text = "\n".join(lines) + "\n"

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_text)
        print(f"{len(lines)} segments, offset {offset_hms} -> {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(output_text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
