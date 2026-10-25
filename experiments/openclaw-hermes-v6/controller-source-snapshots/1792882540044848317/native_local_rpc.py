"""Trusted native Hermes operator client. Requires an already-running owner; never starts a substitute runtime."""
import asyncio,json,sys
from pathlib import Path
from hermes_constants import get_hermes_home
from hermes_cli.gateway_runtime import discover_gateway_endpoint,attachable
from hermes_cli.gateway_client import connect_gateway
async def main():
 discovery=discover_gateway_endpoint(get_hermes_home())
 deadline=asyncio.get_running_loop().time()+30
 while discovery.state=='starting' and asyncio.get_running_loop().time()<deadline:
  await asyncio.sleep(.2);discovery=discover_gateway_endpoint(get_hermes_home())
 if not attachable(discovery):raise RuntimeError('Existing native owner not attachable: '+str(discovery))
 commands=json.loads(sys.argv[1]);results=[]
 async with connect_gateway(endpoint=discovery.endpoint) as client:
  for command in commands:
   try:result=await client.rpc(command['method'],**command.get('params',{}));results.append({'method':command['method'],'result':result})
   except Exception as ex:results.append({'method':command['method'],'error':type(ex).__name__,'detail':str(ex)[:300]})
 print(json.dumps(results,ensure_ascii=False))
asyncio.run(main())
