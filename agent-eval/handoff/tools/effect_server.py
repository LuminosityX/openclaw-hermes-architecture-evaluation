#!/usr/bin/env python3
"""Local fixture. Intentionally non-idempotent; never proxies real business actions."""
import argparse, json, os, socket, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

def make_server(state_dir, port=0):
    state=Path(state_dir)
    state.mkdir(parents=True,exist_ok=True)
    journal=state/"effects.jsonl"
    if journal.exists():raise FileExistsError("Refusing to reuse an existing journal")
    journal.touch(); lock=threading.Lock(); events=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,code,obj):
            raw=json.dumps(obj).encode();self.send_response(code);self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            if self.path=="/health":return self.reply(200,{"ok":True})
            if self.path=="/state":
                with lock:data={"count":len(events),"events":list(events)}
                return self.reply(200,data)
            self.reply(404,{"error":"unknown_path"})
        def do_POST(self):
            if self.path!="/effect":return self.reply(404,{"error":"unknown_path"})
            try:
                n=int(self.headers.get("Content-Length","0"))
                if not 0<n<=4096:raise ValueError("invalid length")
                payload=json.loads(self.rfile.read(n))
                operation_id=payload["operation_id"]
                if not isinstance(operation_id,str) or not 1<=len(operation_id)<=200:raise ValueError("invalid operation_id")
            except Exception:return self.reply(400,{"error":"invalid_payload"})
            with lock:
                event={"sequence":len(events)+1,"operation_id":operation_id,"time_ns":time.time_ns()}
                with journal.open("a") as f:f.write(json.dumps(event)+"\n");f.flush();os.fsync(f.fileno())
                events.append(event)
            if payload.get("drop_response") is True:
                self.close_connection=True
                try:self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:pass
                self.connection.close();return
            self.reply(200,event)
    return ThreadingHTTPServer(("127.0.0.1",port),Handler)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--state-dir",required=True);p.add_argument("--port",type=int,default=0);a=p.parse_args()
    server=make_server(a.state_dir,a.port)
    print(json.dumps({"base_url":f"http://127.0.0.1:{server.server_address[1]}","warning":"fixture_only_no_dedup"}),flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
