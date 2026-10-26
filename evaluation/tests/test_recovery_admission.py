"""Startup polling cannot replay ambiguous or dispatched external work."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from recovery_cases import pending_admission


class AdmissionTest(unittest.TestCase):
    def test_only_explicit_undispatched_admission_rejection_is_retryable(self):
        log='AgentDatabaseAdmissionError: main has not completed startup inspection and preparation'
        self.assertTrue(pending_admission({'status':500},log,False,0))
        for status,seen,effects,record in [(None,False,0,log),(200,False,0,log),(500,True,0,log),(500,False,1,log),(500,False,0,'unrelated internal error')]:
            self.assertFalse(pending_admission({'status':status},record,seen,effects))
