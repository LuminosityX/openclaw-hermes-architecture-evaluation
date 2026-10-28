"""Deterministic local Responses-API fixture provider for Codex mechanism tests.

Implements the minimal wire contract the pinned Codex client exercises for a
custom `model_providers` entry with `wire_api = "responses"` (chat wire API was
removed upstream): POST {base_url}/responses returning an SSE stream built from
`response.created`, `response.output_text.delta`, `response.output_item.done`
and `response.completed` events (see codex-api/src/sse/responses.rs at commit
6aaac694803004a63c6f393d153c96d22521a6b9). Every request is recorded in an
independent ledger with monotonic timestamps; scripted replies carry fixed
token usage so transport behaviour is testable without any real provider.

This fixture is a controlled deterministic stand-in: it validates protocol,
retry and persistence mechanics only. It is never evidence about model quality.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket


class ResponsesFixture:
    """Scripted OpenAI-Responses-compatible server with an independent ledger."""

    def __init__(self, bearer='fixture-key', model='fixture-model'):
        self.bearer = bearer
        self.model = model
        self.ledger = []            # independent request ledger: the product never owns it
        self.hold_event = threading.Event()   # when set, next request waits on release
        self.release = threading.Event()
        self.release.set()
        self.hold_mode = False
        self.reply_text = 'FIXTURE_FINAL_REPLY'
        self.fail_next_with = None  # e.g. (503, {'error': 'upstream'})
        self.usage = dict(input_tokens=101, output_tokens=7, total_tokens=108)
        self._sequence = 0
        self._lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *_args):
                pass

            def _bearer_ok(self):
                return self.headers.get('Authorization') == 'Bearer ' + owner.bearer

            def _record(self, kind, **fields):
                entry = dict(monotonic_ns=time.monotonic_ns(), kind=kind, **fields)
                with owner._lock:
                    owner.ledger.append(entry)
                return entry

            def do_GET(self):
                if self.path.rstrip('/').endswith('/models'):
                    self._record('models-list', path=self.path)
                    body = json.dumps({'data': [{'id': owner.model}]}).encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self._record('unexpected-get', path=self.path)
                self.send_response(404)
                self.send_header('Content-Length', '0')
                self.end_headers()

            def do_POST(self):
                try:
                    self._do_post()
                except (BrokenPipeError, ConnectionResetError):
                    self._record('client-disconnected', note='killed while holding or streaming')

            def _do_post(self):
                if not self.path.rstrip('/').endswith('/responses'):
                    self._record('unexpected-post', path=self.path)
                    self.send_response(404)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                if not self._bearer_ok():
                    self._record('response-request', authorized=False, status=401)
                    self.send_response(401)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 8 * 1024 * 1024:
                    self._record('response-request', status=413)
                    self.send_response(413)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                body = json.loads(self.rfile.read(size))
                with owner._lock:
                    owner._sequence += 1
                    sequence = owner._sequence
                self._record('response-request', authorized=True, sequence=sequence,
                             model=body.get('model'), stream=body.get('stream'),
                             input_items=len(body.get('input', [])) if isinstance(body.get('input'), list) else None,
                             tools=len(body.get('tools', [])) if isinstance(body.get('tools'), list) else None)
                if owner.hold_mode:
                    owner.hold_event.set()
                    if not owner.release.wait(timeout=120):
                        self._record('hold-timeout', sequence=sequence)
                failure = owner.fail_next_with
                if failure is not None:
                    owner.fail_next_with = None
                    status, payload = failure
                    self._record('response-failure', sequence=sequence, status=status)
                    body = json.dumps(payload).encode()
                    self.send_response(status)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self._stream_reply(sequence)

            def _stream_reply(self, sequence):
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Connection', 'close')
                self.end_headers()
                response_id = f'resp_fixture_{sequence}'
                item = {'type': 'message', 'id': f'item_{sequence}', 'role': 'assistant',
                        'content': [{'type': 'output_text', 'text': owner.reply_text}]}
                usage = dict(owner.usage)
                events = [
                    ('response.created', {'type': 'response.created', 'response': {'id': response_id}}),
                    # This parser treats output_item.done as item-add; a bare
                    # output_text.delta without its internal active-item tracking logs
                    # an error, and the item already carries the full output text.
                    ('response.output_item.done', {'type': 'response.output_item.done',
                     'output_index': 0, 'item': item}),
                    ('response.completed', {'type': 'response.completed', 'response': {
                        'id': response_id, 'output': [item], 'usage': usage}}),
                ]
                for kind, payload in events:
                    try:
                        self.wfile.write(f'event: {kind}\ndata: {json.dumps(payload)}\n\n'.encode())
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        self._record('client-disconnected', sequence=sequence, note='during stream')
                        return
                self._record('response-sent', sequence=sequence, response_id=response_id)

        self._server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self._server.server_address[1]
        self.base_url = f'http://127.0.0.1:{self.port}/v1'
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def close(self):
        self._server.shutdown()
        self._server.server_close()

    def requests(self):
        with self._lock:
            return list(self.ledger)
