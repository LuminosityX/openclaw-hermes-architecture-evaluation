"""Bounded independent inspection of actual SQLite archive bytes."""
import io
import json
from pathlib import Path
import sqlite3
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
import backup_cases


class BackupOracleTests(unittest.TestCase):
    def test_queued_native_metadata_does_not_require_a_committed_user_message(self):
        session='agent:main:pilot:owned-queued-task'
        probe=dict(responses=[dict(result=dict(ok=True,payload=dict(messages=[],pendingInputs=dict(items=[]),
            sessionInfo=dict(key=session,status='queued',hasActiveRun=True))))])
        self.assertTrue(backup_cases.queued_admission(probe,session))
        self.assertFalse(backup_cases.queued_admission(probe,session+'-other'))
        probe['responses'][0]['result']['payload']['sessionInfo']['status']='done'
        self.assertFalse(backup_cases.queued_admission(probe,session))
    def test_exact_frozen_scenario_scope(self):
        plan=json.loads((Path(__file__).resolve().parents[1]/'campaigns/full-20261026-batched/plan.json').read_text())
        expected={s['id'] for c in plan['cases'] if c['id']=='REL-10' for s in c['scenarios']}
        self.assertEqual(expected,set(backup_cases.SCENARIOS))

    def test_native_control_requires_actual_independent_sqlite_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);database=root/'owned.sqlite';token='PILOT_OWNED_BACKUP_CONTROL'
            connection=sqlite3.connect(database);connection.execute('create table transcript_events(body text)')
            connection.execute('insert into transcript_events values (?)',(token,));connection.commit();connection.close()
            archive=root/'owned.tar.gz'
            with tarfile.open(archive,'w:gz') as output:
                data=json.dumps(dict(schemaVersion=1,sqliteSnapshots=[])).encode();info=tarfile.TarInfo('snapshot/manifest.json');info.size=len(data);output.addfile(info,io.BytesIO(data))
                output.add(database,arcname='snapshot/payload/state/agent.sqlite')
            inspection=backup_cases.inspect_archive(archive,root,token)
            self.assertEqual(inspection['databases'][0]['quick_check'],[('ok',)])
            self.assertTrue(inspection['databases'][0]['acknowledged_control_seen'])
            self.assertFalse(backup_cases.inspect_archive(archive,root,'PILOT_ABSENT_CONTROL')['databases'][0]['acknowledged_control_seen'])
            self.assertFalse(list(root.glob('inspect-*.sqlite')))


if __name__=='__main__':unittest.main()
