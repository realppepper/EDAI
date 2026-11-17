"""Bounded full-scope selection after partial screens; power ties are explicit."""
import math
from .loop_04_extended_policy import ledger
from .harness_04_feedback import implemented_scope_case_ids
from .harness_03_loop import assessment

POWER_ABS_TOL_MW = 1e-6
POWER_REL_TOL = 1e-6


def ranked_candidates(records):
    remaining = [r for r in records if r.get('status') == 'screened']
    ranked = []
    # Feasible partial screens precede numeric partial progress. Neither is final acceptance.
    for feasible in (True, False):
        group = [r for r in remaining if bool(r.get('feasible_for_screening')) == feasible]
        while group:
            if not feasible:
                chosen = min(group, key=lambda r: (r['total_normalized_violation'], r['number']))
            else:
                low = min(r['objective_power_mW'] for r in group)
                if not math.isfinite(low) or low <= 0:
                    raise ValueError('Invalid measured power')
                tied = [r for r in group if abs(r['objective_power_mW'] - low) <= max(POWER_ABS_TOL_MW, abs(low) * POWER_REL_TOL)]
                # Most headroom at the weakest screened performance constraint; stable trial number last.
                chosen = min(tied, key=lambda r: (-r.get('screening_margin', 0), r['number']))
            ranked.append(chosen)
            group.remove(chosen)
    return ranked


def full_assessment(document, policy):
    if document.get('operational_startup',{}).get('required') is not True:
        raise ValueError('Required physical startup gate missing')
    scope = implemented_scope_case_ids(ledger(document), policy)
    if not scope:
        raise ValueError('No qualified implemented scope')
    result = assessment(document, document, scope)
    records = ledger(document)
    result['measurement_integrity_passed'] = all(
        records[k]['case']['status'] in {'passed_sampled_model_case', 'failed_in_model'}
        and not records[k]['case'].get('gate_issues')
        and not any(p.get('gate_issues') for p in records[k]['case'].get('parts', [])) for k in scope)
    return result


def choose_validated(attempts):
    """Caller supplies only source-verified full pipeline receipts in screening rank order."""
    qualified = [a for a in attempts if a['assessment'].get('measurement_integrity_passed', True)]
    if not qualified:
        return None
    return min(qualified, key=lambda a: (not a['assessment']['scope_passed'],
                                       len(a['assessment']['failed_requirement_ids']), a['rank']))


def validate_shortlist(ranked, cap, validate):
    if isinstance(cap, bool) or not isinstance(cap, int) or not 1 <= cap <= 20:
        raise ValueError('Full validation cap must be1..20')
    attempts = []
    for rank, record in enumerate(ranked[:cap]):
        item = validate(record, rank)
        attempts.append(item)
        if item['assessment']['scope_passed']:
            break
    return choose_validated(attempts), attempts
