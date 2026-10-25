"""Frozen quantitative comparisons from completed, scope-matched native measurements."""
import json, statistics, sys, time
from runtime import R, save
sys.path.insert(0, '/root/output/oc-hermes-formal-design-20261024')
from score_protocol import quant_compare


def main():
    scale_file = R / 'results/scale-matched-tools.json'
    scale = json.loads(scale_file.read_text())
    mechanisms = json.loads((R / 'results/native-suite.json').read_text())
    if len(scale) != 12 or any(x.get('profile') != 'matched-file-and-shell-tools' for x in scale):
        raise RuntimeError('Primary scope-matched independent service instances incomplete')
    if not all(x['passed'] for x in scale):
        raise RuntimeError('Investigate invalid or incorrect service results before timing comparison')
    terminal_audit = []
    for instance in scale:
        requests = [instance['warmup']] + [request for batch in instance['batches'] for request in batch['requests']]
        for request in requests:
            chunks = request.get('chunks', [])
            finishes = [choice.get('finish_reason') for chunk in chunks for choice in chunk.get('choices', [])
                        if choice.get('finish_reason')]
            valid = (request.get('status') == 200 and request.get('correct') is True
                     and 'stop' in finishes and all(x == 'stop' for x in finishes)
                     and not any(chunk.get('error') for chunk in chunks))
            terminal_audit.append(dict(family=instance['family'], unit=instance['independent_unit'],
                                       token=request.get('token'), finish_reasons=finishes, passed=valid))
    save(R / 'results/native-scale-terminal-audit.json', dict(
        profile='matched-file-and-shell-tools', requests=len(terminal_audit),
        passed=all(x['passed'] for x in terminal_audit), records=terminal_audit,
        scope='Posthoc check of stored streamed terminal chunks, not merely HTTP200 or token appearance; no subject rerun.'))
    if not all(x['passed'] for x in terminal_audit):
        raise RuntimeError('Native streamed terminal status requires adjudication')
    out = dict(at=time.time(), scale_instances=len(scale),
               MCP_connections=sum(x['kind'] == 'mcp' for x in mechanisms),
               measurement_profile='matched-file-and-shell-tools',
               source_scale_file=str(scale_file.relative_to(R)), dimensions_graded=False,
               native_stream_terminal_audit='results/native-scale-terminal-audit.json',
               scope='Same native file/shell scope on both whole Gateways; earlier unequal tool-scope timing retained separately and excluded from primary grading.',
               quantitative={})
    pairs = []
    efficiency = []
    for unit in range(1, 7):
        fs = {x['family']: x for x in scale if x['independent_unit'] == unit}
        if set(fs) != {'openclaw', 'hermes'}:
            raise RuntimeError('Missing independent paired Gateway instance')
        for case in ['cold_gateway', 'warm_gateway']:
            values = {f: (x['warmup']['cold_start_to_text_seconds'] if case == 'cold_gateway'
                          else statistics.median(z['first_text_seconds'] for b in x['batches']
                                                 if b['concurrency'] == 1 for z in b['requests']))
                      for f, x in fs.items()}
            pairs.append(dict(unit=f'{unit}-{case}', cluster=f'gateway-{unit}', case=case,
                              oc=values['openclaw'], hermes=values['hermes']))
        for n in [1, 2, 4, 8, 16]:
            values = {}
            for f, x in fs.items():
                base = statistics.mean(b['throughput'] for b in x['batches'] if b['concurrency'] == 1)
                values[f] = statistics.mean(b['throughput'] for b in x['batches'] if b['concurrency'] == n) / (n * base)
            efficiency.append(dict(unit=f'{unit}-N{n}', cluster=f'gateway-{unit}', case=f'N{n}',
                                   oc=values['openclaw'], hermes=values['hermes']))
    out['quantitative']['gateway_first_text'] = dict(
        pairs=pairs, comparison=quant_compare(dict(pairs=pairs), .2, ['cold_gateway', 'warm_gateway']))
    out['quantitative']['scale_efficiency'] = dict(
        pairs=efficiency, comparison=quant_compare(dict(pairs=efficiency, lower_is_better=False), .2,
                                                 ['N1', 'N2', 'N4', 'N8', 'N16']))
    pairs = []
    for unit in range(1, 7):
        fs = {x['family']: x for x in mechanisms if x['kind'] == 'mcp' and x['independent_unit'] == unit}
        if set(fs) != {'openclaw', 'hermes'} or not all(x['passed'] for x in fs.values()):
            raise RuntimeError('Independent native MCP preflight incomplete')
        for n in [1, 4, 8]:
            values = {f: statistics.median(b['duration_ms'] for b in x['batches']
                                          if b['count'] == n and not b['warmup']) for f, x in fs.items()}
            pairs.append(dict(unit=f'{unit}-MCP{n}', cluster=f'connection-{unit}', case=f'MCP{n}',
                              oc=values['openclaw'], hermes=values['hermes']))
    out['quantitative']['MCP_tool_critical_path'] = dict(
        pairs=pairs, comparison=quant_compare(dict(pairs=pairs), .2, ['MCP1', 'MCP4', 'MCP8']))
    save(R / 'results/native-measured-differences.json', out)
    print('MATCHED_NATIVE_QUANTITATIVE_COMPARISONS_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
