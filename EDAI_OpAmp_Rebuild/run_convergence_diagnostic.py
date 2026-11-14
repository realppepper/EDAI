"""Compare unchanged DUTs under identical diagnostic numerical policies."""
import argparse,json,time
from pathlib import Path
from opamp_pipeline.diag_01_convergence import numerical_deck
from opamp_pipeline.verify_01_fixtures import build_fixture
from opamp_pipeline.verify_02_metrics import measure
from opamp_pipeline.tb_02_ltspice import run_bench,decode_log
from opamp_pipeline.loop_02_handoff import write_json
from opamp_pipeline.support.execution_state import file_hash


def main():
    p=argparse.ArgumentParser();p.add_argument('--ltspice',required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--timeout',type=float,default=10);a=p.parse_args();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    source=Path('runs/lm358b_overview_20261112/measurement_plan/plan_02_measurements.json')
    plan=json.loads(source.read_text(encoding='utf-8'));item=next(x for x in plan['measurements'] if x['symbol']=='VOS')
    case=next(c for c in item['cases'] if c['fixture']['supply_voltage_V']==5)
    paths={
        'baseline':'runs/extended_design_loop/20261113_bias_revision/candidate_002.inc',
        'folded':'runs/extended_design_loop/20261113_input_gain_revision/candidate_001.inc',
        'buffered':'runs/extended_design_loop/20261113_input_gain_revision/candidate_002.inc'}
    result={'status':'running','diagnostic_only':True,'source_plan_sha256':file_hash(source),'checks':[],
            'unchanged_acceptance':True,'no_forced_initial_conditions':True,'default_candidate_changed':False}
    def save():write_json(out/'RESULT.json',result)
    save()
    for label,src in paths.items():
        model=out/(label+'.inc');model.write_bytes(Path(src).read_bytes())
        for policy in ('normal','alternate','alternate_hint'):
            path=out/(label+'_'+policy+'.cir');deck,meta=build_fixture(model,item,case)
            path.write_text(numerical_deck(deck,policy,2.5),encoding='ascii');start=time.monotonic()
            record={'candidate':label,'candidate_sha256':file_hash(model),'policy':policy,'case_id':case['case_id'],'deck':str(path)}
            try:
                run=run_bench(a.ltspice,path,meta['names'],ascii_raw=True,timeout=a.timeout)
                value=measure(path,item['method']['kind'],case['fixture'],meta,run['measurements'])
                record.update(status='computed',measurement=value)
            except Exception as e:
                record.update(status='execution_error',error=str(e))
            record['elapsed_s']=time.monotonic()-start
            log=path.with_suffix('.log')
            if log.exists():record['log_tail']=decode_log(log).splitlines()[-12:]
            result['checks'].append(record);save();print(label,policy,record['status'],flush=True)
    result['status']='diagnosis_completed';save()


if __name__=='__main__':main()
