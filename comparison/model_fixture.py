"""Comparison model fixture M (OpenAI Responses protocol), Codex track.

Implements the model-fixture contract of comparison/execution-protocol.md §3
for the Responses wire protocol the pinned Codex CLI uses:

* append-only synthetic ledger: every request stores ``unit_id``, monotonic
  timestamp, wall-clock UTC, protocol, request number, the full parsed input
  items, tool names plus a schema hash, the mode that applied, the response
  type, HTTP failures and socket closes;
* modes: ``ack``, ``503_once``, ``hold_before_response``,
  ``hold_after_tool_call``, ``large_context``, ``scripted_calls``;
* protocol-conformant SSE replies (created -> output_item.done -> completed)
  with consistent synthetic usage. Fixture usage is metadata, never billing.

The fixture signals ``request_received`` on every request so a controller can
verify ``fault_reached`` independently before injecting a fault. Responses are
deterministic; no real provider is ever contacted.
"""

import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODES = {'ack', '503_once', 'hold_before_response', 'hold_after_tool_call',
         'large_context', 'scripted_calls'}


class ModelFixture:
    """One per-unit loopback M instance with its own ledger."""

    def __init__(self, unit_id, ack_text=None, model='fixture-model',
                 bearer='fixture-key', hold_cap_seconds=180.0):
        assert isinstance(unit_id, str) and unit_id
        self.unit_id = unit_id
        self.ack_text = ack_text or f'ACK_{unit_id}'
        self.model = model
        self.bearer = bearer
        self.hold_cap_seconds = hold_cap_seconds
        self.mode = 'ack'
        self.script = []            # scripted_calls: [{'call': {...}} | {'reply': '...'}]
        self.large_bytes = 65536
        self.usage = dict(input_tokens=101, output_tokens=7, total_tokens=108)
        self.request_received = threading.Event()
        self.hold_release = threading.Event()
        self.hold_release.set()
        self.ledger = []
        self._lock = threading.Lock()
        self._request_number = 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *_args):
                pass

            def _close_only(self, status, note):
                body = json.dumps({'error': note}).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_GET(self):
                self._close_only(404, 'unknown-path')

            def do_POST(self):
                try:
                    self._do_post()
                except (BrokenPipeError, ConnectionResetError):
                    owner._record('socket-close', stage='post')

            def _do_post(self):
                if not self.path.rstrip('/').endswith('/responses'):
                    self._close_only(404, 'unknown-path')
                    return
                if self.headers.get('Authorization') != 'Bearer ' + owner.bearer:
                    owner._record('request', authorized=False,
                                  input_items=[], tool_names=[], tool_schema_sha256=None)
                    self._close_only(401, 'unauthorized')
                    return
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 16 * 1024 * 1024:
                    self._close_only(413, 'request-too-large')
                    return
                body = json.loads(self.rfile.read(size))
                with owner._lock:
                    owner._request_number += 1
                    number = owner._request_number
                inputs = body.get('input') if isinstance(body.get('input'), list) else []
                tools = body.get('tools') if isinstance(body.get('tools'), list) else []
                tool_names = [t.get('name') or t.get('type') for t in tools]
                schema_hash = hashlib.sha256(
                    json.dumps(tools, sort_keys=True).encode()).hexdigest()
                owner._record(
                    'request', request_number=number, authorized=True,
                    model=body.get('model'), stream=body.get('stream'),
                    input_items=inputs, input_count=len(inputs),
                    tool_names=tool_names, tool_schema_sha256=schema_hash,
                    mode=owner.mode,
                    input_contains_function_call_output=any(
                        isinstance(item, dict) and item.get('type') == 'function_call_output'
                        for item in inputs))
                owner.request_received.set()

                should_hold = (
                    owner.mode == 'hold_before_response'
                    or (owner.mode == 'hold_after_tool_call' and any(
                        isinstance(item, dict) and item.get('type') == 'function_call_output'
                        for item in inputs)))
                if should_hold:
                    if not owner.hold_release.wait(timeout=owner.hold_cap_seconds):
                        owner._record('hold-timeout', request_number=number)
                        self._close_only(504, 'hold-cap-reached')
                        return

                if owner.mode == '503_once':
                    owner.mode = 'ack'
                    owner._record('http-failure', request_number=number, status=503)
                    self._close_only(503, 'synthetic-upstream-unavailable')
                    return

                self._reply(number)

            def _reply(self, number):
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Connection', 'close')
                self.end_headers()
                response_id = f'resp_m_{number}'
                reply_text, call, response_type = owner._plan_response(number)
                if call is not None:
                    item = {'type': 'function_call', 'call_id': f'call_m_{number}',
                            'name': call['name'], 'arguments': json.dumps(call['arguments'])}
                elif response_type == 'large_context':
                    filler_unit = f'FIXTURE_LARGE_CONTEXT_{number}_'
                    filler = (filler_unit * (owner.large_bytes // len(filler_unit) + 2))
                    reply_text = filler[:owner.large_bytes]
                    item = {'type': 'message', 'id': f'item_m_{number}', 'role': 'assistant',
                            'content': [{'type': 'output_text', 'text': reply_text}]}
                else:
                    item = {'type': 'message', 'id': f'item_m_{number}', 'role': 'assistant',
                            'content': [{'type': 'output_text', 'text': reply_text}]}
                events = [
                    ('response.created', {'type': 'response.created',
                                          'response': {'id': response_id}}),
                    # The pinned Codex SSE parser treats output_item.done as the
                    # item-add; bare output_text.delta logs an error and the
                    # item already carries the full text.
                    ('response.output_item.done', {'type': 'response.output_item.done',
                                                    'output_index': 0, 'item': item}),
                    ('response.completed', {'type': 'response.completed', 'response': {
                        'id': response_id, 'output': [item],
                        'usage': dict(owner.usage)}}),
                ]
                for kind, payload in events:
                    try:
                        self.wfile.write(f'event: {kind}\ndata: {json.dumps(payload)}\n\n'.encode())
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        owner._record('socket-close', request_number=number, stage='stream')
                        return
                owner._record('response-sent', request_number=number,
                              response_id=response_id, response_type=response_type,
                              reply_text_head=reply_text[:80] if reply_text else None,
                              function_call=item['name'] if call is not None else None)

        self._server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self._server.server_address[1]
        self.base_url = f'http://127.0.0.1:{self.port}/v1'
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def _plan_response(self, number):
        """Returns (reply_text, call_or_None, response_type)."""
        if self.mode == 'scripted_calls' and self.script:
            step = self.script[min(number - 1, len(self.script) - 1)]
            if 'call' in step:
                return None, step['call'], 'function_call'
            return step.get('reply', self.ack_text), None, step.get('type', 'ack')
        if self.mode == 'large_context':
            return None, None, 'large_context'
        return self.ack_text, None, 'ack'

    def _record(self, kind, **fields):
        entry = dict(kind=kind, unit_id=self.unit_id,
                     monotonic_ns=time.monotonic_ns(),
                     wall_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                     protocol='responses', **fields)
        with self._lock:
            self.ledger.append(entry)

    def start(self):
        self._thread.start()
        return self

    def close(self):
        self._server.shutdown()
        self._server.server_close()

    def entries(self, kind=None):
        with self._lock:
            return [dict(e) for e in self.ledger if kind is None or e['kind'] == kind]

    def input_texts(self, request_number):
        """Every text fragment in one recorded request, for content verification."""
        for entry in self.entries('request'):
            if entry.get('request_number') == request_number:
                texts = []
                for item in entry.get('input_items', []):
                    if isinstance(item, dict):
                        for content in item.get('content', []) or []:
                            if isinstance(content, dict) and 'text' in content:
                                texts.append(content['text'])
                        if 'arguments' in item:
                            texts.append(item['arguments'])
                return texts
        return None
