"""Architecture explanations must remain bound to source, not merely a release label."""

import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from source_evidence import collect_one, load_registry, validate_registry
from suite import load_matrix


class SourceEvidenceTests(unittest.TestCase):
    def test_a_new_campaign_cannot_reuse_old_source_analysis(self):
        target=dict(load_matrix()['target'],source_commit='b'*40)
        with self.assertRaisesRegex(ValueError,'active campaign commit'):
            validate_registry(load_registry(),target)

    def test_a_source_story_requires_an_alternative_that_can_disprove_it(self):
        registry=copy.deepcopy(load_registry())
        registry['investigations'][0]['falsifiers']=[]
        with self.assertRaisesRegex(ValueError,'counterevidence'):
            validate_registry(registry,load_matrix()['target'])

    def test_same_path_with_different_bytes_is_not_source_evidence(self):
        source=load_registry()['sources'][0]
        with patch('urllib.request.urlopen',return_value=io.BytesIO(b'other revision')):
            with self.assertRaisesRegex(ValueError,'source bytes changed'):
                collect_one(source,load_matrix()['target']['source_commit'])


if __name__=='__main__':
    unittest.main()
