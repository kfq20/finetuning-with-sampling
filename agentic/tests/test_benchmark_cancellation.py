"""Real local sockets: cancellation before headers and during SSE, no model calls."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from append_rewrite.terminus.benchmark_llm import split_thinking, THINKING_SAMPLING
from append_rewrite.terminus.native_stream import NativeStreamClient


class AsyncCancellation(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.requests = []
        self.closed = asyncio.Event()
        self.received = asyncio.Event()
        self.mode = 'partial'
        self.handlers = set()
        self.server = await asyncio.start_server(self.handle, '127.0.0.1', 0)
        self.origin = 'http://127.0.0.1:' + str(self.server.sockets[0].getsockname()[1])
        cfg = self.root / 'private.json'
        cfg.write_text(json.dumps({'base_url': self.origin,
            'native_endpoint': self.origin + '/generate', 'model_id': 'fixture',
            'api_key': 'local', 'context_limit': 128, 'scoped_abort': True}))
        cfg.chmod(0o600)
        self.client = NativeStreamClient(cfg)
        self.tokenizer = SimpleNamespace(encode=lambda *a, **k: [1, 2, 3])

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()
        for task in list(self.handlers):
            task.cancel()
        await asyncio.gather(*self.handlers, return_exceptions=True)
        self.tmp.cleanup()

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.handlers.add(task)
        try:
            raw = await reader.readuntil(b'\r\n\r\n')
            lines = raw.decode().split('\r\n')
            size = int(next(v.split(':', 1)[1] for v in lines
                            if v.lower().startswith('content-length:')))
            body = json.loads(await reader.readexactly(size))
            path = lines[0].split()[1]
            self.requests.append((path, body))
            if path == '/generate':
                self.received.set()
            if path == '/abort_request':
                writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n')
                await writer.drain()
                return
            if self.mode == 'before-headers':
                await reader.read()
                self.closed.set()
                return
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\n\r\n')
            value = {'text': 'partial', 'meta_info': {'id': body['rid'],
                'prompt_tokens': 3, 'completion_tokens': 2, 'finish_reason': None}}
            if self.mode == 'normal':
                value['text'] = 'done'
                value['meta_info']['finish_reason'] = {'type': 'stop'}
            writer.write(('data: ' + json.dumps(value) + '\n\n').encode())
            await writer.drain()
            if self.mode != 'normal':
                await reader.read()
                self.closed.set()
        finally:
            writer.close()
            await writer.wait_closed()
            self.handlers.discard(task)

    async def generate(self):
        return await self.client.generate_async('prompt', self.tokenizer,
            journal=self.root / 'turn', sampling_params=THINKING_SAMPLING)

    async def test_cancel_during_sse_closes_socket_and_aborts_only_owned_rid(self):
        task = asyncio.create_task(self.generate())
        await asyncio.wait_for(self.received.wait(), 2)
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(task, 0.05)
        await asyncio.wait_for(self.closed.wait(), 1)
        record = json.loads((self.root / 'turn/cleanup.json').read_text())
        self.assertTrue(record['socket_closed'])
        self.assertTrue(record['abort_acknowledged'])
        self.assertTrue(record['cancelled'])
        self.assertEqual([r[0] for r in self.requests], ['/generate', '/abort_request'])
        self.assertEqual(self.requests[1][1],
                         {'rid': self.requests[0][1]['rid'], 'abort_all': False})
        await asyncio.sleep(0.05)
        self.assertFalse((self.root / 'turn/response.json').exists())

    async def test_cancel_before_headers_still_closes_and_aborts(self):
        self.mode = 'before-headers'
        await self.test_cancel_during_sse_closes_socket_and_aborts_only_owned_rid()

    async def test_normal_stop_has_one_generation_and_no_abort(self):
        self.mode = 'normal'
        result = await self.generate()
        self.assertEqual(result['text'], 'done')
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0][1]['sampling_params']['top_k'], 20)
        self.assertFalse((self.root / 'turn/cleanup.json').exists())

    async def test_unavailable_abort_is_not_claimed_as_engine_cleanup(self):
        self.client.config['scoped_abort'] = False
        task = asyncio.create_task(self.generate())
        await asyncio.wait_for(self.received.wait(), 2)
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(task, 0.05)
        record = json.loads((self.root / 'turn/cleanup.json').read_text())
        self.assertFalse(record['abort_acknowledged'])
        self.assertTrue(record['socket_closed'])
        self.assertEqual(len(self.requests), 1)


class ThinkingProtocol(unittest.TestCase):
    def test_open_template_prefix_and_explicit_tags_separate_reasoning(self):
        for text in ('reasoning</think>\n\n{"commands":[]}',
                     '<think>reasoning</think>\n\n{"commands":[]}'):
            content, reasoning = split_thinking(text, True)
            self.assertEqual(reasoning, 'reasoning')
            self.assertEqual(content, '{"commands":[]}')

    def test_incomplete_thinking_is_never_executable(self):
        with self.assertRaises(ValueError):
            split_thinking('still thinking', True)
        with self.assertRaises(ValueError):
            split_thinking('reasoning</think>', True)

    def test_nonthinking_control_keeps_original_rejection(self):
        self.assertEqual(split_thinking('{"commands":[]}', False), ('{"commands":[]}', None))
        with self.assertRaises(ValueError):
            split_thinking('<think>hidden</think>action', False)

try:
    from harbor.llms.base import LLMResponse
    HARBOR = True
except ImportError:
    HARBOR = False


@unittest.skipUnless(HARBOR, 'Actual Harbor dependency required')
class BenchmarkHistory(unittest.IsolatedAsyncioTestCase):
    async def test_reasoning_is_retained_in_history_but_not_executable_content(self):
        from unittest.mock import AsyncMock, patch
        from append_rewrite.terminus.benchmark_llm import CancellableQwenLLM
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'private.json'
            config.write_text(json.dumps({'base_url': 'http://127.0.0.1',
                'native_endpoint': 'http://127.0.0.1/generate', 'model_id': 'fixture',
                'api_key': 'local', 'context_limit': 262144}))
            config.chmod(0o600)
            rendered = []
            tokenizer = SimpleNamespace(apply_chat_template=lambda history, **kw:
                                        rendered.append(history) or 'wire')
            llm = CancellableQwenLLM(config, tokenizer, root / 'capture')
            async def generate(*args, journal, **kwargs):
                journal.mkdir()
                return {'text': 'private reasoning</think>\n\n{"commands":[]}',
                        'meta_info': {'id': 'fixture', 'prompt_tokens': 3,
                                      'completion_tokens': 5}}
            history = [{'role': 'user', 'content': 'initial'},
                       {'role': 'assistant', 'content': '{}',
                        'reasoning_content': 'previous private reasoning'}]
            with patch.object(llm.client, 'generate_async', side_effect=generate) as mocked:
                result = await llm.call('feedback', history)
            self.assertEqual(result.content, '{"commands":[]}')
            self.assertEqual(result.reasoning_content, 'private reasoning')
            self.assertEqual(rendered[0][1]['reasoning_content'], 'previous private reasoning')
            self.assertEqual(mocked.call_count, 1)
            self.assertEqual(mocked.call_args.kwargs['sampling_params'], THINKING_SAMPLING)

class BufferedCancellation(unittest.IsolatedAsyncioTestCase):
    async def test_already_buffered_sse_yields_to_deadline_cancellation(self):
        from unittest.mock import patch
        import httpx

        class Response:
            status_code = 200
            closed = False
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                self.closed = True
            def raise_for_status(self):
                pass
            async def aiter_lines(self):
                for i in range(100):
                    value = {'text': 'a' * (i + 1), 'meta_info': {
                        'id': 'fixture', 'prompt_tokens': 3, 'finish_reason': None}}
                    yield 'data: ' + json.dumps(value)
                    yield ''
                raise AssertionError('Buffered stream monopolized the event loop')

        response = Response()
        class Client:
            def __init__(self, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            def stream(self, *args, **kwargs):
                return response

        with tempfile.TemporaryDirectory() as folder:
            client = object.__new__(NativeStreamClient)
            client.config = {'model_id': 'fixture', 'context_limit': 128,
                             'api_key': 'local', 'native_endpoint': True}
            client.endpoint = 'http://127.0.0.1/generate'
            tokenizer = SimpleNamespace(encode=lambda *a, **k: [1, 2, 3])
            with patch.object(httpx, 'AsyncClient', Client):
                task = asyncio.create_task(client.generate_async('prompt', tokenizer,
                    journal=Path(folder) / 'turn', sampling_params=THINKING_SAMPLING))
                await asyncio.sleep(0)
                self.assertFalse(task.done())
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            self.assertTrue(response.closed)
            self.assertFalse((Path(folder) / 'turn/response.json').exists())

class IncrementalEvidence(unittest.TestCase):
    def test_delta_journal_reconstructs_all_original_native_events(self):
        from append_rewrite.terminus.native_stream import _parser
        values = [{'text': text, 'meta_info': {'id': 'fixture', 'prompt_tokens': 3,
            'finish_reason': {'type': 'stop'} if i == 2 else None}}
            for i, text in enumerate(['a', 'abc', 'abcdef'])]
        with tempfile.TemporaryDirectory() as folder:
            parser = _parser(folder, 3, delta_capture=True)
            next(parser)
            for value in values:
                parser.send('data: ' + json.dumps(value))
                try:
                    parser.send('')
                except StopIteration as stop:
                    result = stop.value
            rows = [json.loads(line) for line in
                    (Path(folder) / 'wire-deltas.jsonl').read_text().splitlines()]
            text = ''
            for expected, row in zip(values, rows):
                text += row.pop('text_delta')
                self.assertEqual(row.pop('capture_encoding'), 'cumulative-text-delta.v1')
                row['text'] = text
                self.assertEqual(row, expected)
            self.assertEqual(result, values[-1])
            self.assertFalse((Path(folder) / 'wire.jsonl').exists())
