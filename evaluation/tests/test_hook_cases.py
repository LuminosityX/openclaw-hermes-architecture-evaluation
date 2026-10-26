"""Control scripts exercise public hooks and keep effects separate from reports."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from hook_cases import acceptance, configure


class HookTests(unittest.TestCase):
    def test_reference_hooks_really_appear_in_registered_plugin(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'case'
            configure(root,'EXT-08-S03')
            plugin=(root/'plugin/index.js').read_text()
            self.assertIn("api.on('before_tool_call'",plugin)
            self.assertIn("api.on('tool_result_persist'",plugin)
            self.assertIn('const mode="mutation"',plugin)

    def test_effect_order_violation_is_detected(self):
        events=[dict(kind='hook',name='before-high',monotonic_ns=20),dict(kind='effect-start',monotonic_ns=10),
                dict(kind='effect-commit',monotonic_ns=30),dict(kind='hook',name='after',monotonic_ns=40)]
        checks={c['name']:c['verdict'] for c in acceptance('EXT-08-S01',[{'accepted':True}],events,{})}
        self.assertEqual(checks['before-effect-after-order'],'fail')

    def test_disabling_plugin_must_stop_real_effects(self):
        events=[dict(kind='hook',name='before-high'),dict(kind='hook',name='before-high'),dict(kind='effect-commit',token='PILOT_DISABLED_')]
        requests=[dict(accepted=True),dict(accepted=False),dict(accepted=True)]
        checks={c['name']:c['verdict'] for c in acceptance('EXT-08-S06',requests,events,{})}
        self.assertEqual(checks['disabled-plugin-no-effect'],'fail')

    def test_cancelled_request_cannot_hide_a_committed_effect(self):
        events=[dict(kind='hook',name='before-high'),dict(kind='hook',name='async-hook-settled'),dict(kind='effect-commit')]
        checks={c['name']:c['verdict'] for c in acceptance('EXT-08-S05',[{'accepted':False}],events,{'cancellation':{'returncode':0}})}
        self.assertEqual(checks['no-effect-after-cancellation'],'fail')
