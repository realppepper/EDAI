"""Read-only circuit diagnosis: individual DC points, not sweep qualification."""
import math, re


def point_deck(source, voltage, model, policy):
    if policy not in {'original_startup_hint', 'normal_no_hint'}:
        raise ValueError('Unknown diagnostic policy')
    if not math.isfinite(voltage):
        raise ValueError('Nonfinite voltage')
    commands = re.findall(r'^\.dc\s+VIN\s+(\S+)\s+(\S+)\s+(\S+)\s*$', source, re.M | re.I)
    if len(commands) != 1:
        raise ValueError('Expected one VIN sweep')
    start, stop, _ = map(float, commands[0])
    if not min(start, stop)-1e-12 <= voltage <= max(start, stop)+1e-12:
        raise ValueError('Point outside original sweep')
    if len(re.findall(r'^VIN\s+inp\s+0\s+\S+\s*$', source, re.M | re.I)) != 1:
        raise ValueError('Unknown stimulus connection')
    deck, count = re.subn(r'^\.include\s+"[^"\r\n]+"', lambda _: f'.include "{model}"', source, flags=re.M | re.I)
    if count != 1:
        raise ValueError('Expected exactly one DUT include')
    deck = re.sub(r'^VIN\s+inp\s+0\s+\S+\s*$', lambda _: f'VIN inp 0 {voltage:.17g}', deck, flags=re.M | re.I)
    deck = re.sub(r'^\.dc[^\r\n]*', '.op', deck, flags=re.M | re.I)
    deck = re.sub(r'^\.save[^\r\n]*', '.save V(out) V(inp) V(inn) I(VSENSE) I(VDD) V(xdut:bias) V(xdut:x) V(xdut:boost)', deck, flags=re.M | re.I)
    if policy == 'normal_no_hint':
        deck = re.sub(r'^\.nodeset[^\r\n]*\r?\n?', '', deck, flags=re.M | re.I)
        deck = re.sub(r'^\.options solver=alt\s*\r?\n?', '', deck, flags=re.M | re.I)
    return '* Individual-point diagnostic; does not qualify the original full sweep\n'+deck


def assess_point(raw, requested, tracking_limit):
    needed = ['v(inp)', 'v(out)', 'v(inn)', 'i(vdd)', 'v(xdut:bias)']
    if any(key not in raw or len(raw[key]) != 1 or not math.isfinite(raw[key][0]) for key in needed):
        raise ValueError('Missing/nonfinite/multiple operating-point values')
    if abs(raw['v(inp)'][0]-requested) > 1e-9:
        raise ValueError('Requested input was not applied')
    output = raw['v(out)'][0]
    error = abs(output-requested)
    return {'classification': 'computed_tracking_within_limit' if error <= tracking_limit else 'computed_tracking_outside_limit',
        'input_V': requested, 'output_V': output, 'tracking_error_V': error,
        'tracking_limit_V': tracking_limit, 'bias_V': raw['v(xdut:bias)'][0],
        'supply_current_A': -raw['i(vdd)'][0],
        'bias_and_current_are_diagnostics_not_additional_pass_rules': True,
        'full_sweep_qualified': False, 'physical_failure_cause_confirmed': False}
