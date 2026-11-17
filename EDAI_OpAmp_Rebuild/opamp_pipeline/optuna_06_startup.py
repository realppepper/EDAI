"""Numeric startup evidence; incomplete simulation is never a physical violation."""
import math
import re
from pathlib import Path
from .diag_02_startup_seed import internal_nodes, startup_deck
from .tb_05_waveform_metrics import read_real_raw
from .support.execution_state import file_hash


def observe(raw, supply, nodes):
    times = raw['time']
    if len(times) < 2 or not all(math.isfinite(t) for t in times):
        raise ValueError('Invalid startup time axis')
    if times[0] > 1e-12 or any(b < a for a, b in zip(times, times[1:])) or times[-1] < 99.98e-6:
        raise ValueError('Incomplete physical startup')
    tail = [i for i, t in enumerate(times) if t >= 80e-6]
    names = [f'v(xdut:{n.lower()})' for n in nodes] + ['v(out)']
    for name in names:
        series = raw[name]
        if len(series) != len(times) or not all(math.isfinite(v) for v in series):
            raise ValueError('Missing/nonfinite startup waveform')
    seeds = {n.lower(): raw[f'v(xdut:{n.lower()})'][-1] for n in nodes}
    span = max(max(raw[name][i] for i in tail) - min(raw[name][i] for i in tail) for name in names[:-1])
    out, bias = raw['v(out)'][-1], seeds['bias']
    # The bias rule is strictly > .65, including at its boundary.
    constraints = {'tail_span': (span - .005) / .005,
                   'output_midpoint': (abs(out - supply / 2) - .01) / .01,
                   'active_bias': (.65 - bias) / .65 if bias != .65 else math.ulp(1.0)}
    if not all(math.isfinite(v) for v in constraints.values()):
        raise ValueError('Startup constraint overflow')
    return {'supply_V': supply, 'passed': all(v <= 0 for v in constraints.values()),
            'details': {'max_internal_tail_span_V': span, 'output_final_V': out, 'bias_final_V': bias},
            'constraints': constraints}, seeds


def startup_feedback(cases):
    constraints = {f"startup:{c['supply_V']:.12g}:{k}": v for c in cases for k, v in c['constraints'].items()}
    values = [max(0, v) for v in constraints.values()]
    if not values:
        raise ValueError('No complete startup observations')
    return {'policy': 'physical_startup_normalized_v1', 'constraints': constraints,
            'total_normalized_violation': sum(values), 'worst_normalized_violation': max(values)}


def repair_evidence(startup, model, expected_sha):
    """Recheck existing raw evidence and DUT identity before offering startup sizing."""
    try:
        if startup.get('passed') is not False or not startup.get('required') or not startup.get('cases'):
            return False
        if file_hash(model) != expected_sha:
            return False
        cases = startup['cases']
        if sorted(c['supply_V'] for c in cases) != startup['supplies_V']:
            return False
        observed = []
        for case in cases:
            paths = [Path(p) for p in case['artifact_paths'] if Path(p).suffix == '.cir']
            if len(paths) != 1:
                return False
            deck = paths[0].read_text(encoding='ascii')
            includes = re.findall(r'^\.include "([^"]+)"$', deck, re.M)
            if len(includes) != 1 or file_hash(includes[0]) != expected_sha:
                return False
            if deck != startup_deck(includes[0], case['supply_V']):
                return False
            item, _ = observe(read_real_raw(paths[0].with_suffix('.raw')), case['supply_V'],
                              internal_nodes(Path(model).read_text(encoding='ascii')))
            if item['passed'] != case['passed']:
                return False
            observed.append(item)
        return any(not item['passed'] for item in observed)
    except (ValueError, OSError, KeyError, TypeError, IndexError):
        return False
