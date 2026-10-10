---
name: shuai-burn-video-subtitles
description: "Turn a Chinese speech video into a subtitled MP4: extract audio and transcribe when no SRT exists, polish the SRT, review it in a local page, preview the style, and burn subtitles. Also use for subtitle review or burning an existing SRT. Requires libass-enabled ffmpeg for burning."
---

# Burn Video Subtitles

Accept an MP4 alone or an MP4 with an existing UTF-8 SRT. Use an existing SRT as the source of truth; transcribe only when no SRT is available. If a reviewed `<stem>_polished.srt` already exists, use it rather than regenerating it. Keep raw transcription, polished subtitles, and the source MP4 separate. Do not overwrite them.

Set `<skill-dir>` below to the directory containing this `SKILL.md`; do not assume a personal installation path.

Commands below use POSIX shell syntax. On Windows, use `python` (or `py -3`) and the PowerShell examples in [references/environment.md](references/environment.md). Resolve paths with native path tools rather than copying shell assignments or backslash continuations into PowerShell.

## 1. Transcribe when needed

Run this skill's `scripts/transcribe_video.py` with `uv` and faster-whisper. It extracts 16 kHz mono WAV and writes `<stem>.srt`, `<stem>_timestamped.txt`, `<stem>_clean.txt`, and `<stem>_segments.json` beside the video. Prefer the small model for technical speech; if its output is too rough, try a larger model after reviewing the cost and time. The script refuses to replace existing outputs unless `--force` is explicitly passed.

```bash
SKILL="<skill-dir>"
uv run --with faster-whisper --with opencc-python-reimplemented \
  python "$SKILL/scripts/transcribe_video.py" input.mp4 \
  --model Systran/faster-whisper-small
```

If `<stem>.srt` already exists, skip this step and keep that file unchanged. Do not use ASR to replace an existing user-supplied SRT.

## 2. Polish the transcript

Read the full raw SRT and make a second, model-based pass. Correct ASR errors, typos, names, technical terms, and awkward transcription artifacts against the audio/video and available project material. Verify uncertain words by listening; do not guess from a glossary. Preserve what the speaker actually said and keep the initial cue indexes and timecodes unchanged. Use simplified Chinese where appropriate. Do not turn speech into promotional copy or silently omit a point.

Write `<stem>_polished.srt` without replacing the raw SRT. Normalize each cue with `srt_io.strip_terminal_punctuation` before saving the polished SRT; the file itself must follow the punctuation rule below, not only the review display. Compare cue count and timecodes with the raw file, inspect the opening, middle, and ending, and review uncertain names and short cues against the audio. A raw SRT copied without a substantive check is not a completed polishing pass. Regenerate the readable derivatives from the polished SRT:

```bash
python3 "$SKILL/scripts/write_transcript_views.py" \
  --srt input_polished.srt --raw-srt input.srt
```

This writes `<stem>_polished_timestamped.txt` and `<stem>_polished_clean.txt`. Use `--force` only when updating these derived files after later subtitle edits. These TXT files follow the SRT; edit the SRT when wording changes.

## 3. Review the subtitles

Open the local review page with the polished SRT. The editor strips terminal punctuation from each cue before display. Do not skip the review page unless the user says 直接烧录 / 不用审核.

The monochrome review UI supports automatic local-time light/dark mode, a single sun/moon toggle, multi-selection, reversible hiding, merging adjacent cues, and undo/redo. See [references/preview-editor.md](references/preview-editor.md) for controls and save behavior.

```bash
WORK="input.subtitle-work"
python3 "$SKILL/scripts/preview_editor.py" \
  --video input.mp4 \
  --srt input_polished.srt \
  --work-dir "$WORK"
```

Start the command in the background, verify `/`, `/manifest`, `/api/transcript`, and `/api/status`, then give the user the printed URL. Tell them to review the video and captions, edit wording and timing, click **保存并关闭**, and tell you when done. Wait for their confirmation or a genuine saved state as described in [references/preview-editor.md](references/preview-editor.md). Preparing the page is not a save.

After saving, sync edits and show the diff. Then update the polished transcript views:

The page saves review JSON in `$WORK`; sync overwrites the specified polished SRT beside the video. Keep the raw SRT unchanged.

```bash
python3 "$SKILL/scripts/sync_review.py" --work-dir "$WORK" --srt input_polished.srt
python3 "$SKILL/scripts/write_transcript_views.py" --srt input_polished.srt --force
```

## 4. Preview and burn

Render a short preview, inspect caption frames, and get style approval before encoding the full video. Never overwrite the source MP4 or SRT.

```bash
python3 "$SKILL/scripts/render_subtitles.py" \
  --video input.mp4 --srt input_polished.srt \
  --output input_subtitle_preview.mp4 \
  --ass "$WORK/preview-style.ass" --preview 10 --check-dir "$WORK"

python3 "$SKILL/scripts/render_subtitles.py" \
  --video input.mp4 --srt input_polished.srt \
  --output input_subtitled.mp4 \
  --ass "$WORK/preview-style.ass" --check-dir "$WORK"
```

If an SRT is supplied and the user explicitly asks for direct burning, use it without an unnecessary ASR or polishing pass. Respect their requested review and style boundaries.

## Subtitle wording and segmentation

- **Creator punctuation requirement:** Keep commas inside a cue, but remove terminal punctuation from the polished SRT itself. Only ellipses (`…`, `……`, `...`) and exclamation marks (`!`, `！`) may remain at the end. Remove terminal periods (`。`, `.`), commas, question marks, colons, semicolons, and closing quotes/brackets. Do not replace a removed period with an exclamation mark. Apply the same rule before review, after sync, and at render time via `srt_io.strip_terminal_punctuation`; reject a cue that becomes empty.
- Split speech at commas inside a cue when the pause supports it. Set plausible time boundaries by checking the video. Keep cues ordered and non-overlapping.
- Keep complete names and technical phrases in one cue even when ASR split them. Merge adjacent cues and use their combined time span when needed.
- Verify names against the source project's own files when available. Common terms such as `Codex`, `Claude Code`, `Agent`, `Skill`, and `MCP` are examples to check, not automatic replacements.
- After syncing, confirm the SRT parses, every cue ends without punctuation or with an allowed ellipsis/exclamation mark, and no phrase is split awkwardly. Cue timecodes may change during the user's review and segmentation pass.

## Locked look

Keep these values unless the user asks to change them:

- Font: macOS uses `Hiragino Sans GB`; Windows uses Microsoft YaHei Bold / Microsoft YaHei, falling back to SimHei. `--font-file` and optional `--font-index` allow an installed Chinese font override. Keep slightly bold text (`Bold=-1` plus `\b1`).
- Size: for horizontal video (`width > height`), `height * (96 / 2160)` (96 px at 3064×2160); otherwise `height * 0.0278`
- Box: PIL-measured tight rounded rect, fill `&H1C1A1A&` at alpha `&H3D&`
- Wrap: only if measured width exceeds `85%` of a horizontal frame or `70%` of other frames; split on `，` / `,` / `。` / space
- Bottom margin: `height * 0.075`

Do not use a full-width black bar or protected PingFang paths.

## Environment

Read [references/preview-editor.md](references/preview-editor.md) for the review-page protocol, and [references/environment.md](references/environment.md) before the first run on macOS or Windows. Check Python 3.10+, Pillow, and libass-enabled FFmpeg. If port 8765 is taken, use the port printed by `preview_editor.py`; never kill an unknown process.
