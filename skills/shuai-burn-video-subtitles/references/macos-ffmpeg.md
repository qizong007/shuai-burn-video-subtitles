# macOS FFmpeg for subtitle burns

Some FFmpeg builds do not include libass or the `ass` filter required by this skill. Check the installed binary rather than assuming its package includes subtitle support.

Search order used by `scripts/render_subtitles.py`:

1. `--ffmpeg` / `--ffprobe`
2. `$FFMPEG_BIN` / `$FFPROBE_BIN`
3. `$HOME/Tools/ffmpeg/ffmpeg` (optional local build, checked for libass support)
4. `ffmpeg` / `ffprobe` on `PATH`
5. `/opt/homebrew/bin/ffmpeg` and `/usr/local/bin/ffmpeg`

`ffprobe` may come from Homebrew even when `ffmpeg` does not. That is fine.

Confirm before encoding:

```bash
"$FFMPEG_BIN" -hide_banner -filters | awk '$2=="ass"{print}'
```

If `ass` is missing, stop and use a libass build. Do not fall back to `drawtext` or a full-width `BorderStyle=3` box.

The `ass` filter treats `:` as an option separator. Generate ASS wherever convenient, then pass a colon-free copy such as `/tmp/burn-subs-*/subs.ass` into `-vf ass=...`. Chinese characters in the video `-i` path are acceptable.

Keep `fontsdir=/System/Library/Fonts` so Hiragino Sans GB resolves. Do not pass PingFang TTCs from protected system paths; FFmpeg can silently substitute a Latin fallback.
