"""An archive oracle must detect changed event identities and binary payloads."""
import sqlite3
import tempfile
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from retention_cases import transcript_inventory

class RecordFidelityTest(unittest.TestCase):
    def test_native_row_identity_and_binary_content_are_both_accounted_for(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);path=root/'events.sqlite';db=sqlite3.connect(path)
            db.execute('create table transcript_events(id text primary key,payload blob)')
            db.execute('insert into transcript_events values (?,?)',('stable-event',b'original\x00payload'));db.commit()
            before=transcript_inventory(root)[0]
            db.execute('update transcript_events set id=?',('different-event',));db.commit()
            changed_id=transcript_inventory(root)[0]
            db.execute('update transcript_events set id=?,payload=?',('stable-event',b'different\x00payload'));db.commit();db.close()
            changed_body=transcript_inventory(root)[0]
            for row in [changed_id,changed_body]:
                self.assertEqual(row['row_count'],before['row_count'])
                self.assertNotEqual(row['ordered_independent_record_sha256'],before['ordered_independent_record_sha256'])

    def test_incomplete_bounded_scan_cannot_claim_archive_fidelity(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);db=sqlite3.connect(root/'events.sqlite');db.execute('create table transcript_events(id integer)')
            db.executemany('insert into transcript_events values (?)',[(i,) for i in range(1001)]);db.commit();db.close()
            with self.assertRaisesRegex(RuntimeError,'record bound'):transcript_inventory(root)
