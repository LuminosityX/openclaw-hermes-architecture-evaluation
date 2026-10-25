import json,os,sys
KEYS=['OPENAI_API_KEY','ANTHROPIC_API_KEY','DEEPSEEK_API_KEY','AWS_SECRET_ACCESS_KEY','GITHUB_TOKEN','HF_TOKEN','DATABASE_URL']
for line in sys.stdin:
    try:
        q=json.loads(line);method=q.get('method');rid=q.get('id')
        if rid is None:continue
        if method=='initialize':result={'protocolVersion':q['params']['protocolVersion'],'capabilities':{'tools':{}},'serverInfo':{'name':'actual-nonfunctional-fixture','version':'1'}}
        elif method=='tools/list':result={'tools':[{'name':'inspect_canaries','description':'Report only synthetic benchmark canary visibility','inputSchema':{'type':'object','properties':{}}}]}
        elif method=='tools/call':result={'content':[{'type':'text','text':json.dumps({'canaries':{k:os.environ.get(k,'').startswith('bench-only-canary-')for k in KEYS},'pid':os.getpid()})}],'isError':False}
        else:result={}
        print(json.dumps({'jsonrpc':'2.0','id':rid,'result':result}),flush=True)
    except (ValueError,KeyError):continue
