"""Trusted standard Hermes native session client; no substitute owner or AIAgent.
Keeps a normal client attached and drains native events without issuing model continuations.
"""
import asyncio, json, sys, time, uuid
from pathlib import Path
from hermes_constants import get_hermes_home
from hermes_cli.gateway_runtime import discover_gateway_endpoint, attachable
from hermes_cli.gateway_client import connect_gateway


async def main():
    until = asyncio.get_running_loop().time() + 35
    discovery = discover_gateway_endpoint(get_hermes_home())
    while discovery.state == 'starting' and asyncio.get_running_loop().time() < until:
        await asyncio.sleep(.2)
        discovery = discover_gateway_endpoint(get_hermes_home())
    if not attachable(discovery):
        raise RuntimeError('Existing native owner is not attachable: ' + str(discovery))
    async with connect_gateway(endpoint=discovery.endpoint) as client:
        description = await client.rpc('runtime.describe')
        if 'cli' not in description.get('session_create', {}).get('sources', []):
            raise RuntimeError('Native CLI session source unavailable')
        created = await client.rpc('session.create', request_id=uuid.uuid4().hex, source='cli',
                                   provider='deepseek', model='deepseek-flash', reasoning='high',
                                   cwd='/workspace', toolsets=['terminal', 'delegation'], yolo=True,
                                   accept_hooks=True)
        sid = created['stored_session_id']
        receipt = await client.rpc('prompt.submit', session_id=sid, input_id=uuid.uuid4().hex, text=sys.argv[1])
        record = dict(native_session_id=sid, creation=created, admission=receipt,
                      entry='public native session.create + prompt.submit; standard CLI source',
                      coordinator_model_continuations=0)
        Path('/state/native-parent-admission.json').write_text(json.dumps(record, ensure_ascii=False))
        print(json.dumps(record, ensure_ascii=False), flush=True)
        until = asyncio.get_running_loop().time() + 120
        while asyncio.get_running_loop().time() < until:
            try:
                event = await asyncio.wait_for(client.events.get(), .5)
            except TimeoutError:
                continue
            if isinstance(event, Exception):
                print(json.dumps({'native_client_closed': type(event).__name__}), flush=True)
                break
            with Path('/state/native-parent-events.jsonl').open('a') as output:
                output.write(json.dumps(dict(observed_at_ns=time.monotonic_ns(), event=event), ensure_ascii=False) + '\n')
            if 'PARENT_FINISHED_' in json.dumps(event, ensure_ascii=False):
                break


asyncio.run(main())
