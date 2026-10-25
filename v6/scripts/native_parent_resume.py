"""Standard public native parent reattachment/unknown-confirmation/continuation.
The controller must independently verify the completed synthetic child first.
These operator steps are recorded separately and never called automatic recovery.
"""
import asyncio, json, sys, time, uuid
from pathlib import Path
from hermes_constants import get_hermes_home
from hermes_cli.gateway_runtime import discover_gateway_endpoint, attachable
from hermes_cli.gateway_client import connect_gateway


async def main():
    sid, child_sid, token = sys.argv[1:4]
    if sys.argv[4:] != ['operator-verified-completed-child']:
        raise RuntimeError('Independent child completion and old-owner exit verification required')
    discovery = discover_gateway_endpoint(get_hermes_home())
    until = asyncio.get_running_loop().time() + 35
    while discovery.state == 'starting' and asyncio.get_running_loop().time() < until:
        await asyncio.sleep(.2)
        discovery = discover_gateway_endpoint(get_hermes_home())
    if not attachable(discovery):
        raise RuntimeError('Existing canonical owner not attachable: ' + str(discovery))
    record = dict(native_session_id=sid, native_child_session_id=child_sid, actions=[], events=[],
                  independent_operator_verification=True, coordinator_child_result_injection=False)
    output = Path('/state/native-parent-standard-resume.json')

    def save():
        output.write_text(json.dumps(record, ensure_ascii=False, indent=2))

    async with connect_gateway(endpoint=discovery.endpoint) as client:
        snapshot = await client.rpc('session.resume', session_id=sid)
        record['resume_snapshot'] = snapshot
        record['actions'].append(dict(kind='client_reattach_resume', method='session.resume'))
        unknown = [x for x in snapshot.get('pending', []) if x.get('status') == 'unknown']
        for row in unknown:
            try:
                result = await client.rpc('prompt.resolve_unknown', session_id=sid,
                                          admission_id=row['admission_id'],
                                          execution_generation=row['execution_generation'])
                record['actions'].append(dict(kind='operator_confirm_interrupted',
                    method='prompt.resolve_unknown', admission_id=row['admission_id'],
                    execution_generation=row['execution_generation'], result=result))
            except Exception as error:
                record['actions'].append(dict(kind='unknown_confirmation_refused', error=str(error)))
        save()

        async def observe(seconds):
            deadline = asyncio.get_running_loop().time() + seconds
            while asyncio.get_running_loop().time() < deadline:
                try:
                    event = await asyncio.wait_for(client.events.get(), .5)
                except TimeoutError:
                    continue
                if isinstance(event, Exception):
                    record['client_error'] = str(event)
                    save()
                    return False
                record['events'].append(dict(observed_at_ns=time.monotonic_ns(), event=event))
                save()
                if token in json.dumps(event, ensure_ascii=False):
                    return True
            return False

        recovered = token in json.dumps(snapshot.get('messages', []), ensure_ascii=False)
        if not recovered:
            recovered = await observe(10)
        record['completed_after_reattach_or_confirmation'] = recovered
        if not recovered:
            try:
                result = await client.rpc('prompt.submit', session_id=sid, input_id=uuid.uuid4().hex,
                    text='Continue the existing parent task and consume its already completed child result. Do not launch or execute the child again.')
                record['actions'].append(dict(kind='explicit_parent_continuation', method='prompt.submit', result=result))
                recovered = await observe(25)
            except Exception as error:
                record['actions'].append(dict(kind='explicit_continuation_refused', error=str(error)))
        try:
            record['final_snapshot'] = await client.rpc('session.resume', session_id=sid)
            record['child_info'] = await client.rpc('session.info', session_id=child_sid)
        except Exception as error:
            record['readonly_inspection_error'] = str(error)
        record['parent_finished_event_observed'] = recovered
        save()
        print(json.dumps(record, ensure_ascii=False), flush=True)


asyncio.run(main())
