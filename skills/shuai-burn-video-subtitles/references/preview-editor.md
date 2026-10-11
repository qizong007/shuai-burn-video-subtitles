# Subtitle review page

`scripts/preview_editor.py` serves a local page: video on the left, editable cues on the right. It is part of this skill. Do not clone oil-subtitle.

## Appearance and cue highlighting

The top-left header uses the **shuai** wordmark in `assets/brand/shuai-wordmark.png`, with the requested underline beneath **ai**. Keep the geometric lowercase lettering and the shorter underline. Use the black-letter artwork for light mode and `assets/brand/shuai-wordmark-dark.png` for dark mode. The i dot stays red in both themes; never invert the full image. Keep this branding in the editor UI only, never in the video or burned subtitles. See [brand.md](brand.md) for the asset and usage rules.

The monochrome review page defaults to the browser's local clock: light from 07:00 (inclusive) to 19:00 (exclusive), dark otherwise. It refreshes every minute and when focus or visibility returns. A single borderless button in the top-right app header shows the current sun/moon icon; clicking toggles light/dark with a persistent manual override. Right-click it to resume automatic mode. This affects the editor UI only, not the burned subtitle style. The right pane has one compact toolbar containing cue counts, find, selection actions, and undo/redo; do not repeat the workspace title there. Selection and hidden counts appear only when nonzero, and batch hide appears only with a selection.

Cue highlighting and the video overlay use `[start, end)` intervals. At a shared boundary, the next cue is active. Clicking a cue seeks to its start and immediately updates both; seeking and playback keep them synchronized. Gaps and hidden cues show no active subtitle.

Each cue shows its start and end on separate centered lines with a short vertical divider between them. Keep the row checkbox vertically centered, including for multiline cue text.

## Selection, hiding, and merging

- Row checkboxes only select cues; they do not hide them. The subtitle toolbar's **隐藏** appears after selecting cues and hides the selection; each eye icon toggles a cue's visibility. Hidden rows remain dimmed in the list and can be restored, including after saving and reopening.
- **合并** appears only for two or more selected, visible cues in consecutive list positions. It replaces them with one cue spanning the first start to the last end, joining their text in order with spaces. Hidden or unselected intervening rows prevent merging.
- **查找** and Cmd/Ctrl+F toggle the same search/replace panel. Escape dismisses it. There is no select-all control.
- Edits, merges, and visibility changes are cached as a browser draft until saved; selection is temporary.

## Undo and redo

The two arrows beside the cue count undo and redo committed text edits, replacements, merges, and individual/batch visibility changes. Keep up to 50 operations in memory; a new change after undo clears the redo branch. Reloading or reopening starts a fresh history, while retaining the current draft or saved data. Selection, seeking, and theme changes do not create history entries.

Outside text fields, Cmd/Ctrl+Z undoes and Cmd/Ctrl+Y redoes. Text fields and active cue editing retain the browser's native text undo. Click outside the text to commit it as one workbench operation.

## What 保存 does

The page commits the active text edit, saves **all** cues and their `hidden` flags to `subtitle-transcript.json`, and writes `manual-edit-review.json` and `preview-saved.json`. It stays open, shows a confirmation, and re-enables 保存 so the user can continue editing and save again. A successful save clears the browser draft only if no newer edits were made while the request was pending; newer edits and failed saves keep the draft.

The button does not write the SRT, encode video, or stop the server. Run `sync_review.py` after review to write only visible cues to the polished SRT; hidden cues remain in the work JSON for restoration. Regenerate transcript views and obtain subtitle-style approval before the full burn as usual. A sample preview saves only its own sample work directory.

The default work directory is `<video-stem>.subtitle-work/` beside the video (or the explicitly supplied `--work-dir`). It contains the review JSON, original transcript snapshot, manifest, and saved-state/diff records. Sync overwrites the exact path passed as `--srt`; the normal workflow updates `<stem>_polished.srt` beside the video and preserves the raw `<stem>.srt`. It does not create a new SRT output directory or automatically back up the destination SRT. Do not point sync at the raw SRT unless the user explicitly requests that overwrite.

## Start

Background the process. Close stdin. Log to the work directory:

The example below uses POSIX syntax. For PowerShell commands and Windows dependencies, see [environment.md](environment.md).

```bash
python3 scripts/preview_editor.py \
  --video VIDEO.mp4 \
  --srt VIDEO_polished.srt \
  --work-dir VIDEO.subtitle-work \
  --chapters 章节划分_VIDEO.md
```

`--chapters` is optional; if omitted, the script looks for `章节划分_<stem>.md` next to the video. `--reset` rebuilds work files from the current SRT and discards unsaved page edits.

Verify before sending a URL:

- `GET /` returns HTML
- `GET /manifest` video, duration, cue language
- `GET /api/transcript` first cue and count
- `GET /api/status` has `"saved": false` until the user clicks 保存

If the preferred port is busy, the script picks the next free port in a +9 window and prints `Preview: http://127.0.0.1:PORT/`. Use that URL.

## Wait for the user

`subtitle-transcript.json` written during prepare is not a save. 保存 keeps the editor open, so `GET /api/status` showing `"saved": true` and an existing `preview-saved.json` confirms persistence only; it does not mean the user has finished reviewing. Wait until the user confirms the review is complete / 可以继续 / 可以烧了, and ensure their latest edits have been saved before syncing or burning.

Then run `scripts/sync_review.py` to write the polished SRT and print the diff. Do not write glossary files. One-off wording fixes stay in the SRT only.

`--allow-unsaved` is only for recovering a crashed page when the user confirms the current transcript is the one they want.
