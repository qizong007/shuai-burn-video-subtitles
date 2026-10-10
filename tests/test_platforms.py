"""Platform regression tests plus a two-second render; no ASR model download."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/shuai-burn-video-subtitles/scripts'
sys.path.insert(0, str(SCRIPTS))
import preview_editor
import render_subtitles as render
import srt_io
import transcribe_video


class PlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg = render.resolve_ffmpeg(None)
        cls.ffprobe = render.resolve_ffprobe(None, cls.ffmpeg)
        configured = os.environ.get('SUBTITLE_TEST_FONT')
        cls.font, cls.face = render.resolve_font(Path(configured) if configured else None)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='subtitle-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "字幕 work's [01]"
        self.root.mkdir()

    def make_video(self):
        video = self.root / '输入 clip.mp4'
        subprocess.run([self.ffmpeg, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                        'color=c=black:s=640x360:r=24:d=2', '-f', 'lavfi', '-i',
                        'anullsrc=r=16000:cl=mono', '-t', '2', '-c:v', 'libx264',
                        '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(video)], check=True)
        return video

    def test_windows_font_discovery_and_override(self):
        fonts = self.root / 'Fonts'
        fonts.mkdir()
        # A usable font in a simulated Windows installation, independent of host OS.
        candidate = fonts / 'msyhbd.ttc'
        shutil.copyfile(self.font, candidate)
        with patch.object(render.sys, 'platform', 'win32'), patch.dict(os.environ, {'WINDIR': str(self.root)}):
            selected, face = render.resolve_font()
        self.assertEqual(selected, candidate)
        self.assertEqual(face, 0)
        custom = self.root / ('自定义 font' + self.font.suffix)
        shutil.copyfile(self.font, custom)
        self.assertEqual(render.resolve_font(custom, self.face), (custom.resolve(), self.face))

    def test_windows_ffprobe_sibling(self):
        ffmpeg = self.root / 'ffmpeg.exe'
        sibling = self.root / 'ffprobe.exe'
        sibling.touch()
        with patch.object(render.shutil, 'which', return_value=None), patch.dict(os.environ, {'FFPROBE_BIN': ''}):
            self.assertEqual(render.resolve_ffprobe(None, str(ffmpeg)), str(sibling.resolve()))

    def test_video_without_srt_produces_transcript(self):
        video = self.make_video()
        model = SimpleNamespace(transcribe=lambda *a, **k: (
            iter([SimpleNamespace(start=0.0, end=1.5, text='这是一段口播。')]),
            SimpleNamespace(language='zh', language_probability=1.0)))
        fake_whisper = SimpleNamespace(WhisperModel=lambda *a, **k: model)
        with patch.dict(sys.modules, {'faster_whisper': fake_whisper}), \
             patch.dict(os.environ, {'FFMPEG_BIN': self.ffmpeg}), \
             patch.object(sys, 'argv', ['transcribe_video.py', str(video)]), \
             contextlib.redirect_stdout(io.StringIO()):
            transcribe_video.main()
            for suffix in ('.wav', '.srt', '_clean.txt', '_timestamped.txt', '_segments.json'):
                self.assertTrue(video.with_name(video.stem + suffix).is_file())
            self.assertEqual(srt_io.parse_srt(video.with_suffix('.srt'))[0]['text'], '这是一段口播。')
            with self.assertRaises(SystemExit):
                transcribe_video.main()  # Existing transcripts require explicit --force.

    def test_save_then_sync_preserves_source_and_hidden_rows(self):
        video = self.make_video()
        source = self.root / '原始.srt'
        source.write_text('1\n00:00:00,000 --> 00:00:01,000\n原始，文字。\n\n'
                          '2\n00:00:01,000 --> 00:00:02,000\n保留！\n', encoding='utf-8')
        original = source.read_bytes()
        work = self.root / 'input.subtitle-work'
        preview_editor.prepare_work(video, source, work, None, False)
        server = preview_editor.ThreadingHTTPServer(('127.0.0.1', 0), preview_editor.make_handler(video, work))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            cues = srt_io.load_segments(work / preview_editor.TRANSCRIPT_NAME)
            self.assertEqual(cues[0]['text'], '原始，文字')  # Existing punctuation rule stays intact.
            cues[0].update(text='已改，文字。', hidden=True)
            request = Request(f'http://127.0.0.1:{server.server_port}/api/transcript',
                              data=json.dumps({'segments': cues}).encode('utf-8'),
                              headers={'Content-Type': 'application/json'})
            with urlopen(request) as response:
                self.assertEqual(response.status, 200)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        self.assertEqual(source.read_bytes(), original)
        destination = self.root / '校对.srt'
        subprocess.run([sys.executable, str(SCRIPTS / 'sync_review.py'), '--work-dir', str(work),
                        '--srt', str(destination)], check=True, stdout=subprocess.PIPE)
        self.assertEqual([c['text'] for c in srt_io.parse_srt(destination)], ['保留！'])
        self.assertTrue(srt_io.load_segments(work / preview_editor.TRANSCRIPT_NAME)[0]['hidden'])
        self.assertEqual(source.read_bytes(), original)

    def test_real_burn_with_unicode_spaces_and_font_override(self):
        video = self.make_video()
        before = hashlib.sha256(video.read_bytes()).hexdigest()
        srt = self.root / '字幕.srt'
        srt.write_text('1\n00:00:00,000 --> 00:00:02,000\n有视频，就能做字幕！\n', encoding='utf-8')
        output = self.root / '成片 output.mp4'
        ass = self.root / '样式.ass'
        env = {**os.environ, 'PYTHONUTF8': '1'}
        subprocess.run([sys.executable, str(SCRIPTS / 'render_subtitles.py'), '--video', str(video),
                        '--srt', str(srt), '--output', str(output), '--ass', str(ass),
                        '--font-file', str(self.font), '--font-index', str(self.face),
                        '--ffmpeg', self.ffmpeg, '--ffprobe', self.ffprobe],
                       check=True, env=env, stdout=subprocess.PIPE)
        self.assertAlmostEqual(render.probe_duration(self.ffprobe, output), 2.0, delta=0.25)
        self.assertEqual(hashlib.sha256(video.read_bytes()).hexdigest(), before)
        # An otherwise black frame must contain visible burned caption pixels.
        pixels = subprocess.check_output([self.ffmpeg, '-v', 'error', '-ss', '0.5', '-i', str(output),
                                          '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'])
        self.assertTrue(any(v > 128 for v in pixels[640 * 260 * 3:]))
        layout = ass.read_text(encoding='utf-8')
        self.assertIn('有视频，就能做字幕！', layout)
        self.assertIn('\\b1', layout)


if __name__ == '__main__':
    unittest.main()
