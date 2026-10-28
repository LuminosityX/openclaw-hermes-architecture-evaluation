"""OS observer tests: tracking, sampling, exit detection and summary semantics."""

import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'comparison'))

from os_observer import OSObserver


class OSObserverTests(unittest.TestCase):
    def test_tracks_spawned_group_and_reports_exit(self):
        observer = OSObserver(interval_seconds=0.02).start()
        try:
            process = subprocess.Popen(
                ['bash', '-c', 'sleep 0.5; echo done'], start_new_session=True,
                stdout=subprocess.DEVNULL)
            observer.observe_group(process.pid)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                with observer._lock:
                    if observer.samples:
                        break
                time.sleep(0.01)
            process.wait(timeout=5)
            # let the observer record the exit
            time.sleep(0.15)
        finally:
            summary = observer.stop()
        self.assertGreater(summary['sample_count'], 3)
        # bash -c 'sleep 0.5; echo done' runs sleep as a child: the observed
        # session group legitimately contains both processes.
        self.assertEqual(summary['distinct_processes'], 2)
        exited = {event['pid'] for event in summary['exit_events']}
        self.assertIn(process.pid, exited)
        self.assertEqual(len(summary['exit_events']), 2)
        bash_events = [event for event in summary['exit_events']
                       if event['pid'] == process.pid]
        self.assertIn('bash', bash_events[0]['exe'])
        self.assertGreaterEqual(summary['peak_rss_sum_kb'], 0)
        self.assertIn('sum of per-process resident memory', summary['rss_definition'])

    def test_descendants_join_the_group(self):
        observer = OSObserver(interval_seconds=0.02).start()
        try:
            process = subprocess.Popen(
                ['bash', '-c', 'sleep 0.6 & sleep 0.6; wait'], start_new_session=True,
                stdout=subprocess.DEVNULL)
            observer.observe_group(process.pid)
            deadline = time.monotonic() + 2
            seen_children = 0
            while time.monotonic() < deadline:
                with observer._lock:
                    if observer.samples:
                        seen_children = max(seen_children, len(observer.samples[-1]['processes']))
                if seen_children >= 2:
                    break
                time.sleep(0.02)
            process.wait(timeout=5)
            time.sleep(0.15)
        finally:
            summary = observer.stop()
        self.assertGreaterEqual(summary['distinct_processes'], 2,
                                'the backgrounded sleep child must join the observed group')
        self.assertIn('cpu_seconds_total', summary)


if __name__ == '__main__':
    unittest.main()
