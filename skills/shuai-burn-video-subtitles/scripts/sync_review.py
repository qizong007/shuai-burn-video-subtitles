#!/usr/bin/env python3
"""Write the reviewed transcript back to a UTF-8 SRT."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from srt_io import diff_segments, dump_segments, load_segments, strip_terminal_punctuation, write_srt  # noqa: E402

SAVED_NAME = "preview-saved.json"
TRANSCRIPT_NAME = "subtitle-transcript.json"
ORIG_NAME = "subtitle-transcript.json.orig.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync saved preview edits into an SRT.")
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--srt", type=Path, required=True, help="Destination SRT, usually *_polished.srt.")
    parser.add_argument("--allow-unsaved", action="store_true")
    args = parser.parse_args()

    work_dir = args.work_dir.expanduser().resolve()
    srt = args.srt.expanduser().resolve()
    transcript = work_dir / TRANSCRIPT_NAME
    orig = work_dir / ORIG_NAME
    saved = work_dir / SAVED_NAME
    if not transcript.is_file():
        raise SystemExit(f"Missing {transcript}")
    if not saved.is_file() and not args.allow_unsaved:
        raise SystemExit(
            f"No {SAVED_NAME}. Wait until the user clicks 保存, or pass --allow-unsaved."
        )

    after = load_segments(transcript)
    after = [{**cue, "text": strip_terminal_punctuation(str(cue.get("text") or ""))} for cue in after]
    if any(not cue["text"] for cue in after):
        raise SystemExit("A cue is empty after removing terminal punctuation")
    dump_segments(transcript, after)
    # Keep hidden cues in the workbench for restoration; omit them from the SRT.
    after = [cue for cue in after if not cue.get("hidden")]
    before = load_segments(orig) if orig.is_file() else after
    report = diff_segments(before, after)
    write_srt(after, srt)
    print(f"Wrote {len(after)} cues to {srt}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    for item in report["changed"]:
        print(f"~ {item['start']:.3f}  {item['before']}  ->  {item['after']}")
    for item in report["deleted"]:
        print(f"- {item['start']:.3f}  {item['text']}")
    for item in report["added"]:
        print(f"+ {item['start']:.3f}  {item['text']}")


if __name__ == "__main__":
    main()
