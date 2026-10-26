"""Portable artifact mapping, record fidelity and target provenance are substantive."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from portable_support import owned_child_environment,staged_asset,transcript_inventory
from run_cross_os import native_texts
from adapter_readiness import SOURCES,native_validation
from campaign import load_plan
from run_campaign_family import bind_unit
from suite import ROOT


class PortableEvidenceTest(unittest.TestCase):
    def test_manifest_assets_cannot_escape_staging_or_use_Windows_drive_syntax(self):
        with tempfile.TemporaryDirectory() as directory:
            staging=Path(directory)
            manifest=dict(assets=[dict(kind='state',archivePath='archive/payload/posix/owned/state')])
            self.assertEqual(staged_asset(staging,manifest,'state'),staging/'archive/payload/posix/owned/state')
            for path in ['../escape','C:/escape','owned\\escape','/absolute']:
                manifest['assets'][0]['archivePath']=path
                with self.assertRaises(RuntimeError):staged_asset(staging,manifest,'state')

    def test_independent_native_row_identity_and_binary_bytes_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);db=sqlite3.connect(root/'owned.sqlite')
            db.execute('create table transcript_events(id text primary key,payload blob) without rowid')
            db.execute('insert into transcript_events values (?,?)',('native-id',b'original\x00bytes'));db.commit()
            before=transcript_inventory(root)
            self.assertEqual(before[0]['quick_check'],[['ok']])
            db.execute('update transcript_events set id=?',('changed-id',));db.commit()
            self.assertNotEqual(transcript_inventory(root)[0]['record_sha256'],before[0]['record_sha256']);db.close()

    def test_native_process_handle_text_is_decoded_without_trusting_command_stdout_as_a_handle(self):
        result=[dict(role='tool',content=json.dumps(dict(content=[dict(type='text',text='actual-handle running 2s :: owned-process.py')])))]
        self.assertIn('actual-handle running 2s :: owned-process.py',native_texts(result))
        windows=[dict(role='tool',content='actual-handle running 2s :: & C:\\hostedtoolcache\\win...\\python.exe')]
        import re
        self.assertEqual(re.findall(r'(?m)^\s*([^\s]+)\s+running\s+[^\n]*::','\n'.join(native_texts(windows))),['actual-handle'])

    def test_child_environment_does_not_propagate_real_tokens_or_provider_keys(self):
        import os
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'GITHUB_TOKEN':'not-for-native-children','DEEPSEEK_API_KEY':'not-for-this-fixture'}):
            env=owned_child_environment(Path(directory))
            self.assertNotIn('GITHUB_TOKEN',env);self.assertNotIn('DEEPSEEK_API_KEY',env)

    def test_linux_generic_or_syntax_reports_cannot_be_relabelled_as_Windows_results(self):
        plan=load_plan();native=dict(kind='native-campaign-family-unit',case_id='REL-08',full_campaign_coverage=True,runtime_identity=dict(version=plan['target']['version'],commit=plan['target']['source_commit']),
            controller_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES['REL-08']},observations=[])
        with self.assertRaisesRegex(ValueError,'actual native Linux and Windows'):
            bind_unit(plan,'REL-08',1,native,'hosted','controller','unit-1/summary.json','a'*64)
