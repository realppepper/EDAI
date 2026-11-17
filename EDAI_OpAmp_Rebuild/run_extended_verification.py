"""Three requested verification stages; all source rows remain in coverage ledger."""
import argparse,json,math,time,re
from pathlib import Path
from datetime import datetime
from opamp_pipeline.verify_01_fixtures import build_fixture
from opamp_pipeline.verify_02_metrics import measure
from opamp_pipeline.verify_03_calibrate import calibrate
from opamp_pipeline.tb_02_ltspice import run_bench,decode_log
from opamp_pipeline.loop_02_handoff import write_json,validate_dut
from opamp_pipeline.support.execution_state import file_hash,require_current_hkg,require_current_pdg
from opamp_pipeline.support.source_checks import fingerprint
from opamp_pipeline.plan_04_validate import validate_plan
from opamp_pipeline.plan_01_select_targets import select_targets
from opamp_pipeline.diag_02_startup_seed import internal_nodes,startup_deck,seeds_from_waveform,supply_from_deck,seeded_deck
from opamp_pipeline.tb_05_waveform_metrics import read_real_raw
from opamp_pipeline.diag_03_solver_attempts import run_with_fallback,SolverAttemptsError,measured_trace_deck
from opamp_pipeline.verify_06_batch import select_batch
from opamp_pipeline.validation_03_execution_contract import validate_execution,ExecutionContractError
from opamp_pipeline.validation_04_execution_paths import execution_signature,reusable_job
from opamp_pipeline.validation_05_special_fixtures import startup_meta

STAGES={1:{'vos','iq','gbw','pm','settling','ib','ios'},2:{'vcm','vswing','aol'},
        3:{'iout','isc','sr','cmrr','psrr','noise_density','ro','capacitive_drive'}}
STAGES[3].add('input_resistance')
UNSUPPORTED={'channel_separation':'Single-channel DUT has no second physical channel/coupling model.',
 'noise_pp':'No calibrated intrinsic stochastic device-noise transient adapter/1f model; RMS is not substituted for peak-to-peak.',
 'zid':'R||C input impedance fit adapter not implemented; ideal MOS DC gate resistance is not calibrated.',
 'zic':'Common-mode R||C fit adapter not implemented; ideal MOS DC gate resistance is not calibrated.',
 'overload_recovery':'Manufacturer-equivalent overload/recovery protocol not implemented in this extension.',
 'thdn':'Full THD+N requires harmonic extraction plus calibrated integrated noise; deterministic FFT alone is insufficient.'}


