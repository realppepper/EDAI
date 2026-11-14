"""Separate follower input range from output-sink loading; never change source-case verdicts."""
import argparse,json
from pathlib import Path
from opamp_pipeline.verify_01_fixtures import build_fixture
from opamp_pipeline.verify_02_metrics import measure
from opamp_pipeline.tb_02_ltspice import run_bench
from opamp_pipeline.tb_05_waveform_metrics import read_real_raw
from opamp_pipeline.loop_02_handoff import write_json
from opamp_pipeline.support.execution_state import file_hash


def main():
    p=argparse.ArgumentParser();p.add_argument('--ltspice',required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    src=Path('runs/extended_design_loop/20261113_input_gain_revision/candidate_001.inc');model=out/'candidate.inc';model.write_bytes(src.read_bytes())
    source=Path('runs/lm358b_overview_20261112/measurement_plan/plan_02_measurements.json');plan=json.loads(source.read_text(encoding='utf-8'))
    item=next(x for x in plan['measurements'] if x['symbol']=='VCM');case=next(c for c in item['cases'] if abs(c['fixture']['supply_voltage_V']-36)<1e-9)
    base,meta=build_fixture(model,item,case)
    result={'status':'running','diagnostic_only':True,'no_source_target_changed':True,'source_plan_sha256':file_hash(source),'candidate_sha256':file_hash(model),'checks':[]}
    save=lambda:write_json(out/'RESULT.json',result);save()
    for label,load in [('source_midrail','RL out mid 10000'),('load_to_ground','RL out vm 10000'),('unloaded','* Diagnostic: external RL omitted')]:
        deck=base.replace('RL out mid 10000',load)
        path=out/(label+'.cir');path.write_text(deck,encoding='ascii');record={'intervention':label,'source_case_id':case['case_id']}
        try:
            run=run_bench(a.ltspice,path,[],ascii_raw=True,timeout=30);m=measure(path,'vcm',case['fixture'],meta,{})
            raw=read_real_raw(path.with_suffix('.raw'));error=[abs(a-b) for a,b in zip(raw['v(inp)'],raw['v(out)'])];i=max(range(len(error)),key=error.__getitem__)
            record.update(status='computed',max_error_V=m['value'],worst_input_V=raw['v(inp)'][i],worst_output_V=raw['v(out)'][i],worst_dut_current_A=raw['i(vsense)'][i],zero_input_output_V=raw['v(out)'][0])
        except Exception as e:record.update(status='execution_error',error=str(e))
        result['checks'].append(record);save();print(label,record,flush=True)
    result['status']='diagnosis_completed';save()


if __name__=='__main__':main()
