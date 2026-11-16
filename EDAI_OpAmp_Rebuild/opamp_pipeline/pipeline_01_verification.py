"""One entry for core, input impedance and overload; imported chains are hash-bound."""
import json,subprocess,sys,time
from pathlib import Path
from .loop_02_handoff import write_json
from .harness_01_fixed import validate_candidate,DEFAULT_POLICY
from .harness_02_request import make_request
from .loop_04_extended_policy import ledger
from .support.execution_state import file_hash
from .support.atomic_files import atomic_write_bytes
from .verify_07_startup_gate import startup_gate

ROOT=Path(__file__).resolve().parents[1]
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def verify_manifest(folder):
    for relative,sha in read(Path(folder)/'ARTIFACTS.json')['files'].items():
        if file_hash(Path(folder)/relative)!=sha:raise ValueError('Changed stage artifact: '+relative)


def check_chain(core,impedance,overload,model,plan):
    core,impedance,overload=map(Path,(core,impedance,overload));a,b,c=map(read,(core,impedance,overload))
    model_sha=file_hash(model)
    if a['status']!='completed_with_explicit_unverified_cases' or not a['calibration_passed']:raise ValueError('Core stage incomplete')
    for path,sha in a['input_signatures'].items():
        if file_hash(path)!=sha:raise ValueError('Core input/code changed: '+path)
    for job in a['job_cache'].values():
        if job.get('completed'):
            for path,sha in job['artifacts'].items():
                if file_hash(path)!=sha:raise ValueError('Core execution artifact changed')
    if file_hash(core.parent/'candidate.inc')!=model_sha:raise ValueError('Core DUT differs')
    if a['input_signatures'].get(str(Path(plan).resolve()))!=file_hash(plan):raise ValueError('Source plan differs')
    cal=read(core.parent/'ADAPTER_VALIDATION.json')
    if cal['status']!='passed' or len(cal['checks'])!=23 or not all(x['passed'] for x in cal['checks']):raise ValueError('Core reference qualification incomplete')
    dc_cal=cal.get('dc_grid_validation',[])
    dc_policies={'center_out_complete_grid_v1','full_ascending'}
    if (len(dc_cal)!=4 or not all(c.get('passed') and c.get('coverage',{}).get('complete') and c['coverage'].get('unique_full_grid_points')==201 for c in dc_cal)
            or {c.get('policy') for c in dc_cal}!=dc_policies
            or any({c.get('expected_spec_pass') for c in dc_cal if c.get('policy')==policy}!={True,False} for policy in dc_policies)):
        raise ValueError('DC complete-grid reference qualification incomplete')
    if b['status']!='extension_completed_with_explicit_model_limitations' or len(b['calibration'])!=2 or not all(x['passed'] for x in b['calibration']):raise ValueError('Impedance stage unqualified')
    if Path(b['baseline_result']).resolve()!=core.resolve() or b['baseline_sha256']!=file_hash(core) or b['candidate_sha256']!=model_sha:raise ValueError('Impedance chain differs')
    if c['status']!='extension_completed' or len(c['calibration'])!=4 or not all(x['qualified'] for x in c['calibration']) or {x['expected_spec_pass'] for x in c['calibration']}!={True,False}:raise ValueError('Overload stage unqualified')
    if Path(c['baseline_path']).resolve()!=(impedance.parent/'COMBINED_LEDGER.json').resolve() or c['baseline_sha256']!=file_hash(impedance.parent/'COMBINED_LEDGER.json') or c['model_sha256']!=model_sha:raise ValueError('Overload chain differs')
    for path in (impedance,overload):verify_manifest(path.parent)
    result=read(overload.parent/'COMBINED_LEDGER.json')
    source_ids={x['case_id'] for r in read(plan)['measurements'] for x in r['cases']}
    if set(ledger(result))!=source_ids:raise ValueError('Final case coverage differs')
    counts={s:sum(c['case']['status']==s for c in ledger(result).values()) for s in {x['case']['status'] for x in ledger(result).values()}}
    if counts!=result['case_status_counts']:raise ValueError('Reported counts differ from actual cases')
    result['operational_startup']=startup_gate(a,read(plan))
    return result


