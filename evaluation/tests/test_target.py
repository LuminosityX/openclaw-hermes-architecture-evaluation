"""Campaign pins are exact, stable and checked independently of bootstrap runs."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from suite import load_matrix, validate
from target import require_same_target, stable_target, verify_installation


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.pinned=load_matrix()['target']

    def test_prerelease_and_registry_disagreement_rejected(self):
        release=dict(prerelease=True,draft=False,tag_name='v'+self.pinned['version'])
        with self.assertRaisesRegex(ValueError,'stable release'):
            stable_target(release,dict(version=self.pinned['version']),self.pinned['source_commit'])
        release['prerelease']=False
        with self.assertRaisesRegex(ValueError,'disagree'):
            stable_target(release,dict(version='2020.1.1'),self.pinned['source_commit'])

    def test_stale_version_or_changed_integrity_fail(self):
        for field,value in [('version','2020.1.1'),('source_commit','a'*40),('npm_integrity','sha512-different')]:
            resolved=dict(self.pinned,**{field:value})
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'stale or inconsistent'):
                require_same_target(self.pinned,resolved)

    def test_matrix_cannot_silently_revert_to_unpinned_target(self):
        matrix=load_matrix()
        matrix['target']['version']=None
        with self.assertRaisesRegex(ValueError,'Exact stable version'):
            validate(matrix)

    def test_installed_build_and_lock_must_match_published_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            modules=root/'node_modules'
            product=modules/'openclaw'
            (product/'dist').mkdir(parents=True)
            (product/'package.json').write_text(json.dumps(dict(version=self.pinned['version'])))
            build=product/'dist/build-info.json'
            build.write_text(json.dumps(dict(version=self.pinned['version'],commit=self.pinned['source_commit'])))
            lock=root/'package-lock.json'
            lock.write_text(json.dumps(dict(packages={'node_modules/openclaw':dict(version=self.pinned['version'],integrity=self.pinned['npm_integrity'])})))
            self.assertTrue(verify_installation(self.pinned,modules,lock)['version_and_commit_match'])
            build.write_text(json.dumps(dict(version=self.pinned['version'],commit='b'*40)))
            with self.assertRaisesRegex(ValueError,'build commit'):
                verify_installation(self.pinned,modules,lock)


if __name__=='__main__':
    unittest.main()
