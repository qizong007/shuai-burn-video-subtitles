#!/usr/bin/env python3
"""Local subtitle review page: left video, right editable cue list."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from srt_io import (  # noqa: E402
    diff_segments,
    dump_segments,
    load_segments,
    parse_chapters_md,
    parse_srt,
    strip_terminal_punctuation,
)

HTML_PATH = SCRIPT_DIR.parent / "assets" / "preview.html"
WORDMARK_PATH = SCRIPT_DIR.parent / "assets" / "brand" / "shuai-wordmark-ai.png"
SAVED_NAME = "preview-saved.json"
TRANSCRIPT_NAME = "subtitle-transcript.json"
ORIG_NAME = "subtitle-transcript.json.orig.json"
CHAPTERS_NAME = "subtitle-chapters.json"
MANIFEST_NAME = "subtitle-manifest.json"


def probe_duration(video: Path) -> float:
    ffprobe = os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe") or "ffprobe"
    try:
        out = subprocess.check_output(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video),
            ],
            text=True,
        ).strip()
        return float(out)
    except Exception:
        return 0.0


def default_work_dir(video: Path) -> Path:
    return video.parent / f"{video.stem}.subtitle-work"


def default_chapters(video: Path) -> Path | None:
    candidate = video.parent / f"章节划分_{video.stem}.md"
    return candidate if candidate.is_file() else None


def prepare_work(
    video: Path,
    srt: Path,
    work_dir: Path,
    chapters_path: Path | None,
    reset: bool,
) -> dict:
    work_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = work_dir / TRANSCRIPT_NAME
    orig_path = work_dir / ORIG_NAME
    duration = probe_duration(video) or 0.0

    if reset or not transcript_path.is_file():
        cues = parse_srt(srt)
        cues = [{**cue, "text": strip_terminal_punctuation(cue["text"])} for cue in cues]
        if any(not cue["text"] for cue in cues):
            raise ValueError("A cue is empty after removing terminal punctuation")
        dump_segments(transcript_path, cues)
        dump_segments(orig_path, cues)
    elif not orig_path.is_file():
        shutil.copy2(transcript_path, orig_path)

    if duration <= 0:
        cues = load_segments(transcript_path)
        duration = float(cues[-1]["end"]) if cues else 0.0

    chapters = []
    if chapters_path and chapters_path.is_file():
        chapters = parse_chapters_md(chapters_path, duration)
        (work_dir / CHAPTERS_NAME).write_text(
            json.dumps({"duration": duration, "chapters": chapters}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
    elif (work_dir / CHAPTERS_NAME).is_file() and not reset:
        payload = json.loads((work_dir / CHAPTERS_NAME).read_text(encoding="utf-8"))
        chapters = list(payload.get("chapters") or [])

    try:
        rel_video = os.path.relpath(video, work_dir)
    except ValueError:
        rel_video = str(video)

    manifest = {
        "video": rel_video,
        "subtitle_mode": "zh",
        "duration": duration,
        "languages": [{"code": "zh", "name": "中文", "transcript": TRANSCRIPT_NAME, "source": True}],
        "chapters_file": CHAPTERS_NAME if chapters else None,
        "chapters": chapters,
    }
    (work_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "work_dir": str(work_dir),
        "transcript": str(transcript_path),
        "orig": str(orig_path),
        "duration": duration,
        "cues": len(load_segments(transcript_path)),
        "chapters": len(chapters),
        "saved": (work_dir / SAVED_NAME).is_file(),
    }


def pick_port(host: str, preferred: int) -> int:
    for port in range(preferred, preferred + 10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    raise SystemExit(f"No free port in {preferred}-{preferred + 9}")


def send_bytes(handler: BaseHTTPRequestHandler, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    for key, value in (extra or {}).items():
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)


def send_json(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    send_bytes(handler, status, raw, "application/json; charset=utf-8")


def send_file_range(handler: BaseHTTPRequestHandler, path: Path, content_type: str) -> None:
    file_size = path.stat().st_size
    range_header = handler.headers.get("Range")
    start, end = 0, file_size - 1
    status = 200
    if range_header and range_header.startswith("bytes="):
        spec = range_header.split("=", 1)[1].split(",")[0]
        left, _, right = spec.partition("-")
        if left:
            start = int(left)
        if right:
            end = int(right)
        end = min(end, file_size - 1)
        if start > end or start >= file_size:
            handler.send_error(416)
            return
        status = 206
    length = end - start + 1
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(length))
    if status == 206:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
    handler.end_headers()
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining:
            chunk = handle.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            handler.wfile.write(chunk)
            remaining -= len(chunk)


def make_handler(video: Path, work_dir: Path) -> type[BaseHTTPRequestHandler]:
    transcript_path = work_dir / TRANSCRIPT_NAME
    orig_path = work_dir / ORIG_NAME
    html = HTML_PATH.read_text(encoding="utf-8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in {"/", "/index.html"}:
                cache_key = json.dumps(
                    f"burn-subs:{video}:{transcript_path}:{transcript_path.stat().st_mtime}"
                )
                body = html.replace("__CACHE_KEY__", cache_key).encode("utf-8")
                send_bytes(self, 200, body, "text/html; charset=utf-8")
                return
            if path == "/brand/shuai-wordmark-ai.png":
                send_bytes(self, 200, WORDMARK_PATH.read_bytes(), "image/png")
                return
            if path == "/manifest":
                payload = json.loads((work_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
                payload["video"] = "/video"
                send_json(self, payload)
                return
            if path == "/video":
                send_file_range(self, video, "video/mp4")
                return
            if path == "/api/transcript":
                send_json(self, {"segments": load_segments(transcript_path)})
                return
            if path == "/api/status":
                saved_path = work_dir / SAVED_NAME
                payload = {"saved": saved_path.is_file(), "cues": len(load_segments(transcript_path))}
                if saved_path.is_file():
                    payload.update(json.loads(saved_path.read_text(encoding="utf-8")))
                send_json(self, payload)
                return
            self.send_error(404)

        def do_HEAD(self) -> None:
            if urlparse(self.path).path == "/video":
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(video.stat().st_size))
                self.end_headers()
                return
            self.do_GET()

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/api/transcript":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            segments = body.get("segments") or []
            segments = [
                {**seg, "text": strip_terminal_punctuation(str(seg.get("text") or ""))}
                for seg in segments
            ]
            if any(not seg["text"] for seg in segments):
                send_json(self, {"error": "A cue is empty after removing terminal punctuation"}, 400)
                return
            if not orig_path.is_file():
                shutil.copy2(transcript_path, orig_path)
            before = load_segments(orig_path)
            dump_segments(transcript_path, segments)
            visible = [seg for seg in segments if not seg.get("hidden")]
            report = diff_segments([seg for seg in before if not seg.get("hidden")], visible)
            report_path = work_dir / "manual-edit-review.json"
            report_path.write_text(
                json.dumps({"status": "ok", "mode": "preview-save", **report}, ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
            saved = {
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "cues": len(segments),
                "hidden": len(segments) - len(visible),
                "changed": len(report["changed"]),
                "deleted": len(report["deleted"]),
                "added": len(report["added"]),
            }
            (work_dir / SAVED_NAME).write_text(
                json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            send_json(self, {"ok": True, **saved})

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare and serve the subtitle review page.")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--srt", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--chapters", type=Path)
    parser.add_argument("--port", type=int, default=int(os.environ.get("PREVIEW_EDITOR_PORT", "8765")))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--reset", action="store_true", help="Rebuild work files from the current SRT.")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()

    video = args.video.expanduser().resolve()
    srt = args.srt.expanduser().resolve()
    if not video.is_file():
        raise SystemExit(f"Video not found: {video}")
    if not srt.is_file():
        raise SystemExit(f"SRT not found: {srt}")
    try:
        parse_srt(srt)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    work_dir = (args.work_dir or default_work_dir(video)).expanduser().resolve()
    chapters = args.chapters.expanduser().resolve() if args.chapters else default_chapters(video)
    info = prepare_work(video, srt, work_dir, chapters, args.reset)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    if args.prepare_only:
        return

    port = pick_port(args.host, args.port)
    server = ThreadingHTTPServer((args.host, port), make_handler(video, work_dir))
    pid_path = work_dir / "preview-editor.pid"
    pid_path.write_text(str(os.getpid()), encoding="utf-8")
    url = f"http://{args.host}:{port}/"
    print(f"Preview: {url}")
    print(f"PID file: {pid_path}")
    print("Click 保存并关闭 after review. Do not treat prepare files as user confirmation.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
        if pid_path.is_file() and pid_path.read_text(encoding="utf-8").strip() == str(os.getpid()):
            pid_path.unlink()


if __name__ == "__main__":
    main()
