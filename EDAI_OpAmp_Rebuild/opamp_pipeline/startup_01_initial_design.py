"""Source-reviewed project admission and an initial design request with no seed DUT."""
from copy import deepcopy
from pathlib import Path
from .ref_05_research import tool_contract,validate_usage
from . import ref_07_datasheet as datasheet_refs
from .design_01_cmos_candidate import MODELS
from .harness_01_fixed import load_harness, system_text, validate_candidate
from .support.execution_state import require_current_spec, require_current_hkg, require_current_pdg
from .support.source_checks import fingerprint


def admission(run_dir, selection, plan):
    run = Path(run_dir)
    document = require_current_spec(run, run/'spec_pipeline/spec_03_result.json')
    hkg = require_current_hkg(run); pdg = require_current_pdg(run)
    rows = {r['id']:r for r in document['electrical_specs']}
    selected = {x['row_id'] for x in selection['items'] if x['required_in_project']}
    if {m['row_id'] for m in plan['measurements']} != selected:
        raise ValueError('Selected targets and measurement plan differ')
    policy, _ = load_harness()
    supported = set(policy['qualified_measurement_families'])
    operational_rows = {m['row_id'] for m in plan['measurements'] if m['method']['kind'] in supported}
    blockers = []; deferred = []
    for key in selected:
        v = rows[key]['verification']
        if (v['status'] == 'conflict' or v.get('open_correction_proposals')
                or v.get('llm_semantic_review',{}).get('status') != 'reviewed_match'):
            (blockers if key in operational_rows else deferred).append(key)
    if document['verification_summary'].get('source_rows_missing_from_document', 0):
        blockers.append('source_row_coverage')
    return {'admitted':not blockers, 'blocked_row_ids':blockers,
        'meaning':'Reviewed project subset only; no global extraction/fabrication guarantee.',
        'target_product':document['target_product'], 'source_sha256':document['source_sha256'],
        'source_ready_for_design_flag_preserved':document['ready_for_design'],
        'selected_rows':len(selected), 'all_source_rows':len(rows),
        'operational_source_rows':sorted(operational_rows),
        'deferred_source_review_row_ids':deferred,
        'reference_channels':pdg['summary']['channels'], 'designed_channels':1,
        'characteristic_curve_numeric_targets_used':False,
        'hkg_fingerprint':fingerprint(hkg), 'pdg_fingerprint':fingerprint(pdg)}


def make_initial_request(plan, admitted, policy_path, run_dir=None):
    if not admitted.get('admitted'): raise ValueError('Project inputs need source review')
    policy, sha = load_harness(policy_path)
    requirements = []
    for m in plan['measurements']:
        item={k:deepcopy(m[k]) for k in
            ('row_id','symbol','source','target','method','resolved_conditions','cases')}
        item['required_for_implemented_scope']=m['row_id'] in admitted['operational_source_rows']
        item['source_review_deferred']=m['row_id'] in admitted['deferred_source_review_row_ids']
        requirements.append(item)
    request = {'schema_version':1, 'mode':'fresh_initial_opamp_design',
        'admission':deepcopy(admitted), 'requirements':requirements,
        'system_instructions':system_text(policy), 'harness_sha256':sha,
        'frozen_model_prefix':MODELS,
        'dut_interface':'FIRSTAMP P N VP VM OUT',
        'constraints':['Generate a new topology and sizing from the supplied requirements; there is no starting circuit.',
            'Do not read local previous designs, examples, successful values, prior runs or design generators. External literature is permitted only through an explicitly supplied source-bound reference packet.',
            'Preserve the frozen model prefix verbatim; use only physical M/R/C inside the one-channel DUT.',
            'Use supply pins VP/VM internally, retain an observable BIAS node, provide physical bias and startup.',
            'Generic LEVEL1 at25C only. A dual reference product does not make this one-channel DUT dual.',
            'The host owns all measurements and pass/fail; retain unsupported requirements as unverified.'],
        'past_designs_provided':False, 'past_measurements_provided':False,
        'response_schema':{'request_id':'echo exactly', 'request_sha256':'SHA256 of this request file',
            'netlist':'complete ASCII netlist beginning with frozen_model_prefix',
            'summary':'architecture and sizing rationale; no measured success claim',
            'hypotheses':'list of {case_ids,claim,probe}', 'tradeoffs':'list of risks'},
        'external_designer_api_calls':0}
    request['optional_literature_research']=tool_contract()
    datasheet_refs.add_catalog(request,run_dir)
    request['request_id'] = fingerprint(request)
    return request


def validate_initial(request, response, request_sha256):
    validate_usage(request,response)
    datasheet_refs.validate_usage(request,response)
    if response.get('request_id') != request['request_id'] or response.get('request_sha256') != request_sha256:
        raise ValueError('Initial design is not bound to its request')
    if not isinstance(response.get('summary'),str) or not response['summary'].strip():
        raise ValueError('Initial architecture rationale required')
    if not isinstance(response.get('netlist'),str):raise ValueError('Complete initial netlist required')
    validate_candidate(response['netlist'])
    if not isinstance(response.get('hypotheses',[]),list) or not isinstance(response.get('tradeoffs',[]),list):
        raise ValueError('Hypotheses and tradeoffs must be lists')
    known = {c['case_id'] for r in request['requirements'] for c in r['cases']}
    for h in response.get('hypotheses',[]):
        if not set(h.get('case_ids',[])) <= known: raise ValueError('Unknown hypothesis case')
    return True
