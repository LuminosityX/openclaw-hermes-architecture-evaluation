"""Missing native session state differs from a missing tool or an error string."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from budget_capability_cases import missing_goal


class BudgetGoalSnapshotTest(unittest.TestCase):
    def test_versioned_native_missing_snapshot_is_accepted(self):
        self.assertTrue(missing_goal([dict(role='tool',content='{"status":"missing"}')]))
        self.assertFalse(missing_goal([dict(role='tool',content='Unknown tool: get_goal')]))
        self.assertFalse(missing_goal([dict(role='tool',content='{"status":"error","error":"goal missing"}')]))
        self.assertFalse(missing_goal([dict(role='tool',content='{"status":"found","goal":{"id":"actual"}}')]))
