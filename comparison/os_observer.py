"""Comparison operating-system observer O.

Samples the product's process tree every 100 ms from /proc: per-process RSS,
CPU time, parent and executable; records first-seen/last-seen lifecycle
timestamps and exit events. Only processes belonging to the observed root's
session (process group) and their descendants are tracked; the model fixture,
tool fixture and controller are never included because they live outside the
observed group. RSS summaries are sums of per-process resident memory and are
reported with exactly that definition.
"""

import os
import threading
import time


class OSObserver:
    def __init__(self, interval_seconds=0.1):
        self.interval = interval_seconds
        self.samples = []           # [{monotonic_ns, processes:{pid:{rss_kb,cpu_ticks,exe,ppid}}}]
        self.exits = []             # [{pid, exe, last_seen_ns, exit_observed_ns, signal_hint}]
        self._roots = set()
        self._tracked = {}          # pid -> {exe, ppid, first_seen_ns, last_seen_ns, last_sample}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._page_bytes = os.sysconf('SC_PAGESIZE')
        self._clock_ticks_per_second = os.sysconf('SC_CLK_TCK')  # typically 100 on Linux

    # -- public API ------------------------------------------------------------

    def observe_group(self, pid):
        """Track the session (process group) of pid plus all descendants."""
        with self._lock:
            self._roots.add(pid)

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        return self.summary()

    # -- sampling ---------------------------------------------------------------

    def _loop(self):
        while not self._stop.is_set():
            began = time.monotonic_ns()
            self._sample_once()
            spent = (time.monotonic_ns() - began) / 1e9
            time.sleep(max(0.0, self.interval - spent))

    @staticmethod
    def _read_stat(pid):
        try:
            with open(f'/proc/{pid}/stat', 'rb') as handle:
                data = handle.read().decode(errors='replace')
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            return None
        # comm may contain spaces/parens: split after the last ')'.
        try:
            tail = data[data.rindex(')') + 2:].split()
        except ValueError:
            return None
        # fields from stat(5): state=3, ppid=4, pgrp=5, utime=14, stime=15 (1-indexed
        # after pid+comm); rss in pages is field 24.
        return dict(state=tail[1], ppid=int(tail[2]), pgrp=int(tail[3]),
                    utime_ticks=int(tail[11]), stime_ticks=int(tail[12]),
                    rss_pages=int(tail[21]))

    @staticmethod
    def _read_exe(pid):
        try:
            with open(f'/proc/{pid}/cmdline', 'rb') as handle:
                parts = handle.read().split(b'\0')
            return parts[0].decode(errors='replace')[:120] if parts else ''
        except (FileNotFoundError, ProcessLookupError, PermissionError, IndexError):
            return None

    def _sample_once(self):
        now = time.monotonic_ns()
        with self._lock:
            roots = set(self._roots)
            tracked = dict(self._tracked)
        if not roots:
            return
        root_pgids = {}
        alive = {}
        for entry in os.listdir('/proc'):
            if not entry.isdigit():
                continue
            pid = int(entry)
            stat = self._read_stat(pid)
            if stat is None:
                continue
            alive[pid] = stat
            if pid in roots:
                root_pgids[pid] = stat['pgrp']
        if not root_pgids:
            return
        group_pids = {pid for pid, stat in alive.items()
                      if stat['pgrp'] in root_pgids or pid in roots}
        # Grow to descendants of tracked processes.
        changed = True
        while changed:
            changed = False
            for pid, stat in alive.items():
                if pid not in group_pids and stat['ppid'] in group_pids:
                    group_pids.add(pid)
                    changed = True
        sample = {}
        with self._lock:
            for pid in group_pids:
                stat = alive[pid]
                exe = self._read_exe(pid)
                previous = self._tracked.get(pid)
                if previous and previous.get('exe'):
                    exe = previous['exe']
                entry = dict(rss_kb=stat['rss_pages'] * self._page_bytes // 1024,
                             cpu_ticks=stat['utime_ticks'] + stat['stime_ticks'],
                             ppid=stat['ppid'], state=stat['state'], exe=exe,
                             first_seen_ns=previous['first_seen_ns'] if previous else now,
                             last_seen_ns=now)
                self._tracked[pid] = entry
                sample[pid] = dict(entry)
            for pid in list(self._tracked):
                if pid not in group_pids:
                    gone = self._tracked.pop(pid)
                    self.exits.append(dict(pid=pid, exe=gone.get('exe'),
                                           last_seen_ns=gone['last_seen_ns'],
                                           exit_observed_ns=now,
                                           exit_kind='session-exit-or-detach'))
            self.samples.append(dict(monotonic_ns=now, processes=sample))

    # -- summaries ---------------------------------------------------------------

    def summary(self):
        with self._lock:
            samples = list(self.samples)
            exits = list(self.exits)
            tracked = {pid: dict(v) for pid, v in self._tracked.items()}
        peak_rss_sum_kb = 0
        for sample in samples:
            total = sum(p['rss_kb'] for p in sample['processes'].values())
            peak_rss_sum_kb = max(peak_rss_sum_kb, total)
        cpu_ticks_total = 0
        for pid, entry in tracked.items():
            cpu_ticks_total = max(cpu_ticks_total, entry['cpu_ticks'])
        # CPU across the whole observation also counts exited processes via their
        # final tracked tick counts.
        final_ticks = {}
        for sample in samples:
            for pid, process in sample['processes'].items():
                final_ticks[pid] = max(final_ticks.get(pid, 0), process['cpu_ticks'])
        cpu_seconds_total = sum(final_ticks.values()) / self._clock_ticks_per_second
        lifecycles = []
        for pid, entry in sorted(tracked.items()):
            lifecycles.append(dict(pid=pid, exe=entry.get('exe'),
                                   first_seen_ns=entry['first_seen_ns'],
                                   last_seen_ns=entry['last_seen_ns']))
        return dict(sample_count=len(samples),
                    interval_seconds=self.interval,
                    peak_rss_sum_kb=peak_rss_sum_kb,
                    rss_definition='sum of per-process resident memory (kB) '
                                   'over the observed session group',
                    cpu_seconds_total=round(cpu_seconds_total, 3),
                    distinct_processes=len(set(final_ticks) | {e['pid'] for e in exits}),
                    process_lifecycles=lifecycles,
                    exit_events=exits)
