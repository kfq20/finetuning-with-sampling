import json
from types import SimpleNamespace
import unittest

from append_rewrite.terminus.export import export_row


class Template:
    identity = 'fixture'

    def __init__(self, *, alter_interior=False):
        self.raw = self
        self.alter_interior = alter_interior

    def encode(self, text, **kwargs):
        return SimpleNamespace(ids=[ord(c) for c in text],
                               offsets=[(i, i + 1) for i in range(len(text))])

    def apply_chat_template(self, history, *, add_generation_prompt, **kwargs):
        text = ''
        for m in history:
            content = m['content'].strip()
            if self.alter_interior and m['role'] == 'assistant':
                content = content.replace('  keep  ', 'keep')
            text += m['role'] + '\n' + content + '<|im_end|>'
        if add_generation_prompt:
            text += 'assistant\n'
        return text


class NativeExportTests(unittest.TestCase):
    def test_template_trim_preserves_observed_messages_and_interior_spaces(self):
        raw = '\n' + json.dumps({'analysis': '  keep  ', 'commands': [],
                                  'task_complete': True}) + ' \n'
        history = [{'role': 'user', 'content': 'observation'},
                   {'role': 'assistant', 'content': raw}]
        row = export_row(history, Template(), provenance={})
        self.assertEqual(row['messages'], history)
        self.assertEqual(row['assistant_template_edge_trimmed_messages'], [1])
        supervised = ''.join(chr(t) for t, mask in zip(
            row['input_ids'], row['assistant_loss_mask']) if mask)
        self.assertEqual(supervised, raw.strip() + '<|im_end|>')
        self.assertIn('  keep  ', supervised)

    def test_already_matching_rows_keep_their_schema(self):
        raw = json.dumps({'commands': [], 'task_complete': True})
        row = export_row([{'role': 'user', 'content': 'task'},
                          {'role': 'assistant', 'content': raw}], Template(), provenance={})
        self.assertNotIn('assistant_template_edge_trimmed_messages', row)

    def test_other_template_differences_still_reject(self):
        raw = json.dumps({'analysis': '  keep  ', 'commands': []})
        with self.assertRaisesRegex(ValueError, 'full/incremental'):
            export_row([{'role': 'user', 'content': 'task'},
                        {'role': 'assistant', 'content': raw}],
                       Template(alter_interior=True), provenance={})
