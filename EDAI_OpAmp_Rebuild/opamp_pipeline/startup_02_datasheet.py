"""Fresh PDF stages -> explicit source/policy handoffs -> new DUT -> operational loop."""
import subprocess
import sys
from pathlib import Path
from . import harness_07_workflow as workflow
from . import harness_06_evolution as evolution
from .startup_01_initial_design import admission, make_initial_request, validate_initial
from .harness_01_fixed import DEFAULT_POLICY
from .pipeline_01_verification import ROOT, read, run_pipeline
from .loop_02_handoff import write_json
from .support.execution_state import file_hash, require_current_hkg, require_current_pdg
from .support.source_checks import fingerprint
from .pdg_04_schedule import pdg_signature
from .plan_01_select_targets import source_specs
from .ref_05_research import record_usage
from . import ref_07_datasheet as datasheet_refs


def _save(session,state):
    write_json(Path(session)/'STARTUP_STATE.json',state)
    write_json(Path(session)/'NEXT_ACTION.json',{'status':state['status'],'request':state.get('pending_request')})


def load(session):
    s=read(Path(session)/'STARTUP_STATE.json')
    for p,sha in {**s['code_signatures'],**s['accepted_inputs'],s['pdf_path']:s['pdf_sha256'],
                  s['settings_path']:s['settings_sha256']}.items():
        if file_hash(p)!=sha:raise ValueError('Frozen startup source/input changed: '+p)
    for p,sha in s.get('literature_artifacts',{}).items():
        if file_hash(p)!=sha:raise ValueError('Attached initial literature evidence changed')
    for p,sha in s.get('datasheet_reference_artifacts',{}).items():
        if file_hash(p)!=sha:raise ValueError('Attached initial datasheet reference evidence changed')
    return s


def _command(session,state,name,args):
    logs=Path(session)/'stage_logs';logs.mkdir(exist_ok=True)
    result=subprocess.run([sys.executable,str(ROOT/name),*map(str,args)],cwd=ROOT,capture_output=True,timeout=900)
    index=len(list(logs.glob('*.stdout.txt')))+1
    (logs/f'{index:03d}_{name}.stdout.txt').write_bytes(result.stdout)
    (logs/f'{index:03d}_{name}.stderr.txt').write_bytes(result.stderr)
    if result.returncode:raise RuntimeError(f'{name} failed; inspect {logs}')


def _pending(state,path,status):
    packet=read(path)
    state.update(status=status,pending_request={'path':str(Path(path).resolve()),'sha256':file_hash(path),
        'packet_fingerprint':fingerprint(packet)})


def start(session,pdf,target,settings,env_file=None,max_rounds=2,revisions_per_round=1,optuna_config=None,optuna_trials=4,optuna_rounds=1,optuna_from_designer=False):
    session=Path(session).resolve();session.mkdir(parents=True,exist_ok=True)
    if (session/'STARTUP_STATE.json').exists():raise ValueError('Startup already exists; resume it')
    state={'status':'prepare_document','pdf_path':str(Path(pdf).resolve()),'pdf_sha256':file_hash(pdf),
        'target':target,'document_dir':str(session/'document'),
        'settings_path':str(Path(settings).resolve()),'settings_sha256':file_hash(settings),
        'env_file':str(Path(env_file).resolve()) if env_file else None,
        'code_signatures':{str(p):file_hash(p) for p in [*list((ROOT/'opamp_pipeline').rglob('*.py')),*list(ROOT.glob('run_*.py'))]},
        'accepted_inputs':{},'accepted_replies':[],'pending_request':None,
        'max_rounds':max_rounds,'revisions_per_round':revisions_per_round,
        'history_imported':False,'past_circuit_imported':False,'invalid_initial_responses':0}
    if optuna_config is not None and optuna_from_designer:raise ValueError('Choose fixed or designer sizing mode')
    if optuna_config is not None or optuna_from_designer:
        from .optuna_03_loop_bridge import configure
        from .optuna_04_designer import designer_policy
        state['optuna']=designer_policy(optuna_trials,optuna_rounds) if optuna_from_designer else configure(optuna_config,optuna_trials,optuna_rounds)
        if state['optuna'].get('config_path'):state['accepted_inputs'][state['optuna']['config_path']]=state['optuna']['config_sha256']
    _save(session,state)
    return resume(session)


