"""Scope reconstruction is blind to scenario labels and cannot borrow wrong actors."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from authorization_observation_cases import reconstruct

class AuthorizationReconstructionTest(unittest.TestCase):
    def test_labels_and_expected_choice_text_cannot_create_a_native_grant(self):
        self.assertEqual(reconstruct({'prompt':'OBS-01-S01 single-use allow-once full persistent','expected':'session'})['authority_choice'],'unknown')
        record={'approval':{'status':'allowed','decision':'allow-once','resolvedBy':'native-operator'},'sessionKey':'agent:main:any-label'}
        result=reconstruct(record);record['sessionKey']='agent:main:OBS-01-S04_REVOKED'
        self.assertEqual(reconstruct(record)['authority_choice'],result['authority_choice'])
        self.assertTrue(result['actors'])
    def test_denial_actor_does_not_explain_who_granted_session_or_persistent_authority(self):
        denial={'status':'denied','decision':'deny','resolvedBy':'unrelated-denial-reviewer'}
        session=reconstruct({'current':{'permissionMode':'full'},'denial':denial})
        policy=reconstruct({'file':{'agents':{'main':{'allowlist':[{'pattern':'/owned/tool'}]}}},'denial':denial})
        self.assertEqual(session['authority_choice'],'session');self.assertFalse(session['actors'])
        self.assertEqual(policy['authority_choice'],'persistent');self.assertFalse(policy['actors'])
