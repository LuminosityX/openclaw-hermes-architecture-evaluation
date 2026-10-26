"""A failed external attempt resumes only its exact public computation."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
import external_harness_worker as worker


class ExternalHarnessCheckpointTest(unittest.TestCase):
    def test_actual_checkpoint_survives_failure_and_avoids_recalculation(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(worker,'announce') as observer:
            request=dict(task=dict(task_id='owned',operation='add',left=8,right=13),state_directory=directory,fail_once=True)
            self.assertEqual(worker.attempt(request),73)
            output=io.StringIO()
            with contextlib.redirect_stdout(output):self.assertEqual(worker.attempt(request),0)
            result=json.loads(output.getvalue())
            self.assertEqual(result['value'],21);self.assertTrue(result['resumed'])
            self.assertEqual(result['calculation_count'],1)
            self.assertEqual(observer.call_args_list[0].args[0],'external-checkpoint-then-exit')
            request['task']['right']=14
            self.assertEqual(worker.attempt(request),73)
            self.assertEqual(len(list(Path(directory).glob('*.json'))),2)

    def test_tool_free_executor_rejects_unbounded_or_unsupported_work(self):
        for task in [dict(operation='shell',left=1,right=2),dict(operation='add',left=True,right=2),dict(operation='add',left=10**7,right=2)]:
            with self.assertRaises(ValueError):worker.calculate(task)
