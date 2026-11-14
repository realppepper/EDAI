"""Derive nodeset hints from a physical supply ramp, then release all hints for DC solving."""
import argparse,json,time,math
from pathlib import Path
from opamp_pipeline.verify_01_fixtures import build_fixture
from opamp_pipeline.verify_02_metrics import measure
from opamp_pipeline.tb_02_ltspice import run_bench
from opamp_pipeline.tb_05_waveform_metrics import read_real_raw
from opamp_pipeline.loop_02_handoff import write_json,validate_dut
from opamp_pipeline.support.execution_state import file_hash


def main():
    p=argparse.ArgumentParser();p.add_argument('--ltspice',required=True);p.add_argument('--netlist',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--supplies',type=float,nargs='+',default=[5,36]);a=p.parse_args()
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False);model=out/'candidate.inc';model.write_bytes(a.netlist.read_bytes());validate_dut(model.read_text(encoding='ascii'))
    internal=set()
    for line in model.read_text(encoding='ascii').splitlines():
        fields=line.split()
        if fields and fields[0][0].upper() in {'M','R','C'} and not fields[0].startswith('*'):
            internal.update(fields[1:5] if fields[0][0].upper()=='M' else fields[1:3])
    internal-={'P','N','VP','VM','OUT'}
    explicit_save=' '.join(f'V(xdut:{node})' for node in sorted(internal))
    plan=json.loads(Path('runs/lm358b_overview_20261112/measurement_plan/plan_02_measurements.json').read_text(encoding='utf-8'))
    result={'status':'running','diagnostic_only':True,'candidate_sha256':file_hash(model),'checks':[],'fixed_initial_conditions':False,'forced_solution':False}
    save=lambda:write_json(out/'RESULT.json',result);save()
    for vs in a.supplies:
        record={'supply_V':vs};result['checks'].append(record)
        startup=out/f'start_{vs:g}.cir'
        startup.write_text(f'''* Physical startup for DC initial-guess hints only
.include "{model}"
.temp 25
.options plotwinsize=0 numdgt=15
VDD vp 0 PWL(0 0 5u 0 15u {vs:g} 100u {vs:g})
BMID mid 0 V=V(vp)/2
XDUT mid out vp 0 out FIRSTAMP
RL out mid 10k
CL out mid 20p
.save V(*) I(*) {explicit_save}
.tran 0 100u 0 20n
.end
''',encoding='ascii')
        try:
            run_bench(a.ltspice,startup,[],ascii_raw=True,timeout=20);raw=read_real_raw(startup.with_suffix('.raw'))
            tail=[i for i,t in enumerate(raw['time']) if t>=80e-6]
            record['startup_final_output_V']=raw['v(out)'][-1]
            record['startup_tail_output_span_V']=max(raw['v(out)'][i] for i in tail)-min(raw['v(out)'][i] for i in tail)
            seeds={k[2:-1]:v[-1] for k,v in raw.items() if k.startswith('v(xdut:') and math.isfinite(v[-1])}
            seeds.update(out=vs/2,dout=vs/2,inp=vs/2,inn=vs/2,vid=0)
            hints='.nodeset '+' '.join(f'V({k})={v:.15g}' for k,v in seeds.items())+'\n'
            record['seed_node_count']=len(seeds);record['measurements']=[]
            for symbol in ('VOS','IQ','PSRR'):
                item=next(x for x in plan['measurements'] if x['symbol']==symbol)
                case=next(c for c in item['cases'] if math.isclose(c['fixture']['supply_voltage_V'],vs,rel_tol=1e-12))
                deck,meta=build_fixture(model,item,case);deck=deck.replace('.end\n','.options solver=alt\n'+hints+'.end\n')
                path=out/f'{symbol}_{vs:g}.cir';path.write_text(deck,encoding='ascii');t=time.monotonic()
                try:
                    run=run_bench(a.ltspice,path,meta['names'],ascii_raw=True,timeout=12)
                    measured=measure(path,item['method']['kind'],case['fixture'],meta,run['measurements'])
                    entry={'symbol':symbol,'status':'computed','measurement':measured}
                except Exception as e:entry={'symbol':symbol,'status':'execution_error','error':str(e)}
                entry['elapsed_s']=time.monotonic()-t;record['measurements'].append(entry);save();print(vs,symbol,entry['status'],flush=True)
        except Exception as e:record.update(status='diagnostic_error',error=f'{type(e).__name__}: {e}')
        save()
    result['status']='diagnosis_completed';save()


if __name__=='__main__':main()
