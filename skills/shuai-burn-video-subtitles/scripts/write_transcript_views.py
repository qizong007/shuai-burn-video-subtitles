#!/usr/bin/env python3
"""Regenerate readable transcript files from the current polished SRT."""

from __future__ import annotations

import argparse
from pathlib import Path

from srt_io import parse_srt


def plain_time(seconds: float) -> str:
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--srt", type=Path, required=True)
    parser.add_argument("--raw-srt", type=Path, help="Require cue times to match this source SRT.")
    parser.add_argument("--paragraph-chars", type=int, default=240)
    parser.add_argument("--force", action="store_true", help="Replace existing derived TXT files.")
    args = parser.parse_args()

    srt = args.srt.expanduser().resolve()
    if not srt.is_file():
        raise SystemExit(f"SRT not found: {srt}")
    if args.paragraph_chars < 1:
        raise SystemExit("--paragraph-chars must be positive")
    cues = parse_srt(srt)
    for index, cue in enumerate(cues):
        if cue["end"] <= cue["start"]:
            raise SystemExit(f"Cue {index + 1} has a non-positive duration")
        if index and cue["start"] < cues[index - 1]["end"]:
            raise SystemExit(f"Cue {index + 1} overlaps the previous cue")
    if args.raw_srt:
        raw = parse_srt(args.raw_srt.expanduser().resolve())
        polished_times = [(item["start"], item["end"]) for item in cues]
        raw_times = [(item["start"], item["end"]) for item in raw]
        if polished_times != raw_times:
            raise SystemExit("Polished SRT cue count or timecodes differ from the raw SRT")
    timestamped = srt.with_name(f"{srt.stem}_timestamped.txt")
    clean = srt.with_name(f"{srt.stem}_clean.txt")
    existing = [path for path in (timestamped, clean) if path.exists()]
    if existing and not args.force:
        raise SystemExit("Derived TXT already exists; pass --force to replace: " + ", ".join(map(str, existing)))

    timestamped_lines = []
    paragraphs = []
    buffer = []
    chars = 0
    for cue in cues:
        wording = " ".join(cue["text"].splitlines()).strip()
        if not wording:
            raise SystemExit("Empty cue in polished SRT")
        timestamped_lines.append(
            f"[{plain_time(cue['start'])}-{plain_time(cue['end'])}] {wording}"
        )
        if buffer and chars >= args.paragraph_chars:
            paragraphs.append("".join(buffer))
            buffer = []
            chars = 0
        buffer.append(wording)
        chars += len(wording)
    if buffer:
        paragraphs.append("".join(buffer))

    timestamped.write_text("\n".join(timestamped_lines) + "\n", encoding="utf-8")
    clean.write_text("\n\n".join(paragraphs) + "\n", encoding="utf-8")
    print(f"timestamped_txt={timestamped}")
    print(f"clean_txt={clean}")


if __name__ == "__main__":
    main()
