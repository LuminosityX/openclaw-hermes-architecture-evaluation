"""Long-conversation acceptance depends on preserved input, not merely valid JSON."""
import json
from pathlib import Path
import sys
import unittest
from urllib.request import Request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from conversation_workloads import workload
from task_transcripts import provider_for
from task_workloads import judge


class ConversationWorkloadTest(unittest.TestCase):
    def test_distinct_variants_preserve_declared_history_and_native_interventions(self):
        for i in range(1,6):
            tasks=[workload(f'PERF-10-S{i:02}',unit) for unit in range(1,7)]
            self.assertEqual(len({t['public_fixture_sha256'] for t in tasks}),6)
            for task in tasks:
                profile=task['conversation'];anchor=profile['anchor']
                self.assertLess(len(task['files']['reference.txt'].encode()),128*1024)
                self.assertLessEqual(sum(len(p.encode()) for p in profile['primers']),100*1024)
                self.assertEqual(profile['force_native_compaction'],i==3)
                self.assertEqual(profile['restart_before_final'],i==5)
                if i in {2,3,5}:
                    self.assertIn(anchor,profile['primers'][0])
                    self.assertNotIn(anchor,task['prompt'])
                    self.assertNotIn(anchor,task['files']['reference.txt'])

    def test_correct_settings_cannot_hide_a_lost_setup_anchor(self):
        task=workload('PERF-10-S03',1);expected=task['oracle']['expected']
        self.assertTrue(judge(task,{'answer.json':json.dumps(expected)})['accepted'])
        self.assertFalse(judge(task,{'answer.json':json.dumps(dict(expected,memory_anchor='lost'))})['accepted'])

    def test_golden_priming_and_compaction_do_not_write_an_early_deliverable(self):
        task=workload('PERF-10-S03',1);transport=provider_for(task)
        def answer(content):
            request=Request('https://unused.invalid',data=json.dumps(dict(messages=[dict(role='user',content=content)])).encode())
            with transport(request,timeout=1) as response:return json.loads(response.read().decode().splitlines()[0][6:])['choices'][0]['delta']
        self.assertEqual(answer(task['conversation']['primers'][0])['content'],'ACK')
        summary=answer('Summarize these turns:\n'+'\n'.join(task['conversation']['primers']))
        self.assertIn(task['conversation']['anchor'],summary['content'])
        call=answer('FINAL_STAGE '+task['task_id'])['tool_calls'][0]['function']
        self.assertEqual(call['name'],'task_files')
        self.assertEqual(json.loads(call['arguments'])['op'],'read')
