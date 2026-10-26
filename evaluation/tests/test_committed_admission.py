"""Committed custody is independently visible; an uncommitted row is not."""
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from admission_cases import committed_matches


class CommittedAdmissionTest(unittest.TestCase):
    def test_uncommitted_pending_input_cannot_be_counted_as_durable_custody(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);db=sqlite3.connect(root/'owned.sqlite')
            try:
                db.execute('pragma journal_mode=wal');db.execute('create table pending_inputs(id text,payload text)');db.commit()
                db.execute('insert into pending_inputs values (?,?)',('owned','PILOT_PENDING_INPUT'))
                self.assertFalse(committed_matches(root,'PILOT_PENDING_INPUT')['matches'])
                db.commit();matched=committed_matches(root,'PILOT_PENDING_INPUT')['matches']
                self.assertEqual(len(matched),1);self.assertEqual(matched[0]['table'],'pending_inputs')
            finally:db.close()
