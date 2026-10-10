#!/usr/bin/env python3
"""Burn a UTF-8 SRT into an MP4 with the approved caption look.

White Chinese text, slightly bold, tight rounded translucent box, bottom-centered.
For landscape video, use the user-approved larger type and allow 85% frame width.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from srt_io import parse_srt, strip_terminal_punctuation  # noqa: E402

try:
    from PIL import ImageFont
except ImportError:
    sys.exit("Need Pillow. Install with: python3 -m pip install pillow")

LANDSCAPE_FONT_SIZE_RATIO = 96 / 2160
OTHER_FONT_SIZE_RATIO = 0.0278
PAD_RATIO = 0.0083
MARGIN_BOTTOM_RATIO = 0.075
LANDSCAPE_WRAP_WIDTH_RATIO = 0.85
OTHER_WRAP_WIDTH_RATIO = 0.70
BOX_COLOR = r"\1c&H1C1A1A&\1a&H3D&"


def rounded_rect_path(width: int, height: int, radius: int) -> str:
    width = max(1, int(width))
    height = max(1, int(height))
    radius = max(1, min(int(radius), width // 2, height // 2))
    curve = int(round(radius * 0.55228475))
    return (
        f"m {radius} 0 "
        f"l {width - radius} 0 "
        f"b {width - radius + curve} 0 {width} {radius - curve} {width} {radius} "
        f"l {width} {height - radius} "
        f"b {width} {height - radius + curve} {width - radius + curve} {height} {width - radius} {height} "
        f"l {radius} {height} "
        f"b {radius - curve} {height} 0 {height - radius + curve} 0 {height - radius} "
        f"l 0 {radius} "
        f"b 0 {radius - curve} {radius - curve} 0 {radius} 0"
    )


def resolve_font(explicit: Path | None = None, index: int | None = None) -> tuple[Path, int]:
    if explicit:
        candidates = [(explicit.expanduser().resolve(), index if index is not None else 0)]
    elif sys.platform == "win32":
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        candidates = [(fonts / name, index if index is not None else 0)
                      for name in ("msyhbd.ttc", "msyh.ttc", "simhei.ttf")]
    else:
        candidates = [(Path("/System/Library/Fonts/Hiragino Sans GB.ttc"), index if index is not None else 1)]
    for path, face in candidates:
        try:
            ImageFont.truetype(str(path), size=32, index=face)
            return path, face
        except OSError:
            continue
    raise SystemExit("No usable Chinese font found. Pass --font-file PATH and optionally --font-index N.")


def measure_text(font: ImageFont.FreeTypeFont, text: str) -> tuple[int, int]:
    lines = [line for line in text.split("\n") if line] or [""]
    widths = []
    heights = []
    for line in lines:
        left, top, right, bottom = font.getbbox(line)
        widths.append(max(1, right - left))
        heights.append(max(1, bottom - top))
    line_gap = int(font.size * 0.28)
    height = sum(heights) + line_gap * (len(lines) - 1)
    return max(widths), height


def wrap_if_needed(font: ImageFont.FreeTypeFont, text: str, max_width: int) -> str:
    text = text.replace("\r", "").strip()
    width, _ = measure_text(font, text)
    if width <= max_width or "\n" in text:
        return text
    for separator in ("，", ",", "。", " "):
        if separator not in text:
            continue
        parts = [part.strip() for part in text.split(separator) if part.strip()]
        if len(parts) < 2:
            continue
        joined = []
        current = parts[0]
        for part in parts[1:]:
            trial = f"{current}{separator}{part}"
            trial_w, _ = measure_text(font, trial)
            if trial_w <= max_width:
                current = trial
            else:
                joined.append(current + separator)
                current = part
        joined.append(current)
        if len(joined) > 1:
            return "\n".join(joined)
    mid = max(1, len(text) // 2)
    return text[:mid] + "\n" + text[mid:]


def ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    sec = seconds % 60
    cs = int(round((sec - int(sec)) * 100))
    if cs == 100:
        sec = int(sec) + 1
        cs = 0
        if sec == 60:
            sec = 0
            m += 1
            if m == 60:
                m = 0
                h += 1
    return f"{h}:{m:02d}:{int(sec):02d}.{cs:02d}"


def escape_ass(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def write_ass(cues: list[dict], output: Path, width: int, height: int,
              font_path: Path | None = None, font_index: int | None = None) -> dict:
    landscape = width > height
    font_size_ratio = LANDSCAPE_FONT_SIZE_RATIO if landscape else OTHER_FONT_SIZE_RATIO
    wrap_width_ratio = LANDSCAPE_WRAP_WIDTH_RATIO if landscape else OTHER_WRAP_WIDTH_RATIO
    font_size = int(round(height * font_size_ratio))
    pad = int(round(height * PAD_RATIO))
    margin_bottom = int(round(height * MARGIN_BOTTOM_RATIO))
    font_path, font_index = resolve_font(font_path, font_index)
    font = ImageFont.truetype(str(font_path), size=font_size, index=font_index)
    font_family = "Hiragino Sans GB" if font_path.name == "Hiragino Sans GB.ttc" else font.getname()[0]
    max_text_width = int(width * wrap_width_ratio)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CaptionText,{font_family},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: CaptionBox,Arial,10,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    wrapped = 0
    for cue in cues:
        clean_text = strip_terminal_punctuation(str(cue["text"]))
        if not clean_text:
            raise ValueError("A cue is empty after removing terminal punctuation")
        text = wrap_if_needed(font, clean_text, max_text_width)
        if not text:
            continue
        if "\n" in text and "\n" not in cue["text"]:
            wrapped += 1
        text_w, text_h = measure_text(font, text)
        box_width = min(width - 40, text_w + pad * 2)
        box_height = text_h + pad * 2
        radius = max(6, int(font_size * 0.18))
        box_x = int((width - box_width) / 2)
        box_y = height - margin_bottom - box_height
        center_x = box_x + box_width / 2
        center_y = box_y + box_height / 2
        start, end = ass_time(cue["start"]), ass_time(cue["end"])
        path = rounded_rect_path(box_width, box_height, radius)
        events.append(
            f"Dialogue: 0,{start},{end},CaptionBox,,0,0,0,,"
            f"{{\\an7\\pos({box_x},{box_y})\\p1{BOX_COLOR}\\bord0\\shad0}}{path}"
        )
        events.append(
            f"Dialogue: 1,{start},{end},CaptionText,,0,0,0,,"
            f"{{\\an5\\pos({center_x:.1f},{center_y:.1f})\\b1}}{escape_ass(text)}"
        )
    output.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return {
        "width": width,
        "height": height,
        "font_size": font_size,
        "pad": pad,
        "margin_bottom": margin_bottom,
        "cues": len(cues),
        "wrapped": wrapped,
        "font_file": str(font_path),
        "font_index": font_index,
        "font_family": font_family,
    }


def run_output(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True, encoding="utf-8", errors="replace", stderr=subprocess.STDOUT)


def has_filter(ffmpeg: str, name: str) -> bool:
    try:
        out = run_output([ffmpeg, "-hide_banner", "-filters"])
    except (OSError, subprocess.CalledProcessError):
        return False
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == name:
            return True
    return False


def first_existing(paths: list[str | None]) -> list[str]:
    seen: list[str] = []
    for path in paths:
        if not path or path in seen:
            continue
        seen.append(path)
    return seen


def resolve_ffmpeg(explicit: str | None) -> str:
    candidates = first_existing(
        [
            explicit,
            os.environ.get("FFMPEG_BIN"),
            shutil.which("ffmpeg"),
            str(Path.home() / "Tools/ffmpeg/ffmpeg"),
            "/opt/homebrew/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
        ]
    )
    found = []
    for path in candidates:
        if Path(path).is_file() or shutil.which(path):
            found.append(path)
            if has_filter(path, "ass"):
                return str(Path(shutil.which(path) or path).resolve())
    hint = ", ".join(found) or "none"
    raise SystemExit(
        "No ffmpeg with libass/ass filter. "
        f"Tried: {hint}. Set FFMPEG_BIN or pass --ffmpeg with a libass-enabled binary."
    )


def resolve_ffprobe(explicit: str | None, ffmpeg: str) -> str:
    sibling = str(Path(ffmpeg).with_name("ffprobe" + Path(ffmpeg).suffix))
    candidates = first_existing(
        [
            explicit,
            os.environ.get("FFPROBE_BIN"),
            shutil.which("ffprobe"),
            sibling,
            "/opt/homebrew/bin/ffprobe",
            "/usr/local/bin/ffprobe",
        ]
    )
    for path in candidates:
        if Path(path).is_file() or shutil.which(path):
            return str(Path(shutil.which(path) or path).resolve())
    raise SystemExit("ffprobe not found. Set FFPROBE_BIN.")


def probe_size(ffprobe: str, video: Path) -> tuple[int, int]:
    out = subprocess.check_output(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(video),
        ],
        text=True,
    ).strip()
    raw_width, raw_height = out.split(",")
    return int(raw_width), int(raw_height)


def probe_duration(ffprobe: str, media: Path) -> float:
    out = subprocess.check_output(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(media),
        ],
        text=True,
    ).strip()
    return float(out)


def burn_video(ffmpeg: str, video: Path, output: Path, ass_path: Path,
               font_path: Path, preview: float | None) -> None:
    # Relative filter paths avoid Windows drive colons and filtergraph escaping.
    with tempfile.TemporaryDirectory(prefix="burn-subs-") as stage:
        stage_path = Path(stage)
        shutil.copy2(ass_path, stage_path / "subs.ass")
        fonts = stage_path / "fonts"
        fonts.mkdir()
        # System fonts may have protected metadata that cannot be copied.
        shutil.copyfile(font_path, fonts / ("caption" + font_path.suffix))
        cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video)]
        if preview is not None:
            cmd += ["-t", str(preview)]
        cmd += ["-map", "0:v:0", "-map", "0:a?", "-vf", "ass=subs.ass:fontsdir=fonts",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "copy", "-movflags", "+faststart", str(output)]
        output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(cmd, cwd=stage_path, check=True)


def extract_frames(
    ffmpeg: str,
    video: Path,
    cues: list[dict],
    output_dir: Path,
    preview: float | None,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    visible = [cue for cue in cues if preview is None or cue["start"] < preview]
    if not visible:
        return []
    picks = []
    first, last = visible[0], visible[-1]
    picks.append(("start", min(first["start"] + 0.25, (first["start"] + first["end"]) / 2)))
    if len(visible) > 2:
        mid = visible[len(visible) // 2]
        picks.append(("mid", (mid["start"] + mid["end"]) / 2))
    if last is not first:
        picks.append(("end", max(last["start"] + 0.1, last["end"] - 0.15)))
    paths = []
    for name, t in picks:
        if preview is not None:
            t = min(t, max(0.0, preview - 0.05))
        dest = output_dir / f"subtitle-check-{name}.jpg"
        subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{t:.3f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                str(dest),
            ],
            check=True,
        )
        paths.append(dest)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Burn Chinese SRT with the approved caption style.")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--srt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ass", type=Path, help="Keep the generated ASS next to the work files.")
    parser.add_argument("--preview", type=float, help="Only encode the first N seconds.")
    parser.add_argument("--check-dir", type=Path, help="Write a few subtitle-check JPEGs after render.")
    parser.add_argument("--ass-only", action="store_true", help="Write ASS and exit without encoding.")
    parser.add_argument("--ffmpeg")
    parser.add_argument("--ffprobe")
    parser.add_argument("--font-file", type=Path, help="Override the platform's Chinese font (TTF/OTF/TTC).")
    parser.add_argument("--font-index", type=int, help="Face index in a font collection; default depends on the font.")
    args = parser.parse_args()

    video = args.video.expanduser().resolve()
    srt = args.srt.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not video.is_file():
        raise SystemExit(f"Video not found: {video}")
    if not srt.is_file():
        raise SystemExit(f"SRT not found: {srt}")
    if output in {video, srt}:
        raise SystemExit("Refusing to overwrite the source video or SRT.")

    ffmpeg = resolve_ffmpeg(args.ffmpeg)
    ffprobe = resolve_ffprobe(args.ffprobe, ffmpeg)
    width, height = probe_size(ffprobe, video)
    try:
        cues = parse_srt(srt)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if args.ass:
        ass_path = args.ass.expanduser().resolve()
        ass_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        work = Path(tempfile.mkdtemp(prefix="burn-subs-"))
        ass_path = work / "subs.ass"
    layout = write_ass(cues, ass_path, width, height, args.font_file, args.font_index)
    print(
        f"layout: {layout['width']}x{layout['height']} font={layout['font_size']} "
        f"margin_bottom={layout['margin_bottom']} cues={layout['cues']} wrapped={layout['wrapped']}"
    )
    print(f"ffmpeg: {ffmpeg}")
    print(f"ASS: {ass_path}")
    print(f"font: {layout['font_family']} ({layout['font_file']}, face {layout['font_index']})")
    if args.ass_only:
        return

    burn_video(ffmpeg, video, output, ass_path, Path(layout["font_file"]), args.preview)
    print(f"Rendered: {output}")
    duration = probe_duration(ffprobe, output)
    print(f"duration: {duration:.6f}s {width}x{height}")
    if args.preview is None:
        source_duration = probe_duration(ffprobe, video)
        delta = abs(duration - source_duration)
        if delta > 0.25:
            raise SystemExit(f"Duration mismatch: source {source_duration:.3f}s vs output {duration:.3f}s")

    if args.check_dir:
        frames = extract_frames(ffmpeg, output, cues, args.check_dir, args.preview)
        for frame in frames:
            print(f"check: {frame}")


if __name__ == "__main__":
    main()
