"""Original evidence binding and bounded in-memory retention."""
import io
import json
from pathlib import Path
import sys
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from campaign import load_plan
from retain_campaign_results import bounded_archive,compact_results


def archive(files):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as output:
        for name,value in files.items():
            output.writestr(name,value)
    return stream.getvalue()


class RetentionTests(unittest.TestCase):
    def fixture(self):
        plan=load_plan()
        row=dict(schema_version=1,plan_sha256=plan['plan_sha256'],product='openclaw',target_version=plan['target']['version'],
            target_commit=plan['target']['source_commit'],scenario_id='REL-14-S01',unit=1,state='pass',native_invoked=True,
            fixture_validated=True,run_id='123',evidence=['unit-1/summary.json#REL-14-S01'],
            assertions=[dict(name='receipt',verdict='pass',evidence=['receipt-ledger'])],full_campaign_coverage=True)
        files={'results.json':json.dumps([row]),'execution.json':json.dumps(dict(github_run_id='123',controller_commit='abc')),
               'unit-1/summary.json':'{"synthetic":true}'}
        return plan,files

    def test_unsafe_names_and_expansion_bomb_are_rejected_without_extraction(self):
        with self.assertRaisesRegex(ValueError,'Unsafe'):
            bounded_archive(archive({'../outside.json':'x'}))
        with self.assertRaisesRegex(ValueError,'expanded bound'):
            bounded_archive(archive({'oversize.txt':'0'*(8*1024**2+1)}))

    def test_original_records_are_bound_to_hosted_artifact_hashes(self):
        plan,files=self.fixture()
        rows,manifest=compact_results(plan,dict(id=123,head_sha='abc'),dict(id=456,name='campaign-REL-14'),archive(files))
        self.assertEqual(rows[0]['hosted_artifact_id'],456)
        self.assertEqual(rows[0]['original_evidence_paths'],['unit-1/summary.json#REL-14-S01'])
        self.assertTrue(rows[0]['evidence'][0].startswith('https://github.com/'))
        self.assertEqual(manifest['files']['unit-1/summary.json']['bytes'],len(files['unit-1/summary.json']))
        self.assertFalse(manifest['local_raw_evidence_retained'])

    def test_missing_receipt_evidence_is_not_retained_as_completed(self):
        plan,files=self.fixture()
        files.pop('unit-1/summary.json')
        with self.assertRaisesRegex(ValueError,'evidence path is missing'):
            compact_results(plan,dict(id=123,head_sha='abc'),dict(id=456,name='campaign-REL-14'),archive(files))


if __name__=='__main__':
    unittest.main()
