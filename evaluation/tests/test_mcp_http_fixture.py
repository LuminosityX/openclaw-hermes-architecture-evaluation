"""Real owned HTTP/SSE, generation expiry and cooperative cancellation controls."""
import concurrent.futures
import http.client
import json
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from mcp_http_fixture import McpHTTPFixture
import mcp_contract_cases


class McpHTTPFixtureTests(unittest.TestCase):
    def test_frozen_two_family_scope(self):
        plan=json.loads((Path(__file__).resolve().parents[1]/'campaigns/full-20261026-batched/plan.json').read_text())
        expected={s['id'] for c in plan['cases'] if c['id'] in mcp_contract_cases.FAMILIES for s in c['scenarios']}
        self.assertEqual(expected,set(mcp_contract_cases.SCENARIOS))
        self.assertEqual(len(expected),8)

    def test_streamable_http_content_fidelity_and_real_expiry(self):
        fixture=McpHTTPFixture();connection=http.client.HTTPConnection('127.0.0.1',18085,timeout=3)
        def rpc(body,session=None):
            headers={'Content-Type':'application/json'}
            if session:headers['Mcp-Session-Id']=session
            connection.request('POST','/mcp',json.dumps(body),headers)
            response=connection.getresponse();raw=response.read()
            return response.status,json.loads(raw) if raw else None,response.getheader('Mcp-Session-Id')
        try:
            status,result,session=rpc(dict(jsonrpc='2.0',id=1,method='initialize',params=dict(protocolVersion='2025-03-26')))
            self.assertEqual(status,200);self.assertTrue(session)
            self.assertEqual(result['result']['protocolVersion'],'2025-03-26')
            for index,format in enumerate(['text','structured','resource','unicode','large'],2):
                token='PILOT_MCP_HTTP_'+format.upper();fixture.register(token,format=format)
                status,result,_=rpc(dict(jsonrpc='2.0',id=index,method='tools/call',params=dict(name='eval_probe',arguments=dict(token=token,unicode='π中文🙂'))),session)
                self.assertEqual(status,200);self.assertEqual(fixture.receipts[token],1)
                text=json.dumps(result,ensure_ascii=False)
                if format=='structured':self.assertEqual(result['result']['structuredContent']['marker'],'STRUCTURED_ONLY_'+token)
                if format=='resource':self.assertIn('eval-fixture://owned/'+token,text)
                if format=='unicode':self.assertIn('π_中文_🙂',text)
                if format=='large':self.assertIn('q'*(32*1024),text)
            fixture.expire()
            status,_,_=rpc(dict(jsonrpc='2.0',id=20,method='tools/list'),session)
            self.assertEqual(status,404)
        finally:connection.close();fixture.close()

    def test_cancelled_cooperative_call_never_commits(self):
        fixture=McpHTTPFixture();session=fixture.session();token='PILOT_COOPERATIVE_CANCEL'
        fixture.register(token,gate=True);fixture.release.clear()
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(fixture.response,dict(id=3,method='tools/call',params=dict(arguments=dict(token=token))),session)
                until=time.monotonic()+2
                while not fixture.calls and time.monotonic()<until:time.sleep(.01)
                fixture.response(dict(method='notifications/cancelled',params=dict(requestId=3)),session)
                fixture.release.set();result=future.result(timeout=3)
            self.assertEqual(result['error']['code'],-32800)
            self.assertFalse(fixture.receipts)
            self.assertTrue(any(e['kind']=='mcp-cancel-notification' and e['matched'] for e in fixture.events))
        finally:fixture.close()

    def test_legacy_sse_endpoint_and_jsonrpc_response_are_actual_streams(self):
        fixture=McpHTTPFixture('sse');stream=http.client.HTTPConnection('127.0.0.1',18085,timeout=3)
        sender=http.client.HTTPConnection('127.0.0.1',18085,timeout=3)
        try:
            stream.request('GET','/sse');response=stream.getresponse()
            self.assertEqual(response.status,200)
            self.assertEqual(response.readline(),b'event: endpoint\n')
            endpoint=response.readline().decode().strip().removeprefix('data: ');response.readline()
            sender.request('POST',endpoint,json.dumps(dict(jsonrpc='2.0',id=1,method='initialize',params=dict(protocolVersion='2024-11-05'))),{'Content-Type':'application/json'})
            sent=sender.getresponse();sent.read();self.assertEqual(sent.status,202)
            self.assertEqual(response.readline(),b'event: message\n')
            data=json.loads(response.readline().decode().removeprefix('data: '))
            self.assertEqual(data['result']['protocolVersion'],'2024-11-05')
        finally:sender.close();stream.close();fixture.close()


if __name__=='__main__':unittest.main()
