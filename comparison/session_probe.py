#!/usr/bin/env python3
"""Hosted-only calibration of native session reconstruction with a synthetic model."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if os.environ.get('GITHUB_ACTIONS') != 'true':
    raise SystemExit('This probe runs only on a disposable GitHub-hosted runner')

runtime = Path(os.environ['COMPARISON_RUNTIME'])
out = Path(os.environ['COMPARISON_OUTPUT'])
out.mkdir(parents=True, exist_ok=True)
requests = []
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if not (self.path.endswith('/chat/completions') or self.path.endswith('/messages')):
            self.send_error(404)
            return
        requests.append(body)
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        if self.path.endswith('/messages'):
            events = [('message_start', {'type': 'message_start', 'message': {'id': 'synthetic', 'type': 'message', 'role': 'assistant', 'model': 'deepseek-flash', 'content': [], 'stop_reason': None, 'usage': {'input_tokens': 1, 'output_tokens': 0}}}), ('content_block_start', {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}}), ('content_block_delta', {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': 'SYNTHETIC_ACK'}}), ('content_block_stop', {'type': 'content_block_stop', 'index': 0}), ('message_delta', {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}, 'usage': {'output_tokens': 1}}), ('message_stop', {'type': 'message_stop'})]
            for name, event in events:
                self.wfile.write(('event: ' + name + '\ndata: ' + json.dumps(event) + '\n\n').encode())
            self.wfile.flush()
            return
        for delta, finish in [({'role': 'assistant', 'content': 'SYNTHETIC_ACK'}, None), ({}, 'stop')]:
            chunk = {'id': 'synthetic', 'object': 'chat.completion.chunk', 'created': int(time.time()),
                     'model': 'fixture-model', 'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]}
            self.wfile.write(('data: ' + json.dumps(chunk) + '\n\n').encode())
        self.wfile.write(b'data: [DONE]\n\n')
        self.wfile.flush()

server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{server.server_port}/v1'
report = {'kind': 'session-reconstruction', 'formal': os.environ.get('COMPARISON_FORMAL') == 'true',
          'unit': int(os.environ.get('COMPARISON_UNIT', '1')), 'products': {}}

def invoke(args, env, cwd):
    try:
        r = subprocess.run(args, env=env, cwd=cwd, text=True, capture_output=True, timeout=120)
        return {'exit_code': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr}
    except subprocess.TimeoutExpired:
        return {'exit_code': None, 'stdout': '', 'stderr': 'timeout'}

def summarize(product, first, second, start):
    relevant = requests[start:]
    matches = []
    for r in relevant:
        messages = json.dumps(r.get('messages', []), ensure_ascii=False)
        if 'CONTINUE_7345' in messages:
            matches.append({'prior_user': 'SESSION_MARKER_7345' in messages,
                            'prior_assistant': 'SYNTHETIC_ACK' in messages,
                            'new_user': True})
    result = {'first_exit': first['exit_code'], 'second_exit': second['exit_code'],
              'request_count': len(relevant), 'resume_requests': matches,
              'first_stderr_tail': first['stderr'][-2000:], 'second_stderr_tail': second['stderr'][-2000:]}
    result['valid'] = first['exit_code'] == 0 and second['exit_code'] == 0 and len(matches) == 1
    result['history_present'] = all(matches[0].values()) if result['valid'] else None
    report['products'][product] = result

try:
    with tempfile.TemporaryDirectory(prefix='comparison-', dir=os.environ['RUNNER_TEMP']) as tmp:
        root = Path(tmp)
        env = dict(os.environ, PATH=str(runtime / 'node_modules/.bin') + os.pathsep + os.environ['PATH'])
        dshhome = root / 'dsh'; dshhome.mkdir()
        dshenv = dict(env, DSH_HOME=str(dshhome), DEEPSEEK_BASE_URL=base, DEEPSEEK_API_KEY='synthetic-only')
        start = len(requests)
        first = invoke(['dsh', '--profile', 'headless', '--json', 'SESSION_MARKER_7345'], dshenv, root)
        sid = None
        for line in first['stdout'].splitlines():
            try:
                event = json.loads(line)
                if event.get('type') == 'session': sid = event.get('sessionId')
            except ValueError:
                continue
        second = invoke(['dsh', '--profile', 'headless', '--json', '--session-id', sid, 'CONTINUE_7345'], dshenv, root) if sid else {'exit_code': None, 'stdout': '', 'stderr': 'No session id emitted'}
        summarize('DSH', first, second, start)
        state = root / 'openclaw-state'; state.mkdir()
        workspace = root / 'workspace'; workspace.mkdir()
        config = root / 'openclaw.json'
        config.write_text(json.dumps({'gateway': {'mode': 'local', 'bind': 'loopback', 'auth': {'mode': 'token', 'token': 'synthetic-only'}},
            'models': {'providers': {'fixture': {'baseUrl': base, 'apiKey': 'synthetic-only', 'api': 'openai-completions', 'models': [{'id': 'fixture-model', 'name': 'fixture-model', 'reasoning': False, 'input': ['text'], 'contextWindow': 128000, 'maxTokens': 1024}]}}},
            'agents': {'defaults': {'workspace': str(workspace), 'model': {'primary': 'fixture/fixture-model'}, 'skipBootstrap': True, 'thinkingDefault': 'off'}}, 'cron': {'enabled': False}}))
        ocenv = dict(env, OPENCLAW_STATE_DIR=str(state), OPENCLAW_CONFIG_PATH=str(config))
        sid = '5c1e6f80-79f2-4eb9-b59a-100000000001'
        start = len(requests)
        cmd = ['openclaw', 'agent', '--local', '--session-id', sid, '--json']
        first = invoke(cmd + ['--message', 'SESSION_MARKER_7345'], ocenv, workspace)
        second = invoke(cmd + ['--message', 'CONTINUE_7345'], ocenv, workspace)
        summarize('OpenClaw', first, second, start)
finally:
    server.shutdown(); server.server_close()
    (out / 'session-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(report, ensure_ascii=False, indent=2))
if not all(x['valid'] and x['history_present'] for x in report['products'].values()):
    raise SystemExit('Calibration failed or incomplete; inspect retained evidence')
