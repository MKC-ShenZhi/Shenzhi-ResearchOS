"""Model sidecar framing, validation and failure preservation."""
import json
import unittest

from agent_app.execution.message_stream import MessageStream
from agent_app.execution.model_output import ModelOutput, MAX_REFERENCE_CHARS


def output(body, records):
    return body + '\n<references_json>\n' + json.dumps(records, ensure_ascii=False) + '\n</references_json>'


class ModelOutputTests(unittest.TestCase):
    def test_every_character_boundary_hides_json_and_keeps_markdown(self):
        body = '# 中文\n\n正文 [[cite:r1]]。'
        records = [{'id': 'r1', 'type': 'paper', 'title': 'Paper'}]
        text = output(body, records)
        for boundary in range(len(text) + 1):
            parser = ModelOutput()
            visible = parser.append(text[:boundary]) + parser.append(text[boundary:])
            tail, references, errors = parser.finish()
            self.assertEqual(visible + tail, body + '\n')
            self.assertEqual(references['r1'].title, 'Paper')
            self.assertEqual(errors, [])

    def test_character_stream_code_examples_and_json_string_delimiters(self):
        body = '```text\n<references_json>\n[]\n</references_json>\n```\n\n正文'
        text = output(body, [{'id': 'r', 'type': 'paper', 'title': 'literal </references_json> in title'}])
        parser = ModelOutput()
        visible = ''.join(parser.append(character) for character in text)
        tail, references, errors = parser.finish()
        self.assertEqual(visible + tail, body + '\n')
        self.assertEqual(references['r'].title, 'literal </references_json> in title')
        self.assertEqual(errors, [])

    def test_invalid_truncated_and_oversized_json_never_enters_body(self):
        for sidecar in ('{bad}</references_json>', '[', '[]', '[]</references_json>trailing',
                        '[{"id":"r","id":"other"}]</references_json>', 'x' * (MAX_REFERENCE_CHARS + 1)):
            parser = ModelOutput()
            self.assertEqual(parser.append('保留正文\n<references_json>' + sidecar), '保留正文\n')
            tail, references, errors = parser.finish()
            self.assertEqual(tail, '')
            self.assertEqual(references, {})
            self.assertTrue(errors)

    def test_invalid_entries_and_conflicting_keys_do_not_discard_other_sources(self):
        parser = ModelOutput()
        parser.append(output('', [
            {'id': 'good', 'type': 'paper', 'title': 'Good'},
            {'id': 'bad', 'type': 'paper', 'title': 'Bad', 'year': '2025'},
            {'id': 'same', 'type': 'paper', 'title': 'One'},
            {'id': 'same', 'type': 'paper', 'title': 'Another'},
        ]))
        _, refs, errors = parser.finish()
        self.assertEqual(list(refs), ['good'])
        self.assertIn('invalid_reference', errors)
        self.assertIn('conflicting_reference_key', errors)

    def test_first_citation_order_unused_sources_and_system_ids(self):
        stream = MessageStream(lambda *_: None, model='fake')
        stream.append(output('先 B [[cite:b]]，再 A [[cite:a]]，再 B [[cite:b]]', [
            {'id': 'a', 'type': 'paper', 'title': 'A'},
            {'id': 'unused', 'type': 'paper', 'title': 'Not cited'},
            {'id': 'b', 'type': 'paper', 'title': 'B'},
        ]))
        message = stream.finish('done', duration_ms=1)
        self.assertEqual([ref.title for ref in message.references], ['B', 'A'])
        self.assertTrue(all(ref.id.startswith('ref_') for ref in message.references))
        self.assertEqual(message.blocks[0].content.count(f'[[cite:{message.references[0].id}]]'), 2)

    def test_missing_json_and_failed_json_preserve_text_and_seal_valid_message(self):
        for suffix in ('', '\n<references_json>[', '\n<references_json>{bad}</references_json>'):
            stream = MessageStream(lambda *_: None, model='fake')
            stream.append('有效内容 [[cite:unresolved]]' + suffix)
            message = stream.finish('stopped', duration_ms=1)
            self.assertIn('有效内容 [引用不可用]', message.blocks[0].content)
            self.assertNotIn('references_json', message.blocks[0].content)
            self.assertEqual(message.references, [])

    def test_repeated_source_across_responses_deduplicates_and_preserves_id(self):
        stream = MessageStream(lambda *_: None, model='fake')
        for key in ('first', 'second'):
            stream.begin_response()
            stream.append(output(f'正文 [[cite:{key}]]', [
                {'id': key, 'type': 'paper', 'title': 'Same', 'doi': '10.1/same'},
            ]))
            stream.end_block()
        message = stream.finish('done', duration_ms=1)
        self.assertEqual(len(message.references), 1)
        self.assertTrue(all(f'[[cite:{message.references[0].id}]]' in block.content for block in message.blocks))
