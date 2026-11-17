"""Source-bound screening using the existing calibrated measurement adapters."""
import json
from pathlib import Path
from .support.execution_state import require_current_hkg,require_current_pdg,file_hash
from .support.source_checks import fingerprint
from .plan_01_select_targets import select_targets
from .plan_04_validate import validate_plan
from .verify_01_fixtures import build_fixture
from .verify_02_metrics import measure
from .validation_03_execution_contract import validate_execution,ExecutionContractError
from .validation_05_special_fixtures import startup_meta
from .diag_02_startup_seed import startup_deck,internal_nodes,seeds_from_waveform,seeded_deck
from .tb_05_waveform_metrics import read_real_raw
from .tb_02_ltspice import run_bench
from .validation_01_results import save_report
from .optuna_01_parameters import physical_score
from .optuna_06_startup import observe,startup_feedback


def load_plan(run_dir):
    run_dir=Path(run_dir);folder=run_dir/'measurement_plan'
    read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
    hkg=require_current_hkg(run_dir);pdg=require_current_pdg(run_dir)
    status=read(folder/'STATUS.json')
    if not status.get('completed') or fingerprint(read(folder/'MEASUREMENT_PLAN.json'))!=status['final_document_fingerprint']:raise ValueError('Incomplete/changed measurement plan')
    for item in status['inputs']:
        if file_hash(item['path'])!=item['sha256']:raise ValueError('Measurement plan input changed')
    policy=read(status['inputs'][0]['path']);selection=read(folder/'plan_01_target_selection.json')
    plan=read(folder/'plan_02_measurements.json')
    if selection!=select_targets(hkg,pdg,policy):raise ValueError('Target selection differs')
    validate_plan(selection,plan,read(folder/'plan_03_execution_policies.json'),hkg,pdg,policy['engineering_defaults'])
    return plan


class NativeExecutor:
    def __init__(self,out,executable,timeout=30):
        self.out=Path(out);self.executable=executable;self.timeout=timeout;self.jobs=[]

    def __call__(self,label,deck,meta):
        folder=self.out/'jobs'/label;folder.mkdir(parents=True,exist_ok=False)
        path=folder/'bench.cir';path.write_text(deck,encoding='ascii')
        meta['execution_contract_receipt_dir']=str(self.out/'execution_contracts')
        validate_execution(deck,meta,phase='optuna_preflight')
        job={'label':label,'path':str(path),'status':'started'};self.jobs.append(job)
        save_report(self.out/'JOBS.json',self.jobs)
        try:
            result=run_bench(self.executable,path,meta['names'],ascii_raw=meta['analysis']!='noise',timeout=self.timeout)
        except Exception as error:
            job.update(status='error',error_type=type(error).__name__,error=str(error));save_report(self.out/'JOBS.json',self.jobs);raise
        job.update(status='completed',artifacts={str(p):file_hash(p) for p in folder.iterdir() if p.is_file()})
        save_report(self.out/'JOBS.json',self.jobs)
        return {'path':path,'measurements':result['measurements']}


def screen_candidate(model,plan,kinds,out,executable,timeout=30):
    """Partial screening only; never call this a full-datasheet verification."""
    from run_extended_verification import case_verdict
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    allowed={'iq','gbw','pm','sr'}
    if not kinds or len(set(kinds))!=len(kinds) or not set(kinds)<=allowed or 'iq' not in kinds:raise ValueError('Unsupported screening selection')
    rows=[m for m in plan['measurements'] if m['method']['kind'] in kinds]
    if set(m['method']['kind'] for m in rows)!=set(kinds):raise ValueError('A requested screening quantity is absent from the source plan')
    execute=NativeExecutor(out,executable,timeout)
    state={'status':'running','cases':[],'startup':[],'partial_screening_only':True,'all_datasheet_requirements_passed':False}
    save=lambda:save_report(out/'SCREENING.json',state)
    save();seeds={}
    try:
        supplies=sorted({c['fixture']['supply_voltage_V'] for m in plan['measurements'] for c in m['cases']})
        for supply in supplies:
            meta=startup_meta(model,supply)
            job=execute('startup_'+format(supply,'.12g'),startup_deck(model,supply),meta)
            validate_execution(job['path'].read_text(encoding='ascii'),meta,phase='optuna_startup_before_metric')
            observation,seed=observe(read_real_raw(job['path'].with_suffix('.raw')),supply,internal_nodes(Path(model).read_text(encoding='ascii')))
            if observation['passed']:seeds[supply]=seed
            observation['artifacts']={str(p):file_hash(p) for p in job['path'].parent.iterdir() if p.is_file()}
            state['startup'].append(observation);save()
        state['startup_constraint_feedback']=startup_feedback(state['startup'])
        if not all(c['passed'] for c in state['startup']):
            state.update(status='startup_failed',feasible_for_screening=False,objective_power_mW=None,
                         failed_screening_case_ids=['OPERATIONAL-STARTUP'],physical_spec_failure_established=True)
            save();return state
        for index,item in enumerate(rows):
            kind=item['method']['kind']
            for case_index,case in enumerate(item['cases']):
                parts=[]
                for variant in ('rising','falling') if kind=='sr' else ('default',):
                    deck,meta=build_fixture(model,item,case,variant)
                    deck=seeded_deck(deck,seeds[case['fixture']['supply_voltage_V']],case['fixture']['rails_V']['V_minus'])
                    job=execute(f'{index:03d}_{kind}_{case_index:03d}_{variant}',deck,meta)
                    measured=measure(job['path'],kind,case['fixture'],meta,job['measurements'])
                    measured.update(variant=variant,job_path=str(job['path']));parts.append(measured)
                verdict=case_verdict(item,case,parts);verdict['kind']=kind
                state['cases'].append(verdict);save()
        state.update(status='completed',**physical_score(state['cases']))
        save();return state
    except Exception as error:
        state.update(status='execution_error',error_type=type(error).__name__,error=str(error),physical_spec_failure_established=False)
        save();raise
