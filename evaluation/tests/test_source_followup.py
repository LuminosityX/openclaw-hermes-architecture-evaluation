"""Source-derived counterfactuals must not bake their desired product result into validity."""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

RUNNER=Path(__file__).resolve().parents[1]/'runner'
def module(name):
    spec=importlib.util.spec_from_file_location(name,RUNNER/(name+'.py'))
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value
pilot=module('pilot')
followup=module('source_followup')


class SourceFollowupTests(unittest.TestCase):
    def test_known_name_catalog_can_skip_search_and_describe(self):
        token='PILOT_SRC_KNOWN_T0'
        controls=['tool_search','tool_describe','tool_call']
        self.assertEqual(pilot.planned_tool_call(controls,token,'effect',[],strategy='known'),
                         ('tool_call',dict(id='eval_probe',args=dict(token=token,action='effect'))))
        self.assertEqual(pilot.planned_tool_call(controls,token,'effect',[],strategy='conservative')[0],'tool_search')
        failed=[dict(content=json.dumps(dict(tool=dict(id='plugin:pilot-probe:eval_probe',name='eval_probe'),error='controlled')))]
        self.assertIsNone(pilot.planned_tool_call(controls,token,'throw',failed,strategy='known'))

    def test_denied_control_really_requests_the_excluded_tool(self):
        token='PILOT_DENIED_SOURCE'
        control,args=pilot.planned_tool_call(['tool_call','tool_search','tool_describe'],token,'effect',[])
        self.assertEqual((control,args['id']),('tool_call','denied_probe'))
        self.assertEqual(pilot.planned_tool_call(['eval_probe'],token,'effect',[])[0],'denied_probe')

    def test_catalog_configuration_uses_public_native_setting(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'unit'
            root.mkdir()
            config=pilot.configuration(root,catalog_size=64,tool_search=False)
            manifest=json.loads((root/'plugin/openclaw.plugin.json').read_text())
            self.assertFalse(config['tools']['toolSearch'])
            self.assertEqual(len(config['tools']['allow']),64)
            self.assertIn('denied_probe',manifest['contracts']['tools'])
            self.assertNotIn('denied_probe',config['tools']['allow'])
            if shutil.which('node'):
                subprocess.run(['node','--check',str(root/'plugin/index.js')],check=True,capture_output=True)

    def test_provider_accounting_preserves_unknown_token_prices(self):
        events=[dict(kind='provider-request',token='one',payload_bytes=120,tool_schema_bytes=20,message_bytes=70,tool_names=['tool_call'])]*2
        value=followup.provider_totals(events)
        self.assertEqual(value['model_requests'],2)
        self.assertEqual(value['total_payload_bytes'],240)
        self.assertIsNone(value['token_counts'])
        self.assertIsNone(value['calculated_cost_usd'])

    def test_batch_cpu_has_a_separate_measurement_window(self):
        delta=followup.cpu_delta(dict(user_seconds=20,system_seconds=4,monotonic_ns=1_000_000),
                                 dict(user_seconds=21.5,system_seconds=4.2,monotonic_ns=501_000_000))
        self.assertEqual(delta['user_seconds'],1.5)
        self.assertEqual(delta['window_ms'],500)

    def test_a_security_counterexample_remains_a_valid_observation(self):
        fixture=SimpleNamespace(events=[])
        def request(token):
            fixture.events.extend([dict(kind='provider-request',token=token),dict(kind='effect-commit',token=token)])
            return dict(accepted=True,token=token,status=200)
        gateway=SimpleNamespace(process=SimpleNamespace(poll=lambda:None),request=request)
        result=followup.denied_control(fixture,gateway,'unit')
        self.assertTrue(result['valid'])
        self.assertFalse(result['rejected_without_effect'])
        self.assertEqual(result['effect_count'],1)


if __name__=='__main__':
    unittest.main()