def case_verdict(item,case,parts):
    if item['method']['kind']=='vcm':
        from opamp_pipeline.verify_04_dc_coverage import require_complete_vcm_case
        require_complete_vcm_case(case['fixture'],parts)
    kind=item['method']['kind'];gates=[g for p in parts for g in p['gate_issues']]
    limitations=[s for p in parts for s in p['model_limitations']]
    values=[p['value'] for p in parts];tests=[]
    if kind=='capacitive_drive':
        pm=parts[0]['value'];pm_ok=pm is not None and pm>=45
        growth=all(p['metrics'].get('finite_window_non_growing_response',False) for p in parts[1:])
        tests=[{'metric':'phase_margin','value':pm,'operator':'>=','limit':45,'passed':pm_ok},
               {'metric':'finite_observation_non_growing_step','value':growth,'passed':growth}]
    else:
        rules=item['target']['rules']
        if kind=='vcm':rules=[rules[1]]
        for value in values:
            for rule in rules:
                limit=rule['value'];op=rule['operator']
                valid=isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
                good=valid and (value<=limit if op=='<=' else value>=limit if op=='>=' else value==limit)
                tests.append({'metric':rule['metric'],'value':value,'operator':op,'limit':limit,'unit':rule.get('unit'),'passed':bool(good)})
    if limitations:status='unverified_model'
    elif gates or not all(t['passed'] for t in tests):status='failed_in_model'
    else:status='passed_sampled_model_case'
    return {'case_id':case['case_id'],'supply_V':case['fixture']['supply_voltage_V'],'status':status,
            'fixture':case['fixture'],'tests':tests,'gate_issues':gates,'model_limitations':limitations,'parts':parts,
            'full_continuous_range_verified':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('--ltspice',required=True);p.add_argument('--netlist',type=Path,required=True)
    p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--resume',type=Path)
    p.add_argument('--reuse-run',type=Path,help='Reuse physically identical saved jobs; changed decks are re-simulated')
    p.add_argument('--reuse-calibration',type=Path,help='Reuse known-answer reference jobs only, never a different DUT result')
    p.add_argument('--output-dir',type=Path)
    p.add_argument('--bench-timeout',type=float,default=20)
    p.add_argument('--numerical-policy',choices=['default','startup_seeded'],default='default')
    p.add_argument('--case-id',action='append',help='Diagnostic subset only; repeat per case. Never reports full-plan completion.')
    a=p.parse_args();root=Path(__file__).resolve().parent;planfolder=a.run_dir/'measurement_plan'
    read=lambda path:json.loads(Path(path).read_text(encoding='utf-8'))
    hkg=require_current_hkg(a.run_dir);pdg=require_current_pdg(a.run_dir);status=read(planfolder/'STATUS.json')
    if not status.get('completed') or fingerprint(read(planfolder/'MEASUREMENT_PLAN.json'))!=status['final_document_fingerprint']:raise ValueError('Incomplete or changed plan')
    for i in status['inputs']:
        if file_hash(i['path'])!=i['sha256']:raise ValueError('Source plan input changed')
    policy=read(status['inputs'][0]['path']);selection=read(planfolder/'plan_01_target_selection.json')
    measurements=read(planfolder/'plan_02_measurements.json')
    if selection!=select_targets(hkg,pdg,policy):raise ValueError('Target selection changed')
    validate_plan(selection,measurements,read(planfolder/'plan_03_execution_policies.json'),hkg,pdg,policy['engineering_defaults'])
    execution_rows,batch=select_batch(measurements,a.case_id)
    validate_dut(a.netlist.read_text(encoding='ascii'))
    out=a.resume or a.output_dir or root/'runs/extended_verification'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    if not a.resume and (out/'RESULT.json').exists():raise ValueError('Refusing existing result; use resume or a fresh output folder')
    out=out.resolve();out.mkdir(parents=True,exist_ok=True)
    signatures={str(path):file_hash(path) for path in [a.netlist.resolve(),(planfolder/'plan_02_measurements.json').resolve(),
        root/'opamp_pipeline/verify_01_fixtures.py',root/'opamp_pipeline/verify_02_metrics.py',root/'opamp_pipeline/verify_03_calibrate.py',root/'opamp_pipeline/verify_04_dc_coverage.py',root/'opamp_pipeline/verify_06_batch.py',root/'opamp_pipeline/tb_06_loop_gain.py']}
    if a.numerical_policy!='default':
        for path in (root/'run_extended_verification.py',root/'opamp_pipeline/diag_02_startup_seed.py',root/'opamp_pipeline/diag_03_solver_attempts.py'):
            signatures[str(path)]=file_hash(path)
    for path in [*(root/'opamp_pipeline').glob('*.py'),Path(__file__).resolve()]:signatures[str(path)]=file_hash(path)
    if a.resume:
        result=read(out/'RESULT.json')
        if result['input_signatures']!=signatures:raise ValueError('Inputs/code changed; preserve old run and start a new one')
        if result.get('numerical_policy','default')!=a.numerical_policy:raise ValueError('Numerical policy changed')
        if result.get('batch')!=batch:raise ValueError('Selected diagnostic batch changed')
    else:
        (out/'candidate.inc').write_bytes(a.netlist.read_bytes())
        result={'status':'started','stage':0,'input_signatures':signatures,'rows':{},'job_cache':{},
            'execution_limits':{'per_bench_timeout_s':a.bench_timeout},
            'scope':'Generic LEVEL1 model,25C,one physical channel; source-case voltage/load conditions retained.',
            'source_rows_required':len(execution_rows),'source_cases_required':sum(len(m['cases']) for m in execution_rows),'batch':batch,
            'new_external_llm_calls':0,'all_source_requirements_passed':False}
        result['numerical_policy']=a.numerical_policy
    model=out/'candidate.inc'
    if file_hash(model)!=signatures[str(a.netlist.resolve())]:raise ValueError('Stored DUT copy changed')
    calibration_only=bool(a.reuse_calibration) and not bool(a.reuse_run)
    reuse_dir=(a.reuse_run or a.reuse_calibration).resolve() if a.reuse_run or a.reuse_calibration else None
    reuse_result=read(reuse_dir/'RESULT.json') if reuse_dir else None
    if reuse_dir:
        if not calibration_only and file_hash(reuse_dir/'candidate.inc')!=file_hash(model):raise ValueError('Reuse DUT differs')
        if reuse_result['input_signatures'][str((planfolder/'plan_02_measurements.json').resolve())]!=file_hash(planfolder/'plan_02_measurements.json'):raise ValueError('Reuse source plan differs')
        result['reprocessed_from']={'path':str(reuse_dir),'result_sha256':file_hash(reuse_dir/'RESULT.json'),
            'scope':'calibration_only' if calibration_only else 'physically_identical_jobs',
            'rule':'Raw jobs reused only after full netlist and included-model content equivalence; current metrics recalculated.'}
    def save():write_json(out/'RESULT.json',result)
    save()
    def execute(label,deck,meta,*,calibration_job=False):
        meta['execution_contract_receipt_dir']=str(out/'execution_contracts')
        validate_execution(deck,meta,phase='generated_preflight')
        normal_recovery=meta.get('numerical_execution')=='normal_no_hint_once'
        if normal_recovery and (meta['analysis']!='dc' or meta.get('kind') not in {'vcm','cmrr'} or calibration_job):
            raise ValueError('Normal recovery is limited to DUT VCM/CMRR DC coverage')
        if a.numerical_policy=='startup_seeded':deck=measured_trace_deck(deck,meta)
        fallback_deck=deck
        if a.numerical_policy=='startup_seeded' and meta['analysis']=='tran':
            fallback_deck=fallback_deck.replace('.end\n','.options itl4=100\n.end\n')
        if normal_recovery:
            from opamp_pipeline.verify_04_dc_coverage import normal_vcm_recovery_deck
            deck=normal_vcm_recovery_deck(deck,'VCM' if meta['kind']=='cmrr' else 'VIN')
        elif a.numerical_policy=='startup_seeded':
            if calibration_job:
                deck=deck.replace('.end\n','.options solver=alt\n.end\n')
            else:
                vs,minus=supply_from_deck(deck);key=f'{vs:.10g}'
                seedfolder=out/'startup_seeds';seedfolder.mkdir(exist_ok=True)
                receipt=result.setdefault('startup_seeds',{}).get(key)
                failure=result.setdefault('startup_seed_failures',{}).get(key)
                if receipt:
                    if any(file_hash(p)!=h for p,h in receipt['artifacts'].items()):raise ValueError('Startup seed artifact changed')
                elif not failure:
                    path=seedfolder/f'start_{key}.cir';path.write_text(startup_deck(model,vs),encoding='ascii')
                    start_meta=startup_meta(model,vs)
                    start_meta['execution_contract_receipt_dir']=str(out/'execution_contracts')
                    validate_execution(path.read_text(encoding='ascii'),start_meta,phase='startup_preflight')
                    try:
                        run_bench(a.ltspice,path,[],ascii_raw=True,timeout=a.bench_timeout)
                        start_validation=validate_execution(path.read_text(encoding='ascii'),start_meta,phase='startup_before_metric')
                        seeds,details=seeds_from_waveform(read_real_raw(path.with_suffix('.raw')),vs,internal_nodes(model.read_text(encoding='ascii')))
                    except ExecutionContractError:
                        raise
                    except Exception as error:
                        result['startup_seed_failures'][key]={'error':str(error),'path':str(path)}
                        result['startup_seed_failure_is_not_a_source_case_verdict']=True;save()
                    else:
                        receipt={'seeds':seeds,'details':details,'execution_contract':start_validation,
                                 'artifacts':{str(p):file_hash(p) for p in (path,path.with_suffix('.raw'),path.with_suffix('.log'))}}
                        result['startup_seeds'][key]=receipt;save()
                if receipt:deck=seeded_deck(deck,receipt['seeds'],minus)
                else:deck=deck.replace('.end\n','.options solver=alt\n.end\n')
            if meta['analysis']=='tran':deck=deck.replace('.end\n','.options itl4=100\n.end\n')
        validate_execution(deck,meta,phase='execution_preflight')
        execution_binding=execution_signature(deck,meta)
        identity=execution_binding['key']
        old=result['job_cache'].get(identity)
        hit=reusable_job(old,deck,meta,execution_binding)
        if hit:return hit
        if reuse_dir and (not calibration_only or calibration_job):
            # Legacy unbound entries are misses. A verdict is never reused;
            # every hit is interpreted by today's checked measurement code.
            reused=reuse_result['job_cache'].get(identity)
            hit=reusable_job(reused,deck,meta,execution_binding)
            if hit:
                result['job_cache'][identity]={**reused,'reused_from_readonly_run':str(reuse_dir),'reused_without_simulation':True}
                save();return hit
        jobroot=out/'jobs'/identity[:20];jobroot.mkdir(parents=True,exist_ok=True)
        attempt=len(list(jobroot.glob('attempt_*')))+1;folder=jobroot/f'attempt_{attempt:02d}';folder.mkdir()
        path=folder/'bench.cir';path.write_text(deck,encoding='ascii')
        result['job_cache'][identity]={'completed':False,'path':str(path),'label':label,
                                       'execution_signature':execution_binding};save()
        start=time.monotonic()
        try:
            if normal_recovery:
                # Exactly one execution: do not nest the generic solver retry.
                run=run_bench(a.ltspice,path,meta['names'],ascii_raw=True,timeout=a.bench_timeout)
                observed=re.search(r'^solver = (.+)$',decode_log(path.with_suffix('.log')),re.M)
                if not observed or observed[1].strip().lower()!='normal':raise ValueError('Recovery did not use the Normal solver')
                result['job_cache'][identity].update(numerical_execution='normal_no_hint_once',observed_solver='Normal',
                    solver_attempts=[{'policy':'normal_no_hint_once','path':str(path),'status':'computed'}])
            elif a.numerical_policy=='startup_seeded':
                attempt=run_with_fallback(a.ltspice,path,meta['names'],meta['analysis']!='noise',a.bench_timeout,fallback_deck,meta=meta)
                path=attempt['path'];run=attempt['run'];result['job_cache'][identity].update(path=str(path),solver_attempts=attempt['attempts'])
            else:run=run_bench(a.ltspice,path,meta['names'],ascii_raw=meta['analysis']!='noise',timeout=a.bench_timeout)
        except Exception as error:
            if isinstance(error,SolverAttemptsError):result['job_cache'][identity]['solver_attempts']=error.attempts
            elif normal_recovery:result['job_cache'][identity]['solver_attempts']=[{'policy':'normal_no_hint_once','path':str(path),'status':'execution_error','error':str(error)}]
            result['job_cache'][identity].update(error=str(error),seconds=time.monotonic()-start);save();raise
        artifacts={str(x):file_hash(x) for x in folder.rglob('*') if x.is_file()}
        result['job_cache'][identity].update(completed=True,measurements=run['measurements'],seconds=time.monotonic()-start,artifacts=artifacts)
        save();return {'path':path,'measurements':run['measurements'],'cache_reused':False}
    try:
        result['stage']='calibration';save()
        # Calibration may use nested labels such as core_cal_settling_*. Its
        # known-answer circuits must never receive the DUT's startup seeds.
        calibration=calibrate(out,measurements,
            lambda label,deck,meta:execute(label,deck,meta,calibration_job=True))
        write_json(out/'ADAPTER_VALIDATION.json',calibration)
        if calibration['status']!='passed':raise ValueError('New adapter calibration failed; DUT source-case verdicts withheld')
        result['calibration_passed']=True;save();print('Adapter known-answer checks passed.',flush=True)
        for stage,kinds in STAGES.items():
            result['stage']=stage;save();print(f'Stage {stage} started.',flush=True)
            for item in execution_rows:
                kind=item['method']['kind']
                if kind not in kinds:continue
                row=result['rows'].setdefault(item['row_id'],{'row_id':item['row_id'],'symbol':item['symbol'],'kind':kind,'target':item['target'],'cases':[]})
                done={c['case_id'] for c in row['cases']}
                for case in item['cases']:
                    if case['case_id'] in done:continue
                    variants=['lower','upper'] if kind=='vcm' else ['rising','falling'] if kind in {'sr','settling'} else ['pm','rising','falling'] if kind=='capacitive_drive' else ['source','sink'] if kind=='isc' else ['default']
                    if kind=='vswing' and case['fixture'].get('forced_output_rail')=='both':variants=['upper','lower']
                    parts=[];numerical_attempts=None
                    def collect(requested_variants,normal_no_hint=False):
                        parts.clear()
                        for variant in requested_variants:
                            deck,meta=build_fixture(model,item,case,variant)
                            if normal_no_hint:meta={**meta,'numerical_execution':'normal_no_hint_once'}
                            job=execute(item['symbol']+'_'+variant,deck,meta)
                            part=measure(job['path'],kind,case['fixture'],meta,job['measurements'])
                            part.update(variant=variant,job_path=str(job['path']),assumptions=meta['assumptions'])
                            if normal_no_hint:part['numerical_execution']='normal_no_hint_once'
                            if kind in {'pm','capacitive_drive'} and meta['analysis']=='ac':
                                part['metrics']['qualification']={'status':'extended_adapter_reference_checks_passed',
                                    'evidence':str(out/'ADAPTER_VALIDATION.json'),'measurement_code_sha256':signatures[str(root/'opamp_pipeline/tb_06_loop_gain.py')]}
                            parts.append(part)
                        return list(parts)
                    try:
                        if kind=='vcm':
                            from opamp_pipeline.verify_04_dc_coverage import collect_vcm_with_numerical_fallback
                            parts,numerical_attempts=collect_vcm_with_numerical_fallback(collect,
                                collect_normal=lambda:collect(('default',),normal_no_hint=True))
                        elif kind=='cmrr':
                            from opamp_pipeline.verify_04_dc_coverage import collect_cmrr_with_numerical_fallback
                            parts,numerical_attempts=collect_cmrr_with_numerical_fallback(
                                lambda normal:collect(('default',),normal_no_hint=normal))
                        else:parts=collect(variants)
                        verdict=case_verdict(item,case,parts)
                    except Exception as error:
                        verdict={'case_id':case['case_id'],'supply_V':case['fixture']['supply_voltage_V'],'fixture':case['fixture'],
                            'status':'execution_error','error':str(error),'parts':parts,'full_continuous_range_verified':False,
                            'physical_spec_failure_established':False}
                        if isinstance(error,ExecutionContractError):
                            verdict.update(status='execution_contract_error',error_type=type(error).__name__,
                                           validation=error.validation)
                        if hasattr(error,'coverage'):
                            verdict['measurement_coverage']=error.coverage
                            verdict['error_type']=type(error).__name__
                            verdict['physical_spec_failure_established']=False
                        numerical_attempts=getattr(error,'numerical_attempts',numerical_attempts)
                    if numerical_attempts:verdict['numerical_attempts']=numerical_attempts
                    row['cases'].append(verdict);save()
                print(f"  {item['symbol']}: "+','.join(c['status'] for c in row['cases']),flush=True)
        for item in execution_rows:
            if item['row_id'] not in result['rows']:
                result['rows'][item['row_id']]={'row_id':item['row_id'],'symbol':item['symbol'],'kind':item['method']['kind'],'target':item['target'],
                    'cases':[{'case_id':c['case_id'],'supply_V':c['fixture']['supply_voltage_V'],'fixture':c['fixture'],
                              'status':'unverified_adapter','reason':UNSUPPORTED.get(item['method']['kind'],'Adapter not implemented')} for c in item['cases']]}
        allcases=[c for r in result['rows'].values() for c in r['cases']]
        counts={s:sum(c['status']==s for c in allcases) for s in sorted({c['status'] for c in allcases})}
        if len(allcases)!=result['source_cases_required']:raise ValueError('Source case coverage missing')
        result.update(status='completed_selected_cases_diagnostic' if batch['partial_run'] else 'completed_with_explicit_unverified_cases',stage='finished',case_status_counts=counts)
        save()
    except Exception as error:
        result.update(status='error',error=str(error))
        if isinstance(error,ExecutionContractError):
            result.update(error_type=type(error).__name__,error_category='execution_contract_error',
                          validation=error.validation,physical_spec_failure_established=False)
        save();raise
    feedback={'scope':result['scope'],'case_status_counts':counts,'rows':list(result['rows'].values()),
        'all_source_requirements_passed':False,'input_signatures':signatures,'no_source_target_rewritten':True,'batch':batch}
    write_json(out/'LLM_FEEDBACK.json',feedback)
    lines=['# 拡張検証'.replace('拡張検証','전원·범위·구동 및 성능 검증'),'',result['scope'],'',
        (f"부분 검증: 원래{batch['full_plan_source_cases']}조건 중 선택{len(batch['selected_case_ids'])}조건만 실행하며 나머지{len(batch['not_executed_case_ids'])}조건은 미실행입니다. 전체 통과가 아닙니다." if batch['partial_run'] else f"현재 채택한{batch['full_plan_source_rows']}행/{batch['full_plan_source_cases']}사례를 모두 추적합니다. 미채택 원문 행은 목표 선택 파일에 보존됩니다. 아래 통과는 해당 일반 모델·표본·프로젝트 측정 정의에서의 결과이며 실제 제조나 연속 범위 전체 인증이 아닙니다."),
        '',str(counts),'', '| 사양 | 전원(V) | 상태 | 측정값 |','|---|---:|---|---|']
    for row in result['rows'].values():
        for case in row['cases']:
            values=', '.join(str(p['value']) for p in case.get('parts',[]))
            lines.append(f"| {row['symbol']} | {case['supply_V']} | {case['status']} | {values} |")
    lines+=['','## 한계·미검증','',
        '-25°C만 검사하며 원문의 온도 범위는 바꾸지 않습니다. 범위는 유한 격자·표본 검사입니다.',
        '- 일반 LEVEL1 모델은 고전압 내압·제조 공정·1/f잡음·게이트 누설·mismatch의 정확성을 보장하지 않습니다. KF를 임의로 만들어 성능에 맞추지 않았습니다.',
        '- 잡음 밀도는 실제.noise로 얻은 열잡음 기반 진단입니다. 모델 한계가 있는 값은 낮게 나왔다고 전체 잡음 통과로 집계하지 않습니다.',
        '- CMRR은 전체 지정 입력 범위의 유효 DC 바이어스와 오프셋 민감도를 확인합니다. PSRR은 중간 공통모드를 고정하고 양 전원을 대칭으로 변화시켜 공통모드 변화가 섞이지 않도록 했습니다.',
        '- VO는1V 차동 과구동을 사용한 프로젝트 포화 측정입니다. 출력 전류는 DUT 단자 VSENSE로 측정해 외부 RL 전류와 혼동하지 않습니다.',
        '- 미구현 항목은 분모에서 삭제하지 않습니다. 모든 원문 사양 성공을 선언하지 않습니다.',
        '', '측정 근거: [ADI DC 측정법](https://www.analog.com/en/resources/analog-dialogue/articles/simple-op-amp-measurements.html), [ADI LTspice noise/.MEAS](https://github.com/analogdevicesinc/ltspice-reference/blob/main/ai_ref/MEAS-REFERENCE.md).']
    (out/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    write_json(root/('runs/verification_batches/LATEST.json' if batch['partial_run'] else 'runs/extended_verification/LATEST.json'),{'output':str(out),'report':str(out/'REPORT.md'),'counts':counts})
    print(json.dumps({'status':result['status'],'output':str(out),'counts':counts},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
