"""Verify the deterministic provider speaks the advertised native tool protocol."""

import importlib.util
import json
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('native_pilot',Path(__file__).resolve().parents[1]/'runner/pilot.py')
pilot=importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


class ProviderFixtureTests(unittest.TestCase):
    def test_direct_tool_and_deferred_tool_use_their_own_contract(self):
        token='PILOT_WARM_0_1'
        self.assertEqual(pilot.planned_tool_call(['eval_probe'],token,'effect',[]),('eval_probe',dict(token=token,action='effect')))
        controls=['tool_search','tool_describe','tool_call']
        self.assertEqual(pilot.planned_tool_call(controls,token,'effect',[]),('tool_search',dict(query='eval_probe',limit=3)))
        search=[dict(role='tool',content=json.dumps([dict(id='plugin:pilot-probe:eval_probe',name='eval_probe')]))]
        self.assertEqual(pilot.planned_tool_call(controls,token,'effect',search),('tool_describe',dict(id='plugin:pilot-probe:eval_probe')))
        described=search+[dict(role='tool',content='schema')]
        self.assertEqual(pilot.planned_tool_call(controls,token,'effect',described),('tool_call',dict(id='plugin:pilot-probe:eval_probe',args=dict(token=token,action='effect'))))

    def test_unmatched_catalog_does_not_guess_a_tool_id(self):
        controls=['tool_search','tool_describe','tool_call']
        results=[dict(role='tool',content='[]')]
        self.assertIsNone(pilot.planned_tool_call(controls,'PILOT_WARM_0_1','effect',results))

    def test_catalog_can_be_wrapped_in_native_text_blocks(self):
        value=[dict(content=json.dumps([dict(type='text',text=json.dumps(dict(id='mcp:probe:eval_probe',name='probe__eval_probe')))]))]
        self.assertEqual(pilot.catalog_id(value,'probe__eval_probe'),'mcp:probe:eval_probe')

    def test_sandbox_and_mcp_select_distinct_tools(self):
        self.assertEqual(pilot.target_tool('PILOT_SANDBOX_WRITE_0'),'exec')
        self.assertEqual(pilot.target_tool('PILOT_BLOCK_B0_MCP'),'probe__eval_probe')


if __name__=='__main__':
    unittest.main()
