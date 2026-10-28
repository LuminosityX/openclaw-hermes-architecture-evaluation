"""Codex first-wave comparison controllers (profile A, deterministic track D).

Implements the shared first-wave scenarios of comparison/first-wave-protocol.md
against the pinned Codex CLI with model fixture M and OS observer O. Every unit
uses a fresh home, workspace and M instance, records the protocol outcome codes
(pass / fail / invalid / adapter_error / unsupported, with explicit reasons),
keeps its positive control separate, and verifies fault reachability through an
independent fixture event before injecting any fault. No real provider is
contacted; recovery, retries and session identity remain product behaviours.

Cases: P01-C0/C1 (fault domains; the exec profile shares the client/core
boundary, recorded as such), P02 (session reconstruction across a normal
exit), P03-C0/C1/C2/C3 (footprint and concurrency), H07-C0/C1 (model retry).
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_adapter import CodexAdapter
from model_fixture import ModelFixture
from os_observer import OSObserver

OUTCOME_OK = {'pass', 'fail'}  # both are valid product observations


def unit_record(case, condition, unit, outcome, reason, **fields):
    record = dict(case=case, condition=condition, unit_id=f'{case}-{condition}-U{unit}',
                  outcome=outcome, reason=reason,
                  wall_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
    record.update(fields)
    return record


def state_snapshot(adapter):
    files = []
    for path in adapter.rollout_paths():
        data = path.read_bytes()
        files.append(dict(path=str(path.relative_to(adapter.home)),
                           bytes=len(data),
                           sha256=hashlib.sha256(data).hexdigest()))
    return files


# --- P02: session reconstruction across a normal exit -------------------------

def run_p02(codex_bin, unit, output_dir, condition='C'):
    m = ModelFixture(unit_id=f'P02-U{unit}', ack_text=f'ACK_P02_U{unit}').start()
    adapter = CodexAdapter(codex_bin, f'P02-U{unit}', m.base_url)
    record = dict()
    try:
        first = adapter.run(f'SESSION_MARKER_P02_U{unit}', timeout=180)
        record['first_turn'] = {k: first[k] for k in ('exit', 'timed_out', 'duration_ms')}
        positive_control = first['exit'] == 0 and any(
            e['reply_text_head'] == f'ACK_P02_U{unit}' for e in m.entries('response-sent'))
        record['positive_control'] = positive_control
        record['state_files'] = state_snapshot(adapter)
        if not positive_control:
            return unit_record('P02', 'C', unit, 'invalid',
                               'first turn did not reach a successful final response',
                               **record)
        second = adapter.resume(f'CONTINUE_P02_U{unit}', timeout=180)
        record['second_turn'] = {k: second[k] for k in ('exit', 'timed_out', 'duration_ms')}
        texts = m.input_texts(2) or []
        joined = '\n'.join(texts)
        required = [f'SESSION_MARKER_P02_U{unit}', f'ACK_P02_U{unit}', f'CONTINUE_P02_U{unit}']
        presence = {token: token in joined for token in required}
        record['second_request_content'] = presence
        record['second_request_input_count'] = (m.entries('request')[1]['input_count']
                                                if len(m.entries('request')) > 1 else 0)
        record['model_ledger_requests'] = len(m.entries('request'))
        outcome = 'pass' if (second['exit'] == 0 and all(presence.values())) else 'fail'
        reason = ('second request carried marker, acknowledgment and new input'
                  if outcome == 'pass' else
                  'second turn failed or second request missed required content: '
                  + json.dumps(presence))
        return unit_record('P02', 'C', unit, outcome, reason, **record)
    except Exception as error:  # controller defect, never a product outcome
        return unit_record('P02', 'C', unit, 'adapter_error', f'{type(error).__name__}: {error}',
                           **record)
    finally:
        adapter.close()
        m.close()


# --- P01: fault domains --------------------------------------------------------

def run_p01(codex_bin, unit, output_dir, condition='C'):
    m = ModelFixture(unit_id=f'P01-{condition}-U{unit}',
                     ack_text=f'ACK_P01_{condition}_U{unit}').start()
    adapter = CodexAdapter(codex_bin, f'P01-{condition}-U{unit}', m.base_url)
    record = dict(
                  boundary_note='codex exec runs client and execution core in one '
                                'process tree; C1 and C2 share this common boundary')
    try:
        if condition == 'C0':
            result = adapter.run(f'Return the acknowledgment exactly.', timeout=180)
            record['run'] = {k: result[k] for k in ('exit', 'timed_out', 'duration_ms')}
            record['model_ledger_requests'] = len(m.entries('request'))
            positive = result['exit'] == 0 and any(
                e['reply_text_head'] for e in m.entries('response-sent'))
            return unit_record('P01', condition, unit,
                               'pass' if positive else 'fail',
                               'no-fault control reached a successful final response'
                               if positive else 'no-fault control did not complete',
                               **record)
        if condition == 'C1':
            m.mode = 'hold_before_response'
            m.hold_release.clear()
            observer = OSObserver(interval_seconds=0.1).start()
            spawned_ns = time.monotonic_ns()
            process = adapter.spawn('Return the acknowledgment exactly.')
            observer.observe_group(process.pid)
            fault_reached = m.request_received.wait(timeout=60)
            record['fault_reached'] = fault_reached
            record['fault_pid'] = process.pid
            if not fault_reached:
                CodexAdapter.kill_group(process)
                observer.stop()
                return unit_record('P01', condition, unit, 'invalid',
                                   'model request never arrived; fault boundary unreached',
                                   **record)
            first_request_ns = m.entries('request')[-1]['monotonic_ns']
            CodexAdapter.kill_group(process)
            killed_ns = time.monotonic_ns()
            process.wait(timeout=10)
            time.sleep(10)  # protocol observation window
            observer_summary = observer.stop()
            # Release the held response now; the fixture's write to the dead
            # socket records the teardown as a socket-close ledger entry.
            m.hold_release.set()
            m.mode = 'ack'
            time.sleep(0.5)
            socket_closes = m.entries('socket-close')
            record.update(
                fault_kill_latency_ms=(killed_ns - first_request_ns) / 1e6,
                request_to_fault_ms=(first_request_ns - spawned_ns) / 1e6,
                socket_close_after_kill=bool(socket_closes),
                socket_close_events=len(socket_closes),
                exit_events=[{k: e[k] for k in ('pid', 'exe', 'exit_observed_ns')}
                             for e in observer_summary['exit_events']],
                residual_processes=adapter.residual_processes(),
                observed_process_count=observer_summary['distinct_processes'],
                work_completed_independently=bool(m.entries('response-sent')))
            resume = adapter.resume('Continue and finish the task.', timeout=60)
            record['resume'] = {k: resume[k] for k in ('exit', 'timed_out', 'duration_ms')}
            record['model_ledger_requests_after_resume'] = len(m.entries('request'))
            consistent = (socket_closes and not adapter.residual_processes()
                          and resume['exit'] is not None)
            return unit_record('P01', condition, unit,
                               'pass' if consistent else 'fail',
                               'entry kill tore down the model connection; session state '
                               'survived and one native resume produced a terminal state'
                               if consistent else
                               'inconsistent post-fault observation (socket close, '
                               'residual processes or resume terminal state)',
                               **record)
        return unit_record('P01', condition, unit, 'unsupported',
                           'condition requires a tool adapter (T); pending', **record)
    except Exception as error:
        return unit_record('P01', condition, unit, 'adapter_error',
                           f'{type(error).__name__}: {error}', **record)
    finally:
        adapter.close()
        m.close()


# --- H07: model retry ----------------------------------------------------------

def run_h07(codex_bin, unit, output_dir, condition='C'):
    m = ModelFixture(unit_id=f'H07-{condition}-U{unit}',
                     ack_text=f'ACK_H07_{condition}_U{unit}').start()
    adapter = CodexAdapter(codex_bin, f'H07-{condition}-U{unit}', m.base_url)
    record = dict()
    try:
        if condition == 'C1':
            m.mode = '503_once'
        began_ns = time.monotonic_ns()
        result = adapter.run(f'H07_MARKER_U{unit}', timeout=180)
        record['run'] = {k: result[k] for k in ('exit', 'timed_out', 'duration_ms')}
        requests = m.entries('request')
        failures = m.entries('http-failure')
        responses = m.entries('response-sent')
        record.update(
            request_count=len(requests),
            failure_events=[{k: f[k] for k in ('request_number', 'status')} for f in failures],
            request_intervals_ms=[
                (requests[i]['monotonic_ns'] - requests[i - 1]['monotonic_ns']) / 1e6
                for i in range(1, len(requests))],
            elapsed_ms=(time.monotonic_ns() - began_ns) / 1e6,
            final_responses=len(responses))
        if requests:
            first_texts = '\n'.join(m.input_texts(1) or [])
            marker_occurrences = first_texts.count(f'H07_MARKER_U{unit}')
            retry_occurrences = 0
            for number in range(2, len(requests) + 1):
                retry_occurrences += ('\n'.join(m.input_texts(number) or [])
                                      ).count(f'H07_MARKER_U{unit}')
            record.update(marker_in_first_request=marker_occurrences,
                          marker_occurrences_in_retry_request=retry_occurrences)
        if condition == 'C0':
            ok = result['exit'] == 0 and len(requests) == 1 and responses
            return unit_record('H07', 'C0', unit, 'pass' if ok else 'fail',
                               'single request reached a successful final response'
                               if ok else 'positive control did not complete cleanly',
                               **record)
        if condition == 'C1':
            coherent = (result['exit'] == 0 and len(responses) == 1
                        and record.get('marker_occurrences_in_retry_request') == 1
                        and any(f['status'] == 503 for f in failures))
            return unit_record('H07', 'C1', unit, 'pass' if coherent else 'fail',
                               'one synthetic 503 was absorbed with a retry and exactly one '
                               'coherent final answer; the retry request carried the user '
                               'message exactly once'
                               if coherent else
                               'terminal state, request accounting or user-history '
                               'duplication violated the retry contract',
                               **record)
        return unit_record('H07', condition, unit, 'unsupported', 'unknown condition', **record)
    except Exception as error:
        return unit_record('H07', condition, unit, 'adapter_error',
                           f'{type(error).__name__}: {error}', **record)
    finally:
        adapter.close()
        m.close()


# --- P03: footprint and concurrency --------------------------------------------

def run_p03(codex_bin, unit, output_dir, condition='C'):
    sessions = {'C1': 1, 'C2': 4, 'C3': 8}.get(condition)
    if condition == 'C0':
        return unit_record('P03', 'C0', unit, 'unsupported',
                           'command-only profile: no resident service baseline to measure',
                           service_profile='codex exec is per-invocation; C0 idle-service '
                           'baseline does not apply')
    m = ModelFixture(unit_id=f'P03-{condition}-U{unit}', ack_text='ACK_P03_TASK').start()
    adapter = CodexAdapter(codex_bin, f'P03-{condition}-U{unit}', m.base_url)
    record = dict(sessions=sessions)
    try:
        observer = OSObserver(interval_seconds=0.1).start()
        spawns = []
        began_ns = time.monotonic_ns()
        for index in range(sessions):
            process = adapter.spawn(f'Return ACK_P03_TASK_{index} exactly.')
            if index == 0:
                observer.observe_group(process.pid)
            spawns.append(process)
        first_request_waited = m.request_received.wait(timeout=180)
        first_request_ns = (m.entries('request')[-1]['monotonic_ns']
                            if m.entries('request') else None)
        results = []
        deadline = time.monotonic() + 180
        for process in spawns:
            try:
                process.communicate(timeout=max(1.0, deadline - time.monotonic()))
            except Exception:
                CodexAdapter.kill_group(process)
                process.communicate()
            results.append(dict(exit=process.returncode, timed_out=False))
        completed_ns = time.monotonic_ns()
        time.sleep(10)  # post-completion sampling window
        summary = observer.stop()
        acknowledged = 0
        for entry in m.entries('response-sent'):
            if entry.get('response_type') == 'ack':
                acknowledged += 1
        record.update(
            cold_start_to_first_request_ms=(
                (first_request_ns - began_ns) / 1e6
                if first_request_ns and first_request_waited else None),
            task_exit_codes=[r['exit'] for r in results],
            tasks_attempted=sessions,
            valid_acknowledgments=acknowledged,
            wall_ms=(completed_ns - began_ns) / 1e6,
            observer_peak_rss_sum_kb=summary['peak_rss_sum_kb'],
            observer_cpu_seconds=summary['cpu_seconds_total'],
            observer_distinct_processes=summary['distinct_processes'],
            residual_processes=adapter.residual_processes(),
            rss_definition=summary['rss_definition'])
        complete = acknowledged == sessions and all(r['exit'] == 0 for r in results)
        return unit_record('P03', condition, unit, 'pass' if complete else 'fail',
                           f'all {sessions} session(s) returned their own valid acknowledgment'
                           if complete else
                           f'only {acknowledged}/{sessions} tasks completed with valid '
                           'acknowledgments; retained as a product observation',
                           **record)
    except Exception as error:
        return unit_record('P03', condition, unit, 'adapter_error',
                           f'{type(error).__name__}: {error}', **record)
    finally:
        adapter.close()
        m.close()


RUNNERS = {'P02': run_p02, 'P01': run_p01, 'H07': run_h07, 'P03': run_p03}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True, choices=sorted(RUNNERS))
    parser.add_argument('--condition', default='C')
    parser.add_argument('--unit', type=int, default=1)
    parser.add_argument('--codex', default='codex')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    record = RUNNERS[args.case](args.codex, args.unit, args.output, args.condition)
    path = args.output / f'{record["unit_id"]}.json'
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(unit=record['unit_id'], outcome=record['outcome'],
                          reason=record['reason'], path=str(path)), ensure_ascii=False))


if __name__ == '__main__':
    main()
