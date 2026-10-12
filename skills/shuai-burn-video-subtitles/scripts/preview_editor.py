#!/usr/bin/env python3
"""Local subtitle review page: left video, right editable cue list."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from srt_io import (  # noqa: E402
    diff_segments,
    dump_segments,
    format_srt,
    load_segments,
    parse_chapters_md,
    parse_srt,
    strip_terminal_punctuation,
)

HTML_PATH = SCRIPT_DIR.parent / "assets" / "preview.html"
BRAND_ASSETS = {
    f"/brand/{name}": SCRIPT_DIR.parent / "assets" / "brand" / name
    for name in ("shuai-wordmark.png", "shuai-wordmark-dark.png")
}
SAVED_NAME = "preview-saved.json"
TRANSCRIPT_NAME = "subtitle-transcript.json"
ORIG_NAME = "subtitle-transcript.json.orig.json"
CHAPTERS_NAME = "subtitle-chapters.json"
MANIFEST_NAME = "subtitle-manifest.json"
REVIEW_FILES = (TRANSCRIPT_NAME, ORIG_NAME, SAVED_NAME, "manual-edit-review.json")


def review_cues(segments: list[dict]) -> list[dict]:
    result = []
    for seg in segments:
        start, end = float(seg["start"]), float(seg["end"])
        text = strip_terminal_punctuation(str(seg.get("text") or "").strip())
        if not text:
            raise ValueError("字幕内容不能为空")
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise ValueError("字幕时间无效")
        result.append({"start": start, "end": end, "text": text, "hidden": bool(seg.get("hidden"))})
    return result


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
    manifest_path = work_dir / MANIFEST_NAME
    previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    source = str(srt.resolve())
    if not reset and transcript_path.is_file():
        source = previous.get("source_srt") or source
    duration = probe_duration(video) or 0.0

    if reset or not transcript_path.is_file():
        cues = parse_srt(srt)
        cues = [{**cue, "text": strip_terminal_punctuation(cue["text"])} for cue in cues]
        if any(not cue["text"] for cue in cues):
            raise ValueError("A cue is empty after removing terminal punctuation")
        dump_segments(transcript_path, cues)
        dump_segments(orig_path, cues)
        for name in (SAVED_NAME, "manual-edit-review.json"):
            (work_dir / name).unlink(missing_ok=True)
        if reset:
            shutil.rmtree(work_dir / "subtitle-files", ignore_errors=True)
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
        "source_srt": source,
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
    lock = threading.RLock()

    def read_manifest() -> dict:
        return json.loads((work_dir / MANIFEST_NAME).read_text(encoding="utf-8"))

    def source_info() -> dict:
        source = Path(read_manifest()["source_srt"])
        candidates = {path.resolve() for path in source.parent.iterdir()
                      if path.is_file() and path.suffix.lower() == ".srt"} if source.parent.is_dir() else set()
        candidates.add(source)
        return {
            "current": str(source),
            "files": [{"path": str(path), "name": path.name} for path in sorted(candidates, key=lambda p: p.name.casefold())],
            "draft_key": f"burn-subs:{video}:{work_dir}:{source}:{orig_path.stat().st_mtime_ns}",
        }

    def switch_source(target: Path) -> None:
        manifest = read_manifest()
        current = Path(manifest["source_srt"])
        if target == current:
            return
        # Parse first so an invalid SRT cannot disturb the active review.
        cues = review_cues(parse_srt(target))
        snapshots = work_dir / "subtitle-files"
        def snapshot_dir(path: Path) -> Path:
            return snapshots / hashlib.sha256(str(path).encode("utf-8")).hexdigest()
        old_dir = snapshot_dir(current)
        new_dir = snapshot_dir(target)
        old_dir.mkdir(parents=True, exist_ok=True)
        for name in REVIEW_FILES:
            if (work_dir / name).is_file():
                shutil.copy2(work_dir / name, old_dir / name)
            else:
                (old_dir / name).unlink(missing_ok=True)
        for name in REVIEW_FILES:
            (work_dir / name).unlink(missing_ok=True)
        if (new_dir / TRANSCRIPT_NAME).is_file():
            for name in REVIEW_FILES:
                if (new_dir / name).is_file():
                    shutil.copy2(new_dir / name, work_dir / name)
        else:
            dump_segments(transcript_path, cues)
            dump_segments(orig_path, cues)
        manifest["source_srt"] = str(target)
        (work_dir / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

        def do_GET(self) -> None:
            if urlparse(self.path).path == "/video":
                send_file_range(self, video, "video/mp4")
                return
            with lock:
                self.get_locked()

        def get_locked(self) -> None:
            path = urlparse(self.path).path
            if path in {"/", "/index.html"}:
                cache_key = json.dumps(
                    f"burn-subs:{video}:{transcript_path}:{transcript_path.stat().st_mtime}"
                )
                body = html.replace("__CACHE_KEY__", cache_key).encode("utf-8")
                send_bytes(self, 200, body, "text/html; charset=utf-8")
                return
            if path in BRAND_ASSETS:
                send_bytes(self, 200, BRAND_ASSETS[path].read_bytes(), "image/png")
                return
            if path == "/manifest":
                payload = json.loads((work_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
                payload["video"] = "/video"
                send_json(self, payload)
                return
            if path == "/api/transcript":
                send_json(self, {"segments": load_segments(transcript_path), **source_info()})
                return
            if path == "/api/subtitles":
                send_json(self, source_info())
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
            with lock:
                try:
                    self.post_locked()
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    send_json(self, {"error": str(exc)}, 400)

        def post_locked(self) -> None:
            path = urlparse(self.path).path
            if path not in {"/api/transcript", "/api/subtitles/switch", "/api/export"}:
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            if body.get("source") and body["source"] != read_manifest()["source_srt"]:
                send_json(self, {"error": "当前文件已切换，请刷新页面后重试"}, 409)
                return
            if path == "/api/subtitles/switch":
                target = Path(body["path"]).expanduser().resolve()
                if str(target) not in {item["path"] for item in source_info()["files"]}:
                    raise ValueError("请选择列表中的 SRT 文件")
                switch_source(target)
                send_json(self, {"segments": load_segments(transcript_path), **source_info()})
                return
            if path == "/api/export":
                visible = review_cues([seg for seg in body.get("segments", []) if not seg.get("hidden")])
                if not visible:
                    raise ValueError("没有可导出的可见字幕")
                send_bytes(self, 200, format_srt(visible).encode("utf-8"), "application/x-subrip; charset=utf-8")
                return
            segments = review_cues(body.get("segments") or [])
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
    print("Click 保存 after review. Do not treat prepare files as user confirmation.")
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
