"""Committed custody is independently visible; an uncommitted row is not."""
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from admission_cases import admitted_run,committed_matches


class CommittedAdmissionTest(unittest.TestCase):
    def test_uncommitted_pending_input_cannot_be_counted_as_durable_custody(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);db=sqlite3.connect(root/'owned.sqlite')
            try:
                db.execute('pragma journal_mode=wal');db.execute('create table pending_inputs(id text,payload text)')
                db.execute('insert into pending_inputs values (?,?)',('control','PILOT_PENDING_INPUT_CONTROL'));db.commit()
                db.execute('insert into pending_inputs values (?,?)',('owned','PILOT_PENDING_INPUT'))
                self.assertFalse(committed_matches(root,'PILOT_PENDING_INPUT')['matches'])
                db.commit();matched=committed_matches(root,'PILOT_PENDING_INPUT')['matches']
                self.assertEqual(len(matched),1);self.assertEqual(matched[0]['table'],'pending_inputs')
            finally:db.close()

    def test_public_custody_must_match_the_actual_native_ACK_identity(self):
        probe=dict(responses=[dict(result=dict(ok=True,payload=dict(sessionInfo=dict(key='agent:main:owned',hasActiveRun=True,status='running',activeRunIds=['native-ack-run']))))])
        self.assertTrue(admitted_run(probe,'agent:main:owned','native-ack-run'))
        self.assertFalse(admitted_run(probe,'agent:main:owned','other-run'))
        self.assertFalse(admitted_run(probe,'agent:main:other','native-ack-run'))
        payload=probe['responses'][0]['result']['payload'];payload['sessionInfo'].pop('activeRunIds');payload['inFlightRun']={'runId':'native-ack-run'}
        self.assertTrue(admitted_run(probe,'agent:main:owned','native-ack-run'))
        self.assertFalse(admitted_run(probe,'agent:main:owned','other-run'))
