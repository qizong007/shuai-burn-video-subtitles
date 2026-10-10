# macOS and Windows setup

Use Python 3.10 or newer, FFmpeg, and ffprobe. Burning also needs Pillow and an FFmpeg build with libass (`ass` filter) and `libx264`. Transcription uses `uv`, faster-whisper, and OpenCC; the first run downloads the model.

## macOS

Check `python3`, `uv`, `ffmpeg`, and `ffprobe` on PATH, then install Pillow in the Python environment used to run the scripts:

```bash
python3 -m pip install pillow
ffmpeg -hide_banner -filters
```

Verify `ass` is listed. Some FFmpeg builds omit libass; check the actual binary. Use `--ffmpeg PATH` / `--ffprobe PATH` or `FFMPEG_BIN` / `FFPROBE_BIN` to select another build.

The default font is the system `Hiragino Sans GB`, keeping the existing caption appearance.

## Windows (PowerShell)

Install Python 3.10+, [uv](https://docs.astral.sh/uv/getting-started/installation/), and a [Windows FFmpeg build](https://ffmpeg.org/download.html#build-windows) with libass. Add the directory containing `ffmpeg.exe` and `ffprobe.exe` to PATH, then reopen PowerShell.

```powershell
python --version
python -m pip install pillow
ffmpeg -hide_banner -filters | Select-String '\bass\b'
ffprobe -version
$env:PYTHONUTF8 = '1'
```

If the `python` command is unavailable, use `py -3`. The normal default font search is `%WINDIR%\Fonts\msyhbd.ttc`, then `msyh.ttc`, then `simhei.ttf`. These are Chinese fonts; Windows editions without them need a user-supplied Chinese TTF/OTF/TTC.

Example commands from the repository root; replace input paths:

```powershell
$Skill = Join-Path $PWD 'skills/shuai-burn-video-subtitles'
uv run --with faster-whisper --with opencc-python-reimplemented python "$Skill/scripts/transcribe_video.py" 'C:\Videos\input.mp4' --model Systran/faster-whisper-small
python "$Skill/scripts/preview_editor.py" --video 'C:\Videos\input.mp4' --srt 'C:\Videos\input_polished.srt' --work-dir 'C:\Videos\input.subtitle-work'
```

The polished SRT is created by the Agent's review pass between transcription and opening the editor. Open the printed URL, save, and then run the sync in another terminal or stop the server first:

```powershell
python "$Skill/scripts/sync_review.py" --work-dir 'C:\Videos\input.subtitle-work' --srt 'C:\Videos\input_polished.srt'
python "$Skill/scripts/write_transcript_views.py" --srt 'C:\Videos\input_polished.srt' --force
python "$Skill/scripts/render_subtitles.py" --video 'C:\Videos\input.mp4' --srt 'C:\Videos\input_polished.srt' --output 'C:\Videos\input_subtitle_preview.mp4' --preview 10
```

Approve the preview before rendering the full video, with `--preview 10` removed and a new output name.

## Fonts and paths

On either platform, `--font-file PATH` overrides the font; `--font-index N` selects a face inside a TTC. Font family names in ASS are derived from the selected font (the macOS default retains its existing family name). Font size, bold text, box, padding, and wrapping rules remain the same across platforms; glyph appearance varies by font.

During encoding, the script copies ASS and the chosen font into a native temporary directory and uses relative filter paths. Video and output paths are absolute subprocess arguments, so spaces, Chinese characters, and Windows drive letters do not enter the filtergraph. The temporary staging directory is removed after encoding.

FFmpeg resolution: explicit argument, environment variable, PATH, then optional macOS local-build/Homebrew fallbacks. ffprobe also checks beside the chosen FFmpeg, including `ffprobe.exe` on Windows. A custom local build directory is optional.

Only macOS and Windows are targeted here. Other platforms can supply fonts explicitly, but are not covered by the platform tests. Source video and original SRT preservation, review/save protocol, punctuation rules, and caption layout are unchanged.
