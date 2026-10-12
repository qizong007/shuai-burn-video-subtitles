#!/usr/bin/env python3
"""Shared SRT and chapter helpers for preview and burn."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path


def strip_terminal_punctuation(text: str) -> str:
    text = text.rstrip()
    while text and unicodedata.category(text[-1]).startswith("P"):
        # Creator preference: sentence-final ellipses and exclamation marks
        # are allowed; periods, commas, question marks, and wrappers are not.
        if text[-1] in "…!！" or text.endswith("..."):
            break
        text = text[:-1].rstrip()
    return text


def parse_srt(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        raise ValueError(f"Empty SRT: {path}")
    cues = []
    for block in raw.split("\n\n"):
        lines = [line for line in block.splitlines() if line.strip()]
        time_index = next((i for i, line in enumerate(lines) if " --> " in line), None)
        if time_index is None or time_index + 1 >= len(lines):
            continue
        start_raw, end_raw = lines[time_index].split(" --> ")

        def to_seconds(value: str) -> float:
            value = value.strip().replace(".", ",")
            h, m, rest = value.split(":")
            s, ms = rest.split(",")
            return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

        cues.append(
            {
                "start": to_seconds(start_raw),
                "end": to_seconds(end_raw.split()[0]),
                "text": "\n".join(lines[time_index + 1 :]).strip(),
            }
        )
    if not cues:
        raise ValueError(f"No cues parsed from {path}")
    return cues


def srt_timestamp(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_srt(cues: list[dict]) -> str:
    blocks = []
    for index, cue in enumerate(cues, start=1):
        text = strip_terminal_punctuation(str(cue.get("text") or "").strip())
        if not text:
            raise ValueError(f"Cue {index} is empty after removing terminal punctuation")
        blocks.append(
            f"{index}\n{srt_timestamp(float(cue['start']))} --> {srt_timestamp(float(cue['end']))}\n{text}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def write_srt(cues: list[dict], path: Path) -> None:
    path.write_text(format_srt(cues), encoding="utf-8")


def parse_chapters_md(path: Path, duration: float) -> list[dict]:
    chapters = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        stamp, title = parts
        bits = stamp.split(":")
        if len(bits) == 3:
            hours, minutes, secs = bits
            start = int(hours) * 3600 + int(minutes) * 60 + float(secs)
        elif len(bits) == 2:
            minutes, secs = bits
            start = int(minutes) * 60 + float(secs)
        else:
            continue
        chapters.append({"start": round(start, 3), "title": title.strip()})
    for index, chapter in enumerate(chapters):
        end = chapters[index + 1]["start"] if index + 1 < len(chapters) else duration
        chapter["end"] = round(end, 3)
    return chapters


def cue_key(cue: dict) -> tuple[float, float]:
    return (round(float(cue["start"]), 3), round(float(cue["end"]), 3))


def load_segments(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("segments") or [])
    return list(data)


def dump_segments(path: Path, segments: list[dict]) -> None:
    path.write_text(
        json.dumps({"segments": segments}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def diff_segments(before: list[dict], after: list[dict]) -> dict:
    before_map = {cue_key(item): item.get("text", "") for item in before}
    after_map = {cue_key(item): item.get("text", "") for item in after}
    changed = []
    for key, text in after_map.items():
        if key in before_map and before_map[key] != text:
            changed.append(
                {
                    "start": key[0],
                    "end": key[1],
                    "before": before_map[key],
                    "after": text,
                }
            )
    return {
        "before_count": len(before),
        "after_count": len(after),
        "deleted": [
            {"start": key[0], "end": key[1], "text": before_map[key]}
            for key in before_map
            if key not in after_map
        ],
        "added": [
            {"start": key[0], "end": key[1], "text": after_map[key]}
            for key in after_map
            if key not in before_map
        ],
        "changed": changed,
    }
