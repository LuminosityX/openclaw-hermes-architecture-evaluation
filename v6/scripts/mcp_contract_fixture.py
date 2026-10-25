"""Public MCP stdio fixture; synthetic values only. No external network or credentials."""
import json,os,sys,time
from pathlib import Path
UNICODE='Straße 中文 🧪 e\u0301'
LARGE='MCP_LARGE_BEGIN_'+('0123456789abcdef'*40000)+'_MCP_LARGE_END_中文'
TOOLS=[dict(name='env_probe',description='Return only two named synthetic environment variables',inputSchema={'type':'object','properties':{}},annotations={'readOnlyHint':True}),dict(name='unicode_echo',description='Return a Unicode string unchanged',inputSchema={'type':'object','properties':{'text':{'type':'string'}},'required':['text']},annotations={'readOnlyHint':True}),dict(name='schema_probe',description='Require count integer at least1',inputSchema={'type':'object','properties':{'count':{'type':'integer','minimum':1}},'required':['count']},annotations={'readOnlyHint':True}),dict(name='error_probe',description='Return a declared tool error',inputSchema={'type':'object','properties':{}},annotations={'readOnlyHint':True}),dict(name='large_probe',description='Return a large Unicode result',inputSchema={'type':'object','properties':{}},annotations={'readOnlyHint':True})]
def reply(request):
 method=request.get('method');params=request.get('params',{});result={}
 if method=='initialize':result={'protocolVersion':params.get('protocolVersion','2025-03-26'),'capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'contract-fixture','version':'1.0'}}
 elif method=='tools/list':result={'tools':TOOLS}
 elif method=='tools/call':
  name=params.get('name');args=params.get('arguments',{});error=False;structured=None
  if name=='env_probe':text=json.dumps({'private':os.environ.get('EVAL_PRIVATE_SECRET'),'approved':os.environ.get('APPROVED_MCP_TOKEN')})
  elif name=='unicode_echo':text=args['text'];structured={'echo':text,'metadata':{'language':'中文'}}
  elif name=='schema_probe':error=type(args.get('count')) is not int or args['count']<1;text='CONTROLLED_SCHEMA_ERROR' if error else 'SCHEMA_OK'
  elif name=='error_probe':error=True;text='CONTROLLED_MCP_ERROR'
  elif name=='large_probe':text=LARGE
  else:error=True;text='Unknown tool'
  result={'content':[{'type':'text','text':text}],'isError':error}
  if structured is not None:result['structuredContent']=structured
 elif method in ['ping','notifications/initialized']:result={}
 elif 'id' in request:return {'jsonrpc':'2.0','id':request['id'],'error':{'code':-32601,'message':'Method not found'}}
 if 'id' not in request:return None
 return {'jsonrpc':'2.0','id':request['id'],'result':result}
def main():
 Path('/workspace/mcp-native-env-received.json').write_text(json.dumps({'private':os.environ.get('EVAL_PRIVATE_SECRET'),'approved':os.environ.get('APPROVED_MCP_TOKEN')}))
 log=Path('/workspace/mcp-truth.jsonl')
 for line in sys.stdin:
  try:
   request=json.loads(line)
   with log.open('a') as f:f.write(json.dumps(dict(at_ns=time.monotonic_ns(),request=request),ensure_ascii=False)+'\n')
   response=reply(request)
   if response is not None:print(json.dumps(response,ensure_ascii=False),flush=True)
  except Exception as e:
   print(json.dumps({'jsonrpc':'2.0','id':request.get('id'),'error':{'code':-32603,'message':type(e).__name__}}),flush=True)
if __name__=='__main__':main()