def resume(session,ltspice=None):
    session=Path(session).resolve();s=load(session);doc=Path(s['document_dir'])
    try:
        if s['status']=='prepare_document':
            inventory=doc/'01_pdf_inventory.json'
            if not inventory.exists():_command(session,s,'run_pdf_overview.py',['--pdf',s['pdf_path'],'--target',s['target'],'--output',doc])
            inv=read(inventory)
            if inv['sha256']!=s['pdf_sha256'] or read(doc/'02_page_plan.json')['target_product']!=s['target']:
                raise ValueError('Prepared document belongs to another PDF/target')
            parsed=doc/'04_parse_summary.json'
            # Existing files in this same fresh job support restart, not old-run imports.
            if not parsed.exists() or not read(parsed).get('all_requested_pages_succeeded'):
                args=['--run-dir',doc]
                if s['env_file']:args+=['--env-file',s['env_file']]
                _command(session,s,'run_pdf_layout.py',args)
            packet=doc/'spec_pipeline/spec_02_input_packet.json'
            if not packet.exists():_command(session,s,'run_spec_pipeline.py',['--run-dir',doc])
            _pending(s,packet,'awaiting_spec_annotations')
        elif s['status']=='validating_initial_design':
            if not ltspice:raise ValueError('LTspice required for initial validation')
            folder=session/'initial/validation'
            run_pipeline(session/'initial/candidate.inc',doc,folder,ltspice,resume=(folder/'STATE.json').exists())
            s['status']='starting_operational_loop';_save(session,s)
        if s['status']=='starting_operational_loop':
            loop=session/'workflow'
            if not (loop/'STATE.json').exists():
                sizing=s.get('optuna',{})
                workflow.start(loop,session/'initial/validation',session/'initial/candidate.inc',doc,
                    s.get('initial_policy',str(DEFAULT_POLICY)),s['max_rounds'],s['revisions_per_round'],
                    sizing.get('config_path'),sizing.get('trials',4),sizing.get('max_rounds',1),sizing.get('mode')=='designer_proposal')
            s.update(status='operational_loop',workflow_session=str(loop),pending_request=None)
        if s['status']=='operational_loop':
            nested=workflow.resume(s['workflow_session'],ltspice) if ltspice else workflow.load(s['workflow_session'])
            s['workflow_status']=nested['status'];s['pending_request']=nested.get('pending_request')
            if nested['status']=='implemented_scope_passed':
                from .schematic_01_export import complete
                complete(session,s,nested['active'])
        s.pop('last_error',None);_save(session,s);return s
    except Exception as error:
        s['last_error']={'type':type(error).__name__,'message':str(error)};_save(session,s);raise


