"""Select a diagnostic batch while retaining the original full-plan inventory."""
from copy import deepcopy


def select_batch(plan, selected_ids=None):
    rows = plan['measurements']
    inventory = [case['case_id'] for row in rows for case in row['cases']]
    if len(inventory) != len(set(inventory)):
        raise ValueError('Duplicate case in source plan')
    if selected_ids is None:
        selected_ids = inventory
        partial = False
    else:
        partial = True
        if not selected_ids or len(selected_ids) != len(set(selected_ids)):
            raise ValueError('Empty or duplicate selected case IDs')
        if not set(selected_ids) <= set(inventory):
            raise ValueError('Selected case is not in the verified source plan')
    selected = set(selected_ids)
    filtered = []
    for row in rows:
        cases = [case for case in row['cases'] if case['case_id'] in selected]
        if cases:
            item = deepcopy(row)
            item['cases'] = deepcopy(cases)
            filtered.append(item)
    return filtered, {'partial_run': partial,
        'full_plan_source_rows': len(rows), 'full_plan_source_cases': len(inventory),
        'selected_case_ids': [key for key in inventory if key in selected],
        'not_executed_case_ids': [key for key in inventory if key not in selected],
        'not_executed_is_not_passed': True}
