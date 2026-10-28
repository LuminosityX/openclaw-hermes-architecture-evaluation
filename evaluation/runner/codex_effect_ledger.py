"""Independent external-effect ledger for Codex side-effect experiments.

A tiny loopback HTTP service the sandboxed shell tool talks to. It owns the
ground truth: every raw attempt is counted, commits are deduplicated by an
explicit idempotency key, rejections are recorded, and a response can be held
or dropped after commit. The product under test never owns this ledger.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


class EffectLedger:
    def __init__(self):
        self.events = []           # monotonic, independently timestamped
        self._lock = threading.Lock()
        self.hold_seconds = 0.0    # delay after commit before responding
        self.drop_after_commit = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *_args):
                pass

            def _send(self, status, payload):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                query = parse_qs(urlsplit(self.path).query)
                if urlsplit(self.path).path.rstrip('/') == '/count':
                    token = (query.get('token') or [''])[0]
                    self._send(200, owner.counts(token))
                    return
                self._send(404, {'error': 'unknown-path'})

            def do_POST(self):
                if self.path.rstrip('/') != '/effect':
                    self._send(404, {'error': 'unknown-path'})
                    return
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 65536:
                    self._send(413, {'error': 'bound'})
                    return
                body = json.loads(self.rfile.read(size))
                token, key = body.get('token', ''), body.get('key', '')
                if not token or not key:
                    self._send(400, {'error': 'token-and-key-required'})
                    return
                if body.get('kind') == 'reject':
                    owner.record('rejected', token=token, key=key)
                    self._send(500, {'error': 'effect-rejected-by-service'})
                    return
                owner.record('raw-attempt', token=token, key=key)
                with owner._lock:
                    committed = [e for e in owner.events
                                 if e['kind'] == 'committed' and e['token'] == token]
                    already = any(e['key'] == key for e in committed)
                    if not already:
                        owner.events.append(dict(
                            monotonic_ns=time.monotonic_ns(), kind='committed',
                            token=token, key=key))
                    committed_count = len([e for e in owner.events
                                           if e['kind'] == 'committed' and e['token'] == token])
                if owner.drop_after_commit:
                    self.close_connection = True
                    try:
                        self.connection.close()
                    except OSError:
                        pass
                    return
                if owner.hold_seconds > 0:
                    time.sleep(owner.hold_seconds)
                self._send(200, {'accepted': not already, 'committed_count': committed_count,
                                 'idempotent_replay': already})

        self._server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def record(self, kind, **fields):
        with self._lock:
            self.events.append(dict(monotonic_ns=time.monotonic_ns(), kind=kind, **fields))

    def counts(self, token):
        with self._lock:
            events = [e for e in self.events if e.get('token') == token]
        return dict(raw_attempts=sum(1 for e in events if e['kind'] == 'raw-attempt'),
                    committed=sum(1 for e in events if e['kind'] == 'committed'),
                    rejected=sum(1 for e in events if e['kind'] == 'rejected'))

    def committed_keys(self, token):
        with self._lock:
            return [e['key'] for e in self.events
                    if e['kind'] == 'committed' and e['token'] == token]

    def start(self):
        self._thread.start()
        return self

    def close(self):
        self._server.shutdown()
        self._server.server_close()
