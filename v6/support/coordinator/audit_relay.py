"""Real upstream API relay; no mock responses, golden data or prompt rewriting."""
import datetime as dt
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import socketserver
import ssl
import threading
import time
from urllib.parse import urlsplit

ROOT = Path('/root/Downloads/1023magnitude/agent_eval_handoff')
PROJECT = Path('/root/Documents/Codex/2026-10-24/agent-root-downloads-1023magnitude-agent-eval')
SECRET = PROJECT / 'work/runtime-secrets/deepseek.json'

def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def append(path, data):
    with path.open('a') as stream:
        stream.write(json.dumps(data, ensure_ascii=False) + '\n')

def balance(key):
    connection = http.client.HTTPSConnection('api.deepseek.com', timeout=20, context=ssl.create_default_context())
    try:
        connection.request('GET', '/user/balance', headers={'Authorization': 'Bearer ' + key})
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError('Balance HTTP ' + str(response.status))
        return json.loads(response.read())
    finally:
        connection.close()

class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

class Relay:
    def __init__(self, run, family, budget, inference_authorized=False):
        self.run, self.family, self.budget = Path(run), family, budget
        self.lock = threading.Lock()
        self.calls = 0
        self.inference_authorized = inference_authorized
        self.violations = []
        self.responses = []
        self.secret = json.loads(SECRET.read_text())['DEEPSEEK_API_KEY'] if family != 'codex' else None
        self.socket_dir = PROJECT / 'work/relay-sockets' / hashlib.sha256(str(run).encode()).hexdigest()[:12]
        self.socket_dir.mkdir(parents=True, exist_ok=True)
        self.socket = self.socket_dir / 'api.sock'
        self.socket.unlink(missing_ok=True)
        self.server = UnixServer(os.path.relpath(self.socket), self.handler())
        self.socket.chmod(0o600)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def handler(self):
        owner = self
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.forward()
            def do_POST(self):
                self.forward()
            def deny(self, reason, status=403):
                with owner.lock:
                    owner.violations.append(reason)
                    append(owner.run / 'api-audit.jsonl', {'at_utc': utc(), 'event': 'blocked_before_upstream', 'method': self.command, 'path': self.path, 'reason': reason})
                data = json.dumps({'error': {'message': reason, 'type': 'evaluation_policy'}}).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(data)
                self.close_connection = True
            def forward(self):
                started = time.monotonic()
                deepseek = owner.family != 'codex'
                prefix = '/ds' if deepseek else '/cx'
                if not self.path.startswith(prefix + '/'):
                    return self.deny('Endpoint outside family allowlist')
                path = self.path[len(prefix):]
                parsed = urlsplit(path)
                allowed_get = ['/models', '/v1/models', '/user/balance', '/api/v1/models', '/api/tags', '/api/version', '/props', '/v1/props', '/version'] if deepseek else ['/backend-api/codex/models', '/models']
                allowed_post = ['/chat/completions', '/v1/chat/completions', '/anthropic/v1/messages'] if deepseek else ['/backend-api/codex/responses', '/responses', '/backend-api/codex/responses/compact', '/responses/compact']
                if parsed.path not in (allowed_get if self.command == 'GET' else allowed_post):
                    return self.deny('API path outside inference/catalog allowlist: ' + parsed.path)
                length = int(self.headers.get('Content-Length', '0'))
                if length > 20_000_000:
                    return self.deny('Request exceeds audit bound', 413)
                body = self.rfile.read(length) if length else None
                if body and any(value and value.encode() in body for value in getattr(owner, 'prohibited_secret_literals', [])):
                    return self.deny('Protected service credential in inference body; upstream request refused')
                try:
                    data = json.loads(body) if body else {}
                except (ValueError, UnicodeDecodeError):
                    return self.deny('Non-JSON inference request refused', 400)
                inference = self.command == 'POST'
                if inference:
                    if not owner.inference_authorized:
                        return self.deny('No inference during free configuration preflight')
                    model = data.get('model')
                    required = 'deepseek-flash' if deepseek else 'gpt-6.1-sol'
                    if model != required:
                        return self.deny('Fixed model mismatch: ' + str(model))
                    title_system = data.get('system', '')
                    if isinstance(title_system, list):
                        title_system = '\n'.join(block.get('text','') for block in title_system if isinstance(block,dict))
                    native_title = (owner.family == 'dsh' and str(title_system).startswith('Create a concise title for an AI coding-assistant session') and not data.get('tools') and data.get('max_tokens') == 4096)
                    if deepseek and data.get('thinking', {}).get('type') == 'disabled' and not native_title:
                        return self.deny('Thinking unexpectedly disabled')
                    if deepseek and not native_title and (data.get('reasoning_effort') or data.get('output_config',{}).get('effort') or 'high') != 'high':
                        return self.deny('Main/child reasoning effort must remain high')
                    if not deepseek and data.get('reasoning', {}).get('effort') != 'medium':
                        return self.deny('Codex reasoning effort must remain medium')
                    if deepseek:
                        with owner.budget['lock']:
                            if owner.budget['spent'] + owner.budget['reserved'] + 5.1 > owner.budget['limit']:
                                return self.deny('Insufficient remaining authorized budget for worst-case request')
                            owner.budget['reserved'] += 5.1
                    with owner.lock:
                        owner.calls += 1
                        call = owner.calls
                    (owner.run / f'api-request-{call:03}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
                    append(owner.run / 'api-audit.jsonl', {'at_utc': utc(), 'event': 'request', 'call': call, 'path': path, 'model': model, 'reasoning': data.get('reasoning'), 'reasoning_effort': data.get('reasoning_effort'), 'output_config': data.get('output_config'), 'thinking': data.get('thinking'), 'native_auxiliary_effort_exception': 'DSH title generator: nonconfigurable minimum effort, same Flash model' if native_title else None, 'service_tier': data.get('service_tier', 'provider_default'), 'request_sha256': hashlib.sha256(body).hexdigest(), 'headers_recorded': False})
                else:
                    call = 0
                headers = {key: value for key, value in self.headers.items() if key.lower() not in ['host', 'connection', 'content-length', 'transfer-encoding', 'accept-encoding']}
                headers['Accept-Encoding'] = 'identity'
                if deepseek:
                    headers = {key: value for key, value in headers.items() if key.lower() not in ['authorization', 'x-api-key']}
                    if parsed.path.startswith('/anthropic/'):
                        headers.pop('Authorization', None)
                        headers.pop('authorization', None)
                        headers['x-api-key'] = owner.secret
                    else:
                        headers.pop('x-api-key', None)
                        headers['Authorization'] = 'Bearer ' + owner.secret
                connection = http.client.HTTPSConnection('api.deepseek.com' if deepseek else 'chatgpt.com', timeout=120, context=ssl.create_default_context())
                raw = bytearray()
                status = None
                failure = None
                try:
                    connection.request(self.command, path, body=body, headers=headers)
                    response = connection.getresponse()
                    status = response.status
                    self.send_response(status)
                    for key, value in response.getheaders():
                        if key.lower() not in ['transfer-encoding', 'connection', 'content-length', 'content-encoding']:
                            self.send_header(key, value)
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    while True:
                        chunk = response.read1(65536)
                        if not chunk:
                            break
                        raw.extend(chunk)
                        self.wfile.write(chunk)
                        self.wfile.flush()
                except Exception as exc:
                    failure = type(exc).__name__
                    if status is None:
                        self.send_error(502, 'Upstream transport failed')
                finally:
                    connection.close()
                    self.close_connection = True
                    if inference:
                        (owner.run / f'api-response-{call:03}.raw').write_bytes(raw)
                        usage, response_models = {}, []
                        candidates = []
                        try:
                            candidates.append(json.loads(raw))
                        except (ValueError, UnicodeDecodeError):
                            for line in raw.splitlines():
                                if line.startswith(b'data: '):
                                    try:
                                        candidates.append(json.loads(line[6:]))
                                    except ValueError:
                                        pass
                        for item in candidates:
                            for candidate in [item, item.get('message', {}), item.get('response', {})]:
                                if candidate.get('model'):
                                    response_models.append(candidate['model'])
                                if candidate.get('usage'):
                                    usage.update(candidate['usage'])
                        terminal_received = (b'data: [DONE]' in raw or any(item.get('type') in ['message_stop','response.completed'] for item in candidates))
                        partial_stream = not terminal_received and (bool(failure) or bool(data.get('stream')) and status is not None and 200 <= status < 300)
                        summary = {'at_utc': utc(), 'event': 'response', 'call': call, 'http_status': status, 'duration_seconds': round(time.monotonic() - started, 3), 'usage': usage, 'response_models': sorted(set(response_models)), 'transport_failure': failure}
                        summary['usage_completeness'] = 'partial_stream' if partial_stream else 'terminal_observed' if terminal_received else 'not_independently_confirmed'
                        if deepseek:
                            cached = usage.get('prompt_cache_hit_tokens', usage.get('cache_read_input_tokens', 0)) or 0
                            tokens_in = (usage.get('prompt_tokens') if 'prompt_tokens' in usage else
                                         (usage.get('input_tokens', 0) or 0) + cached + (usage.get('cache_creation_input_tokens', 0) or 0)) or 0
                            tokens_out = usage.get('completion_tokens', usage.get('output_tokens', 0)) or 0
                            # Saturday's published CNY off-peak rates. Account deltas are retained independently.
                            cost = (max(0, tokens_in - cached) + cached * 0.02 + tokens_out * 4) / 1_000_000
                            summary['estimated_cost_CNY'] = cost if usage else None
                            with owner.budget['lock']:
                                owner.budget['reserved'] -= 5.1
                                if usage:
                                    owner.budget['spent'] += cost
                                if partial_stream:
                                    owner.budget['reserved'] += 5.1
                                    summary['unresolved_cost_reservation_CNY'] = 5.1
                                elif usage or status is not None and 400 <= status < 500:
                                    pass
                                else:
                                    owner.budget['reserved'] += 5.1
                                    summary['unresolved_cost_reservation_CNY'] = 5.1
                        owner.responses.append(summary)
                        append(owner.run / 'api-audit.jsonl', summary)
        return Handler

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.socket.unlink(missing_ok=True)
