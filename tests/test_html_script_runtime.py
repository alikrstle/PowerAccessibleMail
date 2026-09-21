"""Execute the generated script, not just string-match its event handlers."""
import json
import re
import shutil
import subprocess
import unittest
from types import SimpleNamespace

from accessible_mail.mail_page import MailPage


@unittest.skipUnless(shutil.which('node'), 'Node.js is required for JS runtime tests')
class HtmlScriptRuntimeTests(unittest.TestCase):
    def test_generated_handlers_execute_in_normal_and_expanded_views(self):
        for expanded in (False, True):
            with self.subTest(expanded=expanded):
                page = SimpleNamespace(theme='dark', _expanded_viewer=expanded,
                                       message_html_content=lambda text: text)
                document = MailPage.message_html(page, 'First paragraph\n\nSecond paragraph')
                script = re.search(r'<script>(.*?)</script>', document, re.S).group(1)
                harness = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const handlers = {};
const commands = [];
const preview = {style: {}, textContent: ''};
const window = {
  pamBridge: {postMessage: command => commands.push(command)},
  addEventListener: (name, fn) => { handlers['window:' + name] = fn; },
  setTimeout: () => {}, location: {},
  getSelection: () => ({focusNode: {nodeType: 3, nodeValue: 'First\nSecond'}, focusOffset: 7})
};
const document = {
  addEventListener: (name, fn) => { handlers['document:' + name] = fn; },
  getElementById: () => preview
};
vm.runInNewContext(SCRIPT, {window, document});
function key(code, extras = {}) {
  handlers['window:keydown']({code, key: code, keyCode: 0,
    preventDefault() {}, stopPropagation() {}, ...extras});
}
key('Escape');
key('Enter', {ctrlKey: true});
key('KeyC', {ctrlKey: true});
key('F10', {shiftKey: true});
handlers['document:contextmenu']({preventDefault() {}, stopPropagation() {}});
assert.deepEqual(commands, ['focus-list', 'toggle-items', 'copy-message',
  'context-menu:keyboard', 'context-menu:pointer']);
handlers['document:selectionchange']();
assert.equal(preview.textContent, 'Second');
'''
                result = subprocess.run(
                    [shutil.which('node'), '-e', 'const SCRIPT = ' + json.dumps(script) + ';' + harness],
                    capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
