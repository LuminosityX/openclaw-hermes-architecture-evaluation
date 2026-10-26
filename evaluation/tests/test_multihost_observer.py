"""Regression: real effect receipts already carry their host identity."""
from pathlib import Path
import sys
import tempfile
import threading
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from run_multihost_host import Effects

class MultihostObserverTest(unittest.TestCase):
    def test_commit_receipt_is_not_lost_to_duplicate_host_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            observer=object.__new__(Effects);observer.lock=threading.Lock();observer.events=[];observer.boot='owned-host';observer.output=Path(temporary)
            receipt=dict(token='PILOT_MULTI_S1_U0_FIRST',host_boot_id='owned-host',role='gateway',helper_host_pid=123)
            observer.record('actual-tool-effect-committed',**receipt)
            self.assertEqual(observer.events[0]['host_boot_id'],'owned-host')
            self.assertEqual(observer.events[0]['helper_host_pid'],123)
            self.assertTrue((observer.output/'host-events.json').is_file())