def run_pipeline(model,run_dir,out,ltspice=None,imports=None,resume=False,harness=DEFAULT_POLICY):
    model,run_dir,out,harness=map(lambda p:Path(p).resolve(),(model,run_dir,out,harness));validate_candidate(model.read_text(encoding='ascii'))
    plan=run_dir/'measurement_plan/plan_02_measurements.json'
    signature={str(p):file_hash(p) for p in (model,plan,harness,Path(__file__),ROOT/'opamp_pipeline/harness_01_fixed.py',ROOT/'opamp_pipeline/harness_02_request.py')}
    out.mkdir(parents=True,exist_ok=True);statepath=out/'STATE.json'
    if statepath.exists():
        if not resume:raise ValueError('Existing pipeline; use resume')
        state=read(statepath)
        if state['inputs']!=signature:raise ValueError('Pipeline inputs/code changed')
        if state['status']=='completed':
            for p,sha in state['outputs'].items():
                if file_hash(p)!=sha:raise ValueError('Completed pipeline output changed')
            return state
    else:
        state={'status':'started','inputs':signature,'stages':{},'execution_seconds':0,'external_llm_api_calls':0,'chat_token_usage':None,
               'imported_readonly_chain':bool(imports),'harness_sha256':file_hash(harness),'full_datasheet_success':False}
    save=lambda:write_json(statepath,state);save()
    def child(name,script,args,expected):
        stage=state['stages'].get(name)
        if stage and stage.get('completed'):
            if file_hash(stage['result'])!=stage['sha256']:raise ValueError('Recorded stage result changed')
            return Path(stage['result'])
        folder=out/name;folder.mkdir(exist_ok=True)
        if name=='core':
            dest=folder/'execution';extra=['--resume',str(dest)] if (dest/'RESULT.json').exists() else ['--output-dir',str(dest)]
        else:
            index=len(list(folder.glob('attempt_*')))+1;dest=folder/f'attempt_{index:03d}';extra=['--output-dir',str(dest)]
        state['status']='running_'+name;state['stages'][name]={'completed':False,'output':str(dest)};save()
        history=state.setdefault('stage_attempts',{}).setdefault(name,[])
        existing=[int(p.name.rsplit('_',1)[1]) for p in folder.glob('process_attempt_*') if p.is_dir() and p.name.rsplit('_',1)[1].isdigit()]
        index=max([0,*existing,*[a['index'] for a in history]])+1
        process_dir=folder/f'process_attempt_{index:03d}';process_dir.mkdir(exist_ok=False)
        attempt={'index':index,'status':'started','output':str(dest),'logs':str(process_dir)}
        history.append(attempt);save()
        start=time.monotonic();command=[sys.executable,str(ROOT/script),'--ltspice',str(ltspice),*args,*extra]
        def logs(stdout,stderr):
            for filename,data in [('stdout.txt',stdout or b''),('stderr.txt',stderr or b'')]:
                atomic_write_bytes(process_dir/filename,data)
                atomic_write_bytes(folder/filename,data)
        try:
            proc=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=1200)
        except subprocess.TimeoutExpired as e:
            attempt.update(status='timeout',error=str(e));logs(e.stdout,e.stderr)
            raise RuntimeError(name+' time budget exhausted; partial files retained')
        except Exception as error:
            attempt.update(status='worker_start_error',error=str(error));raise
        finally:
            state['execution_seconds']+=time.monotonic()-start
        logs(proc.stdout,proc.stderr)
        save()
        path=dest/'RESULT.json'
        if proc.returncode or not path.exists() or read(path)['status']!=expected:
            attempt.update(status='worker_incomplete',returncode=proc.returncode);save()
            raise RuntimeError(name+' did not complete; see saved logs')
        attempt.update(status='completed',returncode=proc.returncode)
        state['stages'][name]={'completed':True,'result':str(path),'sha256':file_hash(path)};save();return path
    try:
        if imports:
            core,imp,over=map(lambda p:Path(p).resolve(),imports)
        else:
            if not ltspice:raise ValueError('LTspice required')
            core=child('core','run_extended_verification.py',['--netlist',str(model),'--run-dir',str(run_dir),'--numerical-policy','startup_seeded','--bench-timeout','60'],'completed_with_explicit_unverified_cases')
            imp=child('impedance','run_input_impedance_extension.py',['--baseline',str(core),'--plan',str(plan)],'extension_completed_with_explicit_model_limitations')
            over=child('overload','run_overload_extension.py',['--baseline',str(imp.parent/'COMBINED_LEDGER.json'),'--plan',str(plan)],'extension_completed')
        result=check_chain(core,imp,over,model,plan)
        write_json(out/'LEDGER.json',result)
        request=make_request(read(plan),result,model.read_text(encoding='ascii'),harness);write_json(out/'DESIGN_REQUEST.json',request)
        state.update(status='completed',case_status_counts=result['case_status_counts'],results={'core':str(core),'impedance':str(imp),'overload':str(over)},
                     outputs={str(p):file_hash(p) for p in (out/'LEDGER.json',out/'DESIGN_REQUEST.json')})
        state.pop('error',None)
        save();return state
    except Exception as error:
        state.setdefault('error_history',[]).append({'type':type(error).__name__,'error':str(error),'time_unix':time.time()})
        state.update(status='error',error=str(error));save();raise
