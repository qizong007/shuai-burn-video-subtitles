#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


def pick_ffmpeg():
    candidates = [
        os.environ.get("FFMPEG_BIN"),
        shutil.which("ffmpeg"),
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            result = subprocess.run(
                [candidate, "-version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            continue
        if result.returncode == 0:
            return candidate
    raise SystemExit("ffmpeg not found or not runnable")


def run(cmd):
    print("+", " ".join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)


def srt_time(seconds):
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def plain_time(seconds):
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s = rem // 1000
    return f"{h:02}:{m:02}:{s:02}"


def simplify(text):
    try:
        from opencc import OpenCC

        text = OpenCC("t2s").convert(text)
    except Exception:
        pass
    return (
        text.replace(",", "，")
        .replace("?", "？")
        .replace("!", "！")
        .replace("：", ":")
        .strip()
    )


def make_clean_paragraphs(segments, max_chars):
    paragraphs = []
    buf = []
    chars = 0
    for item in segments:
        text = simplify(item["text"])
        if not text:
            continue
        if buf and chars >= max_chars:
            paragraphs.append("".join(buf).strip())
            buf = []
            chars = 0
        buf.append(text)
        chars += len(text)
    if buf:
        paragraphs.append("".join(buf).strip())
    return paragraphs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="Input video file")
    parser.add_argument("--model", default="Systran/faster-whisper-base")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--paragraph-chars", type=int, default=240)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--force", action="store_true", help="Replace existing transcription outputs.")
    args = parser.parse_args()

    video = Path(args.video).expanduser().resolve()
    if not video.exists():
        raise SystemExit(f"video not found: {video}")

    out_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else video.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = video.stem

    audio = out_dir / f"{stem}.wav"
    timestamped_txt = out_dir / f"{stem}_timestamped.txt"
    srt = out_dir / f"{stem}.srt"
    clean_txt = out_dir / f"{stem}_clean.txt"
    segments_json = out_dir / f"{stem}_segments.json"

    outputs = [audio, timestamped_txt, srt, clean_txt, segments_json]
    existing = [path for path in outputs if path.exists()]
    if existing and not args.force:
        raise SystemExit(
            "Transcription output already exists; reuse it or pass --force to replace it: "
            + ", ".join(str(path) for path in existing)
        )

    ffmpeg = pick_ffmpeg()
    run([ffmpeg, "-hide_banner", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio)])

    from faster_whisper import WhisperModel

    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    transcribed, info = model.transcribe(str(audio), language=args.language, beam_size=5, vad_filter=True)

    segments = []
    for seg in transcribed:
        text = seg.text.strip()
        if text:
            segments.append({"start": seg.start, "end": seg.end, "text": text})

    timestamped_lines = []
    srt_lines = []
    for i, item in enumerate(segments, 1):
        text = simplify(item["text"])
        timestamped_lines.append(f"[{plain_time(item['start'])}-{plain_time(item['end'])}] {text}")
        srt_lines.extend([str(i), f"{srt_time(item['start'])} --> {srt_time(item['end'])}", text, ""])

    timestamped_txt.write_text("\n".join(timestamped_lines) + "\n", encoding="utf-8")
    srt.write_text("\n".join(srt_lines), encoding="utf-8")
    clean_txt.write_text("\n\n".join(make_clean_paragraphs(segments, args.paragraph_chars)) + "\n", encoding="utf-8")
    segments_json.write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"language={info.language} probability={info.language_probability:.3f}")
    print(f"audio={audio}")
    print(f"timestamped_txt={timestamped_txt}")
    print(f"srt={srt}")
    print(f"clean_txt={clean_txt}")
    print(f"segments_json={segments_json}")


if __name__ == "__main__":
    main()
