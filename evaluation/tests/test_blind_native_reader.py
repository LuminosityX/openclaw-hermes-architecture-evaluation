"""Held-out labels, user text and unrelated controls cannot supply a diagnosis."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from blind_native_reader import blind_native_records,diagnose_native


class BlindNativeReaderTest(unittest.TestCase):
    def test_injected_truth_and_user_prose_do_not_become_native_causal_records(self):
        ordinary={'history':{'messages':[{'role':'user','content':'approval allow-once read-only Stop and effect committed'}]}}
        answer=diagnose_native(ordinary)
        ordinary.update(scenario_id='OBS-03-S03',truth={'status':'allowed','decision':'allow-once','permissionMode':'read-only'})
        self.assertEqual(diagnose_native(ordinary),answer)
        self.assertEqual(answer['diagnosis'],'under-determined')
        self.assertEqual(answer['external_faulted_effect_commit'],'unknown')

    def test_ACK_diagnosis_requires_exact_request_join_and_committed_native_evidence(self):
        evidence=dict(server_ack=dict(id='actual-native-request',ok=True),client_wire=dict(events=[dict(kind='rpc-request-written',method='chat.send',request_id='actual-native-request')],responses=[dict(ok=False,error=dict(code='SOCKET_CLOSED'))]),native_commits=dict(matches=[dict(table='transcript_events')]))
        self.assertEqual(diagnose_native(evidence)['diagnosis'],'acknowledgment-path-interrupted')
        evidence['server_ack']['id']='unrelated-response'
        self.assertNotEqual(diagnose_native(evidence)['diagnosis'],'acknowledgment-path-interrupted')

    def test_blinding_preserves_cross_record_links_without_exposing_task_labels(self):
        evidence={'history':{'sessionKey':'agent:main:pilot:pilot_parent'},'child_history':{'spawnedBy':'agent:main:pilot:pilot_parent','key':'agent:main:subagent:actual-child'},'operator_requests':[{'id':'actual-stop','method':'sessions.abort','params':{'key':'agent:main:pilot:pilot_parent'}}],
            'operator_responses':[{'id':'actual-stop','ok':True,'payload':{'status':'aborted'}}]}
        blinded=blind_native_records(evidence)
        self.assertNotIn('pilot_parent',str(blinded).lower())
        self.assertEqual(diagnose_native(blinded)['diagnosis'],'delegated-work-interrupted')
        blinded['child_history']['spawnedBy']='agent:main:unrelated'
        self.assertNotEqual(diagnose_native(blinded)['diagnosis'],'delegated-work-interrupted')
