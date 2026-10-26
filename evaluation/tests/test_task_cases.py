"""Task effects and artifacts must survive independent negative controls."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'runner'),str(Path(__file__).resolve().parents[1]/'tools')]
from task_cases import TaskFixture, configure
from task_workloads import workload, judge


class TaskCasesTests(unittest.TestCase):
    def fixture(self,root,task):
        fixture=object.__new__(TaskFixture)
        fixture.task_root=root;fixture.task=task;fixture.task_events=[];fixture.events=[]
        fixture.lock=threading.Lock();fixture.receipts={};fixture.prepared=None;fixture.ack_lost=False
        return fixture

    def test_lost_ack_and_same_key_retry_commit_once(self):
        task=workload('PERF-09-S05',1)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            fixture=self.fixture(root,task)
            oracle=task['oracle']
            order=oracle['order_id']
            self.assertEqual(fixture.service(dict(action='prepare',order_id=order,amount_cents=oracle['amount_cents']))[0],200)
            commit=dict(action='commit',order_id=order,idempotency_key='stable')
            self.assertEqual(fixture.service(commit)[0],503)
            status,receipt=fixture.service(commit)
            self.assertEqual(status,200)
            fixture.service(dict(action='status',order_id=order))
            self.assertTrue(judge(task,{'receipt.json':json.dumps(receipt)},service_events=fixture.task_events)['accepted'])
            fixture.service(dict(commit,idempotency_key='different'))
            self.assertFalse(judge(task,{'receipt.json':json.dumps(receipt)},service_events=fixture.task_events)['accepted'])

    def test_file_access_is_bounded_and_input_files_are_immutable(self):
        task=workload('PERF-09-S03',1)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            config=configure(root,task['public'])
            fixture=self.fixture(root,task)
            self.assertEqual(fixture.files(dict(op='read',path='/etc/passwd'))[0],403)
            self.assertEqual(fixture.files(dict(op='write',path='input-a.csv',content='corrupted'))[0],403)
            self.assertEqual(fixture.files(dict(op='write',path='result.json',content='{}'))[0],200)
            self.assertEqual(fixture.files(dict(op='read',path='result.json'))[1]['content'],'{}')
            self.assertEqual((root/'workspace/input-a.csv').read_text(),task['files']['input-a.csv'])
            self.assertEqual(config['agents']['defaults']['model']['primary'],'deepseek/deepseek-flash')
            self.assertNotIn('oracle',(root/'config.json').read_text())
