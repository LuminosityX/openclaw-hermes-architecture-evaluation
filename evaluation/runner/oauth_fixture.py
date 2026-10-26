"""Owned authorization-code/PKCE and rotating-refresh provider for native MCP."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import io
import json
import threading
import time
from urllib.parse import parse_qs,urlencode,urlsplit
import uuid

from mcp_http_fixture import McpHTTPFixture

ISSUER='http://127.0.0.1:18089'
RESOURCE='http://127.0.0.1:18085/mcp'


def pkce(verifier):return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')


class OAuthPeer(McpHTTPFixture):
    def __init__(self,short_expiry=False,read_only=False):
        self.clients={};self.codes={};self.access={};self.refresh={};self.generation=0
        self.short_expiry=short_expiry;self.read_only=read_only;self.revoked=False
        super().__init__()
        self.authorization_server=ThreadingHTTPServer(('127.0.0.1',18089),self.authorization_handler());self.authorization_server.daemon_threads=True
        threading.Thread(target=self.authorization_server.serve_forever,daemon=True).start()

    def tokens(self,scope):
        access='SYNTHETIC_OAUTH_ACCESS_'+uuid.uuid4().hex;refresh='SYNTHETIC_OAUTH_REFRESH_'+uuid.uuid4().hex
        expires=3 if self.short_expiry else 300
        with self.lock:
            self.generation+=1;generation=self.generation
            self.access[access]=dict(generation=generation,expires_at=time.monotonic()+expires,scope=scope)
            self.refresh[refresh]=dict(generation=generation,scope=scope,valid=True)
        self.event('oauth-token-issued',generation=generation,expires_in=expires,scope=scope)
        return dict(access_token=access,refresh_token=refresh,token_type='Bearer',expires_in=expires,scope=scope)

    def authorization_handler(self):
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send(self,status,data):
                raw=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

            def do_GET(self):
                parsed=urlsplit(self.path)
                if parsed.path=='/.well-known/oauth-authorization-server':
                    return self.send(200,dict(issuer=ISSUER,authorization_endpoint=ISSUER+'/authorize',token_endpoint=ISSUER+'/token',registration_endpoint=ISSUER+'/register',
                        response_types_supported=['code'],grant_types_supported=['authorization_code','refresh_token'],code_challenge_methods_supported=['S256'],
                        token_endpoint_auth_methods_supported=['none'],scopes_supported=['mcp.read','mcp.write']))
                if parsed.path!='/authorize':return self.send(404,dict(error='not_found'))
                args={k:v[0] for k,v in parse_qs(parsed.query).items()};client=owner.clients.get(args.get('client_id'))
                redirect=urlsplit(args.get('redirect_uri',''))
                registered=[urlsplit(v) for v in (client or {}).get('redirect_uris',[])]
                valid_redirect=(redirect.scheme=='http' and redirect.hostname in {'127.0.0.1','localhost','::1'} and any((r.scheme,r.hostname,r.path)==(redirect.scheme,redirect.hostname,redirect.path) for r in registered))
                if not client or not valid_redirect or args.get('code_challenge_method')!='S256' or not args.get('code_challenge') or args.get('response_type')!='code':
                    owner.event('oauth-authorization-denied',registered_client=bool(client),valid_loopback_redirect=valid_redirect);return self.send(400,dict(error='invalid_request'))
                code=uuid.uuid4().hex;scope='mcp.read' if owner.read_only else 'mcp.read mcp.write'
                owner.codes[code]=dict(client_id=args['client_id'],redirect_uri=args['redirect_uri'],challenge=args['code_challenge'],scope=scope)
                owner.event('oauth-authorization-approved',scope=scope,pkce_method='S256',actor='owned-synthetic-evaluation-user')
                location=args['redirect_uri']+('&' if '?' in args['redirect_uri'] else '?')+urlencode(dict(code=code,state=args.get('state','')))
                self.send_response(302);self.send_header('Location',location);self.send_header('Content-Length','0');self.end_headers()

            def do_POST(self):
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=16384:return self.send(413,dict(error='request_bound'))
                raw=self.rfile.read(size)
                try:args=json.loads(raw) if 'json' in self.headers.get('Content-Type','') else {k:v[0] for k,v in parse_qs(raw.decode()).items()}
                except (ValueError,UnicodeError):return self.send(400,dict(error='invalid_request'))
                if not isinstance(args,dict):return self.send(400,dict(error='invalid_request'))
                if self.path=='/register':
                    redirects=args.get('redirect_uris',[])
                    if not redirects or any(urlsplit(r).hostname not in {'localhost','127.0.0.1','::1'} for r in redirects):return self.send(400,dict(error='invalid_redirect_uri'))
                    identifier='owned-client-'+str(len(owner.clients)+1);owner.clients[identifier]=dict(redirect_uris=redirects)
                    owner.event('oauth-client-registered',redirect_count=len(redirects))
                    return self.send(201,dict(client_id=identifier,redirect_uris=redirects,token_endpoint_auth_method='none',grant_types=['authorization_code','refresh_token'],response_types=['code']))
                if self.path!='/token':return self.send(404,dict(error='not_found'))
                if args.get('grant_type')=='authorization_code':
                    grant=owner.codes.pop(args.get('code'),None)
                    valid=bool(grant and grant['client_id']==args.get('client_id') and grant['redirect_uri']==args.get('redirect_uri') and grant['challenge']==pkce(args.get('code_verifier','')))
                    owner.event('oauth-pkce-token-exchange',accepted=valid)
                    if not valid:return self.send(400,dict(error='invalid_grant'))
                    return self.send(200,owner.tokens(grant['scope']))
                if args.get('grant_type')=='refresh_token':
                    with owner.lock:
                        grant=owner.refresh.get(args.get('refresh_token'));valid=bool(grant and grant['valid'] and not owner.revoked)
                        if valid:grant['valid']=False
                    owner.event('oauth-refresh-attempt',accepted=valid,old_generation=grant['generation'] if grant else None)
                    if not valid:return self.send(400,dict(error='invalid_grant'))
                    return self.send(200,owner.tokens(grant['scope']))
                return self.send(400,dict(error='unsupported_grant_type'))
        return Handler

    def handler(self):
        base=super().handler();owner=self
        class Handler(base):
            def challenge(self,scope=False):
                self.send_response(403 if scope else 401)
                value='Bearer resource_metadata="'+RESOURCE.replace('/mcp','/.well-known/oauth-protected-resource/mcp')+'"'
                if scope:value+=', error="insufficient_scope", scope="mcp.write"'
                self.send_header('WWW-Authenticate',value);self.send_header('Content-Length','0');self.end_headers()

            def do_GET(self):
                if self.path.startswith('/.well-known/oauth-protected-resource'):
                    return self.send(200,dict(resource=RESOURCE,authorization_servers=[ISSUER],scopes_supported=['mcp.read','mcp.write'],bearer_methods_supported=['header']))
                if self.path=='/mcp' and not self.headers.get('Authorization'):return self.challenge()
                return super().do_GET()

            def do_POST(self):
                header=self.headers.get('Authorization','');token=header.removeprefix('Bearer ');grant=owner.access.get(token)
                valid=bool(grant and not owner.revoked and grant['expires_at']>time.monotonic())
                if not valid:
                    self.rfile.read(int(self.headers.get('Content-Length','0')));owner.event('oauth-resource-denied',reason='revoked' if owner.revoked else 'missing-or-expired',static_header_used=header=='Bearer IGNORED_STATIC_HEADER');return self.challenge()
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=1024**2:return self.send(413)
                raw=self.rfile.read(size);body=json.loads(raw)
                if body.get('method')=='tools/call' and body.get('params',{}).get('arguments',{}).get('action')!='read' and 'mcp.write' not in grant['scope'].split():
                    owner.event('oauth-resource-denied',reason='insufficient_scope',generation=grant['generation']);return self.challenge(scope=True)
                owner.event('oauth-resource-authorized',method=body.get('method'),generation=grant['generation'],scope=grant['scope'])
                original=self.rfile;self.rfile=io.BytesIO(raw)
                try:return super().do_POST()
                finally:self.rfile=original
        return Handler

    def close(self):
        self.authorization_server.shutdown();self.authorization_server.server_close();super().close()
