import json,pathlib,subprocess,http.server,urllib.parse
ROOT=pathlib.Path(__file__).resolve().parents[1];r=ROOT/'runtime/extended-integration/browser';r.mkdir(parents=True,exist_ok=True)
chrome=pathlib.Path('/root/.cache/ms-playwright/chromium-1161/chrome-linux/chrome')
with (r/'chrome.log').open('a') as log:p=subprocess.Popen([str(chrome),'--headless','--no-sandbox','--disable-dev-shm-usage','--remote-debugging-port=40311',f'--user-data-dir={r}/profile','about:blank'],stdout=log,stderr=log,start_new_session=True)
(r/'chrome.pid').write_text(str(p.pid));events=ROOT/'raw/extended-integration/browser-events.jsonl'
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  query=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query);case=query.get('case',['unknown'])[0]
  if self.path.startswith('/save'):
   with events.open('a') as f:f.write(json.dumps(query)+'\n')
   body=b'{"ok":true}'
  else:body=f'''<html><title>Benchmark order form</title><label>Reference<input id="reference"></label><label>Quantity<input id="quantity" type="number"></label><button id="submit" onclick="fetch('/save?case={case}&reference='+encodeURIComponent(document.querySelector('#reference').value)+'&quantity='+document.querySelector('#quantity').value).then(()=>document.querySelector('#status').textContent='Saved')">Submit</button><p id="status">New</p></html>'''.encode()
  self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass
http.server.ThreadingHTTPServer(('127.0.0.1',40310),Handler).serve_forever()
