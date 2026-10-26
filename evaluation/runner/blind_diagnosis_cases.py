"""Fresh native faults, blinded product records and separately held causal truth."""
import hashlib
import json
from pathlib import Path

import admission_cases
from blind_native_reader import blind_native_records,diagnose_native
import cancellation_cases
import effect_recovery_cases
import privacy_cases
import revocation_cases

SCENARIOS={f'OBS-03-S{i:02}':mode for i,mode in enumerate(['lost-ack','parent-child','approval-race','external-effect'],1)}
EXPECTED={'lost-ack':'acknowledgment-path-interrupted','parent-child':'delegated-work-interrupted',
    'approval-race':'approval-revocation-window','external-effect':'external-tool-result-ambiguous'}


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario]
    if mode=='lost-ack':underlying=admission_cases.run_scenario(root,'REL-01-S02',unit)
    elif mode=='parent-child':underlying=cancellation_cases.run_scenario(root,'REL-05-S03',unit)
    elif mode=='approval-race':underlying=revocation_cases.run_scenario(root,'SEC-06-S01',unit)
    else:
        def capture(path,token):
            return [privacy_cases.history(path,'agent:main:pilot:'+(token+suffix).lower()) for suffix in ['_UNKEYED','_KEYED']]
        underlying=effect_recovery_cases.run_scenario(root,'REL-02-S02',unit,native_observer=capture)
    row=dict(scenario_id=scenario,unit=unit,native_invoked=underlying.get('native_invoked',False),fixture_validated=underlying.get('fixture_validated',False),underlying_native_experiment=underlying,
        owned_state_retained=underlying.get('owned_state_retained',False),resources=underlying.get('resources'))
    if underlying.get('state') not in {'pass','fail'} or not row['native_invoked'] or not row['fixture_validated']:
        row.update(state='harness-error',reason='Underlying known native fault remains invalid: '+underlying.get('reason','unknown')[:1700]);return row
    metadata=underlying.get('metadata',{});stop=underlying.get('native_operator_report',{});approval=underlying.get('native_approval_observer',{})
    evidence=dict(server_ack=metadata.get('native_ack',{}),client_wire=metadata.get('original_client_report',{}),
        history=underlying.get('native_history',{}),child_history=metadata.get('native_child_after_stop',{}),
        operator_requests=stop.get('requests',[])+([approval['revocation_request']] if approval.get('revocation_request') else []),
        operator_responses=stop.get('responses',[])+([approval['revocation']] if approval.get('revocation') else []),
        approval_history=approval.get('history',{}),policy_records=underlying.get('native_records',[]),
        external_histories=underlying.get('native_observer_export',[]),native_commits=metadata.get('committed_records_before_fault',{}))
    blinded=blind_native_records(evidence);diagnosis=diagnose_native(blinded)
    assertions=[dict(name='blind-consumer-identifies-the-held-out-fault-category',verdict='pass' if diagnosis['diagnosis']==EXPECTED[mode] else 'fail',evidence=['blinded-native-product-records','separately-held-actual-injection-truth']),
        dict(name='selected-native-records-let-this-consumer-reconstruct-the-fault-boundary',verdict='pass' if diagnosis['exact_boundary_reconstructed'] else 'fail',evidence=['native-request-run-session-and-policy-linkage']),
        dict(name='consumer-does-not-invent-external-effect-commit-certainty',verdict='pass' if diagnosis['external_faulted_effect_commit']=='unknown' and diagnosis['uncertainties'] else 'fail',evidence=['consumer-input-excludes-independent-effect-oracle'])]
    row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,diagnosis=diagnosis,
        blinded_input_sha256=hashlib.sha256(json.dumps(blinded,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        blinded_input_bytes=len(json.dumps(blinded).encode()),held_out_truth=dict(known_fault=mode,expected_category=EXPECTED[mode],native_intervention_valid=True),paid_model_calls=0,
        reader_source_sha256=hashlib.sha256(Path(__file__).with_name('blind_native_reader.py').read_bytes()).hexdigest(),
        scope='Fresh independently injected native faults. Only curated native product/client records reach the frozen reader, after synthetic task labels are replaced by stable opaque aliases. The original nested native record and code regenerate the exact blinded input; private fault/effect truth is used only afterward for scoring. A reader failure is not proof that every expert or tool would fail to diagnose the records.')
    return row
