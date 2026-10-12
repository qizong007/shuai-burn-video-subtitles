"""File switching and SRT export must preserve sources and per-file reviews."""
from pathlib import Path
import json
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/shuai-burn-video-subtitles/scripts'
sys.path.insert(0, str(SCRIPTS))
import preview_editor as editor
import srt_io


class EditorFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.video = self.root / '视频.mp4'
        self.video.touch()
        self.a = self.root / '原始.srt'
        self.b = self.root / '校对.srt'
        self.bad = self.root / '损坏.srt'
        self.a.write_text('1\n00:00:00,125 --> 00:00:01,500\n原始文字。\n\n'
                          '2\n00:00:01,500 --> 00:00:02,000\n隐藏这一条！\n', encoding='utf-8')
        self.b.write_text('1\n00:00:00,000 --> 00:00:02,000\n另一份字幕！\n', encoding='utf-8')
        self.bad.write_text('这不是 SRT', encoding='utf-8')
        self.originals = {p: p.read_bytes() for p in (self.a, self.b, self.bad)}
        self.work = self.root / '字幕 work'
        self.prepare()
        self.server = editor.ThreadingHTTPServer(('127.0.0.1', 0), editor.make_handler(self.video, self.work))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def prepare(self, reset=False):
        with patch.object(editor, 'probe_duration', return_value=2):
            editor.prepare_work(self.video, self.a, self.work, None, reset)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, body=None):
        req = Request(f'http://127.0.0.1:{self.server.server_port}{path}',
                      data=json.dumps(body).encode('utf-8') if body is not None else None,
                      headers={'Content-Type': 'application/json'})
        with urlopen(req) as response:
            raw = response.read().decode('utf-8')
            return json.loads(raw) if 'json' in response.headers['Content-Type'] else raw

    def switch(self, path):
        current = self.request('/api/subtitles')['current']
        return self.request('/api/subtitles/switch', {'source': current, 'path': str(path)})

    def test_export_uses_live_visible_edits_without_saving_or_overwriting(self):
        state = self.request('/api/transcript')
        state['segments'][0]['text'] = '修改后的文字！\n第二行'
        state['segments'][1]['hidden'] = True
        raw = self.request('/api/export', {'source': state['current'], 'segments': state['segments']})
        self.assertEqual(raw, '1\n00:00:00,125 --> 00:00:01,500\n修改后的文字！\n第二行\n')
        self.assertEqual(self.request('/api/transcript')['segments'][0]['text'], '原始文字')
        self.assertFalse(self.request('/api/status')['saved'])
        for path, original in self.originals.items():
            self.assertEqual(path.read_bytes(), original)
        state['segments'][0]['hidden'] = True
        with self.assertRaises(HTTPError) as error:
            self.request('/api/export', {'segments': state['segments']})
        self.assertEqual(error.exception.code, 400)

    def test_switch_restores_per_file_review_and_selected_file_after_restart(self):
        a = self.request('/api/transcript')
        a['segments'][0].update(text='A 已编辑！', hidden=False)
        a['segments'][1]['hidden'] = True
        self.request('/api/transcript', {'source': a['current'], 'segments': a['segments']})
        # Saving must not invalidate the key of newer browser drafts.
        self.assertEqual(self.request('/api/transcript')['draft_key'], a['draft_key'])
        b = self.switch(self.b)
        self.assertEqual(b['current'], str(self.b))
        self.assertEqual(b['segments'][0]['text'], '另一份字幕！')
        self.assertFalse(self.request('/api/status')['saved'])
        b['segments'][0]['text'] = 'B 已编辑！'
        self.request('/api/transcript', {'source': b['current'], 'segments': b['segments']})
        restored = self.switch(self.a)
        self.assertEqual(restored['segments'], a['segments'])
        self.assertEqual(restored['draft_key'], a['draft_key'])
        self.assertTrue(self.request('/api/status')['saved'])
        self.switch(self.b)
        self.prepare()  # Original CLI --srt must not relabel the restored B review as A.
        restored = self.request('/api/transcript')
        self.assertEqual(restored['current'], str(self.b))
        self.assertEqual(restored['segments'][0]['text'], 'B 已编辑！')
        for path, original in self.originals.items():
            self.assertEqual(path.read_bytes(), original)

    def test_invalid_switch_and_stale_tab_save_cannot_change_active_review(self):
        a = self.request('/api/transcript')
        with self.assertRaises(HTTPError) as error:
            self.switch(self.bad)
        self.assertEqual(error.exception.code, 400)
        self.assertEqual(self.request('/api/transcript'), a)
        outside = self.root / 'outside'
        outside.mkdir()
        other = outside / 'other.srt'
        other.write_bytes(self.b.read_bytes())
        with self.assertRaises(HTTPError):
            self.switch(other)
        b = self.switch(self.b)
        with self.assertRaises(HTTPError) as error:
            self.request('/api/transcript', {'source': a['current'], 'segments': a['segments']})
        self.assertEqual(error.exception.code, 409)
        self.assertEqual(self.request('/api/transcript'), b)

    def test_reset_clears_saved_flags_and_snapshots(self):
        a = self.request('/api/transcript')
        self.request('/api/transcript', {'segments': a['segments']})
        self.switch(self.b)
        self.prepare(reset=True)
        self.assertEqual(self.request('/api/transcript')['current'], str(self.a))
        self.assertFalse(self.request('/api/status')['saved'])
        self.assertFalse((self.work / 'subtitle-files').exists())


if __name__ == '__main__':
    unittest.main()
