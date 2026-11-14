"""Evidence coverage and conservative condition checks; never semantic certification."""
import re
import unicodedata


def normalized(text):
    text = unicodedata.normalize('NFKC', text).replace('−', '-').replace('–', '-')
    text = text.replace('µ', 'u').replace('μ', 'u').replace('Ω', 'Ω')
    return text.casefold()


def evidence_tokens(text):
    # Separate numbers from units so formatting differences do not look like loss.
    return re.findall(r'\d+(?:\.\d+)?|[^\W\d_]{2,}', normalized(text))


def compare_content(source, parsed):
    available = set(evidence_tokens(parsed))
    lines = []
    for line in source.splitlines():
        tokens = set(evidence_tokens(line))
        if not tokens:
            continue
        missing = sorted(tokens - available)
        if missing:
            lines.append({'source_text': line, 'missing_tokens': missing,
                          'status': 'possible_omission_or_notation_change'})
    tokens = set(evidence_tokens(source))
    return {'status': 'review_required' if lines else 'no_token_omission_detected',
            'source_unique_tokens': len(tokens), 'matched_unique_tokens': len(tokens & available),
            'possible_omissions': lines, 'semantic_completeness_verified': False,
            'limitations': 'Token presence cannot prove order, multiplicity, chart coverage or meaning. Native text may itself be incomplete.'}


# Only these simple, explicit assignments are interpreted automatically.
RULES = {
    'supply_voltage_V': ('VS', 'V', 1),
    'ambient_temperature_C': ('TA', '°C', 1),
    'frequency_Hz': ('f', 'Hz', 1),
    'frequency_band_Hz': ('f', 'Hz', 1),
    'closed_loop_gain': ('G', '', 1),
    'load_capacitance_pF': ('CL', 'F', 1e12),
    'output_current_A': ('IO', 'A', 1),
    'output_current_uA': ('IOUT', 'A', 1e6),
    'output_voltage_V': ('VO', 'V', 1),
    'differential_input_voltage_V': ('VID', 'V', 1),
    'measurement_bandwidth_Hz': ('BW', 'Hz', 1),
}


def explicit_quantity(text, symbol, unit, scale=1):
    text = unicodedata.normalize('NFKC', text).replace('−', '-').replace('–', '-')
    text = text.replace('µ', 'u').replace('μ', 'u')
    number = r'([+-]?\s*\d+(?:\.\d+)?)'
    suffix = r'\s*([kMmunp]?)\s*' + re.escape(unit) if unit else ''
    # An optional unit can appear after the first bound as well as the second.
    first_unit = r'(?:\s*[kMmunp]?\s*' + re.escape(unit) + r')?' if unit else ''
    chain = r'(?:\(V\+\)\s*-\s*\(V-\)\s*=\s*)?' if symbol == 'VS' else ''
    pattern = r'(?<![A-Za-z])' + re.escape(symbol) + r'\s*=\s*' + chain + number + first_unit
    pattern += r'(?:\s*(?:to|-)\s*' + number + r')?' + suffix
    if unit:
        pattern += r'(?![A-Za-z])'
    m = re.search(pattern, text)
    if not m:
        return None
    a = float(m.group(1).replace(' ', ''))
    b = float(m.group(2).replace(' ', '')) if m.group(2) is not None else None
    if b is None and re.search(r'\bto\b', text[m.start():]):
        # Native word ordering may put the second bound before the assignment.
        # A truncated range is not a reliable scalar contradiction.
        return None
    prefix = m.group(3) if unit else ''
    factor = {'': 1, 'k': 1e3, 'M': 1e6, 'm': 1e-3, 'u': 1e-6, 'n': 1e-9, 'p': 1e-12}[prefix] * scale
    return ({'min': a*factor, 'max': b*factor} if b is not None else a*factor, m.group(0))


def equal_quantity(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(equal_quantity(a[k], b[k]) for k in a)
    return isinstance(a, (float, int)) and not isinstance(a, bool) and isinstance(b, (float, int)) and abs(a-b) <= 1e-9*max(1, abs(a), abs(b))


def check_conditions(row, condition_sets, page_text):
    conditions = row.get('conditions', {})
    inherited = conditions.get('inherits')
    default = condition_sets.get(inherited, {}) if inherited else {}
    overrides = conditions.get('overrides', {})
    raw = row['original_cell_evidence']['raw_parameter_and_conditions']
    row_text = ' | '.join(c['text'] for c in raw)
    fields = []
    # Verify default and local claims separately. Unrecognised fields stay explicit review.
    header = re.split(r'\bPARAMETER\b', page_text, maxsplit=1)[0]
    for scope, claims, context in [('default', default, header), ('override', overrides, row_text)]:
        for field, value in claims.items():
            if field in ('source_pages', 'applies_unless_overridden'):
                continue
            rule = RULES.get(field)
            found = explicit_quantity(context, *rule) if rule else None
            status = 'review_required'
            if found:
                status = 'explicit_quantity_supported' if equal_quantity(value, found[0]) else 'conflict'
            fields.append({'scope': scope, 'field': field, 'claimed': value, 'status': status,
                           'source_value': found[0] if found else None,
                           'source_excerpt': found[1] if found else None})
    # Reverse check: common explicitly printed local conditions must not silently inherit another value.
    for field, rule in RULES.items():
        if field == 'frequency_band_Hz':
            continue
        found = explicit_quantity(row_text, *rule)
        if found and field not in overrides:
            alias = 'frequency_band_Hz' if field == 'frequency_Hz' else None
            if alias and alias in overrides:
                continue
            fields.append({'scope': 'local_condition_coverage', 'field': field,
                           'source_value': found[0], 'source_excerpt': found[1],
                           'status': 'explicit_quantity_supported' if equal_quantity(default.get(field), found[0]) else 'conflict',
                           'claimed': default.get(field)})
    footnotes = sorted(set(re.findall(r'\((\d+)\)', row_text)))
    return {'status': 'conflict' if any(f['status'] == 'conflict' for f in fields) else 'review_required',
            'fields': fields, 'row_condition_evidence': row_text,
            'footnote_references': footnotes,
            'footnote_context': [line for line in page_text.splitlines() if any('('+n+')' in line for n in footnotes)],
            'semantic_accuracy_verified': False,
            'limitations': 'Explicit assignments only. Rail expressions, inequalities, inherited scope, footnote meaning and product scope require semantic review.'}
