"""Regression checks for the editor's actual JavaScript without browser dependencies."""
from pathlib import Path
import shutil
import subprocess
import unittest

HTML = Path(__file__).resolve().parents[1] / 'skills/shuai-burn-video-subtitles/assets/preview.html'


class SearchTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js is needed for editor JavaScript checks')
    def test_search_and_replacement_regressions(self):
        result = subprocess.run(['node', '-e', r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const elements = new Map();
function element() {
  return { value: '', textContent: '', listeners: {},
    addEventListener(type, fn) { this.listeners[type] = fn; },
    querySelector() { return element(); },
    toggleAttribute() {}, setAttribute() {}, focus() {}, select() {},
    classList: { contains() { return false; }, toggle() {} },
  };
}
const context = vm.createContext({
  assert, console, setInterval() {},
  localStorage: { getItem() {}, setItem() {}, removeItem() {} },
  window: { addEventListener() {} },
  document: {
    documentElement: { dataset: {} }, addEventListener() {},
    getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
    querySelectorAll() { return []; },
  },
});
const html = fs.readFileSync(process.argv[1], 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match => match[1]);
vm.runInContext(scripts[0], context);
// Skip network initialization; use the real event handlers and search/replacement functions.
vm.runInContext(scripts[1].split('\ninit().catch')[0].replace('__CACHE_KEY__', '"test"'), context);
vm.runInContext(`
  render = () => refreshFindMatches();
  paintFindResults = () => {};
  locateFindMatch = () => {};
  function query(value) {
    findInput.value = value;
    findInput.listeners.input();
  }
  segments = [
    { _id: 'a', text: 'Codex codex & <标签> .*', start: 0, end: 1 },
    { _id: 'b', text: '中文中文 Codex', hidden: true, start: 1, end: 2 },
  ];
  query('codex');
  assert.equal(findMatches.length, 3);
  assert.equal(findIndex, 0);
  const original = JSON.stringify(segments);
  findInput.listeners.keydown({ key: 'Enter', preventDefault() {} });
  assert.equal(findIndex, 1);
  assert.equal(JSON.stringify(segments), original, 'Enter must never replace/delete');
  findInput.listeners.keydown({ key: 'Enter', shiftKey: true, preventDefault() {} });
  assert.equal(findIndex, 0);
  findInput.listeners.keydown({ key: 'Enter', isComposing: true, preventDefault() {} });
  assert.equal(findIndex, 0, 'IME confirmation must not navigate');
  navigateFind(-1);
  assert.equal(findIndex, 2, 'previous wraps to hidden cue');
  assert.equal(findMatches[findIndex].id, 'b');
  query('中文');
  assert.equal(findIndex, 0, 'new query resets current occurrence');
  assert.equal(findMatches.length, 2);
  query('missing');
  assert.equal(findIndex, -1);
  assert.equal(findMatches.length, 0);
  query('<标签>');
  assert.equal(findMatches.length, 1);
  assert.equal(insertMarks('x <标签> & y', '<标签>'), 'x <mark>&lt;标签&gt;</mark> &amp; y');
  assert.equal(insertMarks('&', 'amp'), '&amp;', 'do not search HTML entities');
  assert.equal(textMatches('x .* .*', '.*').length, 2, 'literal regex characters');
  assert.equal(textMatches('a\\nb', '\\n').length, 1, 'multiline text');
  query('codex');
  repInput.value = '';
  replaceMatches(false);
  assert.equal(segments[0].text, ' codex & <标签> .*', 'only current occurrence deleted');
  assert.equal(findMatches.length, 2);
  assert.equal(findMatches[findIndex].id, 'a', 'advance to next remaining occurrence');
  restoreHistory(undoStack, redoStack, 'undo');
  assert.equal(JSON.stringify(segments), original);
  query('codex');
  repInput.value = '$&';
  replaceMatches(true);
  assert.equal(segments[0].text, '$& $& & <标签> .*');
  assert.equal(segments[1].text, '中文中文 $&', 'search and replacement include hidden cues');
  assert.equal(findMatches.length, 0);
  assert.equal(statusTxt.textContent, '已替换 3 处');
  restoreHistory(undoStack, redoStack, 'undo');
  query('codex');
  repInput.value = '';
  replaceMatches(true);
  assert.equal(findMatches.length, 0, 'empty replace-all deletes every occurrence');
  assert.equal(segments[0].text, '  & <标签> .*');
  console.log('PASS search navigation, literal matching, safe Enter, replacement, and undo');
`, context);
''', str(HTML)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
