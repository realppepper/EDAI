"""Fast priority screen; full extended revalidation is still required afterward."""
import argparse,json
from datetime import datetime
from pathlib import Path
from opamp_pipeline.verify_01_fixtures import build_fixture
from opamp_pipeline.verify_02_metrics import measure
from opamp_pipeline.tb_02_ltspice import run_bench
from opamp_pipeline.tb_05_waveform_metrics import read_real_raw
from opamp_pipeline.loop_02_handoff import write_json,validate_dut
from opamp_pipeline.support.execution_state import file_hash


def main():
    p=argparse.ArgumentParser();p.add_argument('--ltspice',required=True);p.add_argument('--netlist',type=Path,required=True)
    p.add_argument('--startup-supplies',type=float,nargs='+',default=[5,36])
    a=p.parse_args();root=Path(__file__).resolve().parent
    out=root/'runs/bias_probe'/datetime.now().strftime('%Y%m%d_%H%M%S_%f');out.mkdir(parents=True)
    text=a.netlist.read_text(encoding='ascii');validate_dut(text);model=out/'candidate.inc';model.write_text(text,encoding='ascii')
    plan=json.loads((root/'runs/lm358b_overview_20261112/measurement_plan/plan_02_measurements.json').read_text(encoding='utf-8'))
    result={'status':'running','netlist_sha256':file_hash(model),'checks':[],'startup':[]}
    def save():write_json(out/'RESULT.json',result)
    save()
    for item in plan['measurements']:
        if item['symbol'] not in {'IQ','PSRR','VOS'}:continue
        for case in item['cases']:
            deck,meta=build_fixture(model,item,case);path=out/(case['case_id']+'.cir');path.write_text(deck,encoding='ascii')
            try:
                run=run_bench(a.ltspice,path,meta['names'],ascii_raw=True,timeout=20)
                measured=measure(path,item['method']['kind'],case['fixture'],meta,run['measurements'])
                limit=item['target']['rules'][0]['value'];value=measured['value']
                passed=value is not None and value<=limit and not measured['gate_issues']
                result['checks'].append({'symbol':item['symbol'],'supply_V':case['fixture']['supply_voltage_V'],
                    'measured':value,'limit':limit,'passed':passed,'details':measured})
            except Exception as error:result['checks'].append({'symbol':item['symbol'],'supply_V':case['fixture']['supply_voltage_V'],'passed':False,'error':str(error)})
            save()
    for vs in a.startup_supplies:
        deck=f'''* Zero-supply startup, explicit ramp, no forced internal initial condition
.include "{model.resolve()}"
.temp 25
.options plotwinsize=0 numdgt=15
VDD vp 0 PWL(0 0 5u 0 15u {vs} 200u {vs})
BMID mid 0 V=V(vp)/2
XDUT mid out vp 0 out FIRSTAMP
RL out mid 10k
CL out mid 20p
.save V(vp) V(out) V(xdut:bias) I(VDD)
.tran 0 200u 0 20n
.end
'''
        path=out/f'startup_{vs}V.cir';path.write_text(deck,encoding='ascii')
        try:
            run_bench(a.ltspice,path,[],ascii_raw=True,timeout=30)
            raw=read_real_raw(path.with_suffix('.raw'));tail=[i for i,t in enumerate(raw['time']) if t>=150e-6]
            bias=[raw['v(xdut:bias)'][i] for i in tail];current=[-raw['i(vdd)'][i] for i in tail]
            passed=bool(tail) and min(bias)>.65 and max(bias)-min(bias)<.001 and min(current)>0
            result['startup'].append({'supply_V':vs,'passed':passed,'bias_V_range':[min(bias),max(bias)],
                                     'current_A_range':[min(current),max(current)],'output_final_V':raw['v(out)'][-1]})
        except Exception as error:result['startup'].append({'supply_V':vs,'passed':False,'error':str(error)})
        save()
    result['status']='screen_passed' if all(c['passed'] for c in result['checks']+result['startup']) else 'screen_has_failures';save()
    write_json(root/'runs/bias_probe/LATEST.json',{'output':str(out),'status':result['status']})
    print(json.dumps({'output':str(out),**result},ensure_ascii=False))

if __name__=='__main__':main()
