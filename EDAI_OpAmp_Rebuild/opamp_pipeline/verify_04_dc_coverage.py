"""Require every declared sample of an adapter's numeric one-source DC sweep."""
import math
import re
from pathlib import Path


class IncompleteDCSweep(ValueError):
    def __init__(self, coverage):
        self.coverage = coverage
        super().__init__(
            'Incomplete/invalid DC sweep: '
            f"{coverage['unique_expected_points_observed']}/{coverage['expected_points']} declared samples; "
            f"missing={coverage['missing_count']}, unexpected={coverage['unexpected_count']}, "
            f"direction_errors={coverage['direction_errors']}; "
            f"first missing={coverage['missing_samples'][:8]}")


def dc_sweep_coverage(path, raw):
    """Read the executed contract, not the reported number of raw points.

    Current adapters emit decimal numeric linear .dc sweeps. Nested, parameter,
    or logarithmic sweeps require a separate explicitly supported contract.
    Repeated endpoints are allowed, but cannot substitute for missing samples.
    """
    commands = re.findall(r'^\s*\.dc\s+([^\r\n]+)', Path(path).read_text(encoding='ascii'), re.M | re.I)
    if len(commands) != 1:
        raise ValueError('Exactly one declared numeric DC sweep is required')
    fields = commands[0].split()
    if len(fields) != 4:
        raise ValueError('Only one-source numeric linear DC sweeps are qualified')
    source = fields[0].lower()
    start, stop, step = map(float, fields[1:])
    if not all(math.isfinite(v) for v in (start, stop, step)) or step == 0:
        raise ValueError('Nonfinite/zero DC sweep step')
    intervals = (stop - start) / step
    if not 0 <= intervals <= 1000000:
        raise ValueError('Invalid DC sweep direction or size')
    count = math.floor(intervals + 1e-8) + 1
    expected = [start + i * step for i in range(count)]
    if source not in raw:
        raise ValueError('DC independent source coordinate missing from raw file: ' + source)
    axis = raw[source]
    tolerance = max(1e-12, abs(step) * 1e-6)
    if any(not math.isfinite(v) for v in axis):
        raise ValueError('Nonfinite DC independent coordinate')
    found = set()
    unexpected = []
    for value in axis:
        index = round((value - start) / step)
        if 0 <= index < count and abs(value - expected[index]) <= tolerance:
            found.add(index)
        else:
            unexpected.append(value)
    missing = [value for i, value in enumerate(expected) if i not in found]
    direction_errors = sum((b - a) * (1 if step > 0 else -1) < -tolerance for a, b in zip(axis, axis[1:]))
    return {'source': source, 'start': start, 'stop': stop, 'step': step,
            'expected_points': count, 'observed_points': len(axis),
            'unique_expected_points_observed': len(found),
            'duplicate_expected_points': len(axis) - len(unexpected) - len(found),
            'missing_count': len(missing), 'missing_samples': missing,
            'unexpected_count': len(unexpected), 'unexpected_samples': unexpected,
            'direction_errors': direction_errors,
            'complete': not missing and not unexpected and not direction_errors}


def require_complete_dc_sweep(path, raw):
    coverage = dc_sweep_coverage(path, raw)
    if not coverage['complete']:
        raise IncompleteDCSweep(coverage)
    return coverage


def require_complete_vcm_case(fixture, parts):
    """Qualify the union against the original full grid before judging tracking.

    Two individually complete short sweeps must not silently narrow the range.
    This is a DC continuation policy, not proof of cold startup at every input.
    """
    limits = fixture['input_common_mode_sweep_V']
    lo, hi = limits['min'], limits['max']
    delta = (hi - lo) / 200
    midpoint = lo + 100 * delta
    if len(parts) == 1:
        contracts = [(parts[0], lo, hi, delta, 201)]
    elif len(parts) == 2 and {p.get('variant') for p in parts} == {'lower', 'upper'}:
        by_variant = {p['variant']: p for p in parts}
        contracts = [(by_variant['lower'], midpoint, lo, -delta, 101),
                     (by_variant['upper'], midpoint, hi, delta, 101)]
        first = [p['metrics']['initial_output_V'] for p in parts]
        if abs(first[0] - first[1]) > 1e-8:
            raise ValueError('VCM continuation branches disagree at the shared midpoint')
    else:
        raise ValueError('VCM requires the full grid or both center-out branches')
    tolerance = max(1e-12, abs(delta) * 1e-6)
    for part, start, stop, step, count in contracts:
        coverage = part.get('metrics', {}).get('dc_sweep_coverage', {})
        if (not coverage.get('complete') or coverage.get('expected_points') != count or
            coverage.get('unique_expected_points_observed') != count or
            coverage.get('source') != 'vin' or
            any(abs(coverage.get(k, math.inf) - expected) > tolerance
                for k, expected in [('start', start), ('stop', stop), ('step', step)])):
            raise ValueError('VCM sample coverage differs from the immutable full-range contract')
    return {'complete': True, 'unique_full_grid_points': 201,
            'policy': 'center_out_complete_grid_v1' if len(parts) == 2 else 'full_ascending',
            'cold_startup_at_each_input_verified': False}


def collect_vcm_with_numerical_fallback(collect):
    """Retry only an incomplete measurement/solver failure, never a valid miss.

    Both strategies must independently cover the same original 201-point grid.
    Spec verdicts are evaluated after this function; they do not select a path.
    """
    from .diag_03_solver_attempts import SolverAttemptsError
    attempts = []
    try:
        parts = collect(('lower', 'upper'))
    except (IncompleteDCSweep, SolverAttemptsError) as error:
        attempts.append({'policy': 'center_out_complete_grid_v1', 'status': 'numerical_or_coverage_error',
                         'error': str(error), 'coverage': getattr(error, 'coverage', None)})
    else:
        return parts, [{'policy': 'center_out_complete_grid_v1', 'status': 'computed'}]
    try:
        parts = collect(('default',))
    except Exception as error:
        attempts.append({'policy': 'full_ascending', 'status': 'error', 'error': str(error),
                         'coverage': getattr(error, 'coverage', None)})
        error.numerical_attempts = attempts
        raise
    attempts.append({'policy': 'full_ascending', 'status': 'computed'})
    return parts, attempts