def submit(session,response_path):
    session=Path(session).resolve();s=load(session);path=Path(response_path).resolve();sha=file_hash(path)
    if sha in s['accepted_replies']:return resume(session)
    if s['status']=='operational_loop':raise ValueError('Use run_opamp_workflow.py for the emitted workflow request')
    phase=s['status'];reply=read(path);doc=Path(s['document_dir'])
    if not s.get('pending_request') or file_hash(s['pending_request']['path'])!=s['pending_request']['sha256']:
        raise ValueError('No current intact startup request')
    receipt=session/'responses'/f'{len(s["accepted_replies"]):03d}_{phase}_{sha[:12]}.json'
    evolution._put(receipt,path.read_bytes())
    if phase in {'awaiting_spec_annotations','awaiting_spec_correction'}:
        _command(session,s,'run_spec_pipeline.py',['--run-dir',doc,'--annotations',receipt])
        s['annotations_path']=str(receipt)
        _pending(s,doc/'spec_pipeline/spec_03_llm_input_packet.json','awaiting_semantic_review')
    elif phase=='awaiting_semantic_review':
        _command(session,s,'run_spec_pipeline.py',['--run-dir',doc,'--annotations',s['annotations_path'],'--semantic-review',receipt])
        summary=read(doc/'spec_pipeline/spec_03_verification.json')['summary']
        if any(summary.get(k,0) for k in ('conflict_rows','llm_needs_change_rows','llm_pending_rows','open_correction_proposals','source_rows_missing_from_document')):
            _pending(s,doc/'spec_pipeline/spec_02_input_packet.json','awaiting_spec_correction')
        else:
            _command(session,s,'run_hkg.py',['--run-dir',doc,'--spec-only'])
            _command(session,s,'run_pdg.py',['--run-dir',doc])
            _pending(s,doc/'pdg_pipeline/pdg_01_input_packet.json','awaiting_pdg_annotations')
    elif phase=='awaiting_pdg_annotations':
        _command(session,s,'run_pdg.py',['--run-dir',doc,'--annotations',receipt])
        hkg=require_current_hkg(doc);pdg=require_current_pdg(doc)
        packet={'input_hkg_fingerprint':fingerprint(hkg),'input_pdg_signature':pdg_signature(pdg),
            'target_product':s['target'],'evaluation_temperature_C':25,
            'rows':source_specs(hkg),'engineering_defaults':read(s['settings_path']),
            'instructions':'Return input_hkg_fingerprint,input_pdg_signature,row_decisions only. Every source row needs include/defer_temperature_coefficient/not_separate_temperature_variant and reason; temperature variants reference a primary included row. No source values or engineering defaults may be changed.'}
        target=session/'PROJECT_POLICY_REQUEST.json';write_json(target,packet)
        _pending(s,target,'awaiting_project_policy')
    elif phase=='awaiting_project_policy':
        packet=read(s['pending_request']['path'])
        if set(reply)!={'input_hkg_fingerprint','input_pdg_signature','row_decisions'}:raise ValueError('Unexpected project-policy response')
        policy={**reply,'target_product':s['target'],'evaluation_temperature_C':25,
            'origin':'fresh_source_reviewed_project_policy','engineering_defaults':read(s['settings_path'])}
        p=session/'PROJECT_POLICY.json';write_json(p,policy)
        _command(session,s,'run_measurement_plan.py',['--run-dir',doc,'--project-policy',p])
        selection=read(doc/'measurement_plan/plan_01_target_selection.json');plan=read(doc/'measurement_plan/plan_02_measurements.json')
        checked=admission(doc,selection,plan);write_json(session/'DESIGN_ADMISSION.json',checked)
        if not checked['admitted']:raise ValueError('Source-reviewed design admission blocked')
        initial_policy=session/'initial/harness.json';evolution._put(initial_policy,DEFAULT_POLICY.read_bytes())
        request=make_initial_request(plan,checked,initial_policy,doc)
        target=session/'initial/REQUEST.json';write_json(target,request)
        s['initial_policy']=str(initial_policy);_pending(s,target,'awaiting_initial_design')
    elif phase=='awaiting_initial_design':
        request=read(s['pending_request']['path'])
        try:validate_initial(request,reply,s['pending_request']['sha256'])
        except ValueError as error:
            s['invalid_initial_responses']+=1;s['last_error']={'type':'InvalidInitialResponse','message':str(error)}
            if s['invalid_initial_responses']>=3:s.update(status='invalid_initial_response_budget_exhausted',pending_request=None)
            _save(session,s);raise
        evolution._put(session/'initial/candidate.inc',reply['netlist'].encode('ascii'))
        record_usage(s,request,reply)
        datasheet_refs.record_usage(s,request,reply)
        s.update(status='validating_initial_design',pending_request=None)
    else:raise ValueError('No supported pending startup response')
    s['accepted_inputs'][str(receipt)]=sha;s['accepted_replies'].append(sha)
    _save(session,s);return s
