"""Inventory unresolved cases and qualify deterministic THD without changing models."""
import argparse,json,math
from pathlib import Path
from opamp_pipeline.loop_02_handoff import write_json
from opamp_pipeline.support.execution_state import file_hash
from opamp_pipeline.tb_02_ltspice import run_bench
from opamp_pipeline.tb_05_waveform_metrics import read_real_raw
from opamp_pipeline.verify_08_distortion import distortion_deck,harmonic_metrics


def main():
    p=argparse.ArgumentParser();p.add_argument('--netlist',type=Path,required=True)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--ledger',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--ltspice',required=True);a=p.parse_args()
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    plan,ledger=read(a.plan),read(a.ledger);model=out/'candidate.inc';model.write_bytes(a.netlist.read_bytes())
    source_models={Path(p).resolve() for p,h in ledger['input_signatures'].items() if Path(p).suffix=='.inc' and h==file_hash(model)}
    if not source_models:raise ValueError('Model does not match measured ledger')
    reasons={'ib':'Needs calibrated input leakage; ideal gate current is not compliance evidence.',
             'ios':'Needs input leakage and mismatch assumptions.',
             'noise_density':'Thermal lower bound exists; uncalibrated flicker noise prevents a full pass.',
             'zid':'Capacitance component measured; calibrated leakage resistance is missing.',
             'zic':'Per-pin capacitance component measured; calibrated leakage resistance is missing.',
             'channel_separation':'A second physical channel and justified coupling paths are required; duplicating isolated channels would give a misleading zero.',
             'noise_pp':'Stochastic low-frequency noise model and observation protocol are required.',
             'thdn':'Deterministic distortion can be measured now; full calibrated noise is missing.'}
    inventory=[{'row_id':r['row_id'],'symbol':r['symbol'],'kind':r['kind'],
        'cases':[c['case_id'] for c in r['cases'] if c['status'].startswith('unverified')],
        'reason':reasons.get(r['kind'],'Requires review'),
        'full_verdict_available_without_new_physics':False}
        for r in ledger['rows'].values() if any(c['status'].startswith('unverified') for c in r['cases'])]
    result={'status':'running','model_sha256':file_hash(model),'source_ledger_sha256':file_hash(a.ledger),
            'plan_sha256':file_hash(a.plan),'inventory':inventory,'original_unverified_count':sum(len(r['cases']) for r in inventory),
            'calibration':[],'measurements':[],'full_case_promotions':0,'model_changed':False}
    save=lambda:write_json(out/'RESULT.json',result);save()
    item=next(r for r in plan['measurements'] if r['method']['kind']=='thdn')
    fixture=item['cases'][0]['fixture'];f=item['resolved_conditions']['values']['frequency_Hz']
    bw=item['method']['definition']['bandwidth_Hz'];amp=fixture['output_ac_amplitude_Vrms']
    def run(label,mod,subckt='FIRSTAMP',step='500n'):
        path=out/f'{label}.cir';path.write_text(distortion_deck(mod,fixture,f,amp,step,subckt),encoding='ascii')
        run_bench(a.ltspice,path,[],ascii_raw=True,timeout=120)
        raw=read_real_raw(path.with_suffix('.raw'))
        m=harmonic_metrics(raw['time'],raw['v(out)'],f,.008,.012,bw)
        prior=harmonic_metrics(raw['time'],raw['v(out)'],f,.004,.008,bw)
        m['stationary_fundamental']=abs(m['fundamental_Vrms']/prior['fundamental_Vrms']-1)<.001
        m['stationary_harmonics']=abs(m['thd_ratio']-prior['thd_ratio'])<=max(1e-7,.1*m['thd_ratio'])
        m['max_load_current_A']=max(abs(v) for t,v in zip(raw['time'],raw['i(rl)']) if t>=.008)
        return m
    try:
        for name,ratio in [('linear',0),('distorted',.001)]:
            ref=out/f'{name}.inc';peak=amp*math.sqrt(2)
            ref.write_text(f'.subckt DREF P N VP VM OUT\nBOUT OUT VM V=V(P,VM)+{ratio}*(2*(V(P,VM)-V(VP,VM)/2)**2/{peak}- {peak})\n.ends DREF\n',encoding='ascii')
            m=run('cal_'+name,ref,'DREF');good=abs(m['thd_ratio']-ratio)<1e-7 and m['stationary_fundamental'] and m['stationary_harmonics']
            result['calibration'].append({'name':name,'expected_thd_ratio':ratio,'passed':good,'measurement':m});save()
            if not good:raise ValueError('Analytic distortion reference failed')
        for label,step in [('dut','500n'),('dut_fine','250n')]:
            m=run(label,model,step=step);result['measurements'].append({'name':label,'measurement':m});save()
        first,last=[r['measurement'] for r in result['measurements']]
        convergence=abs(first['thd_ratio']-last['thd_ratio'])<=max(1e-7,.05*last['thd_ratio'])
        protocol=all(m['stationary_fundamental'] and m['stationary_harmonics'] and abs(m['fundamental_Vrms']/amp-1)<.01 and m['max_load_current_A']<=50e-6*1.001 for m in (first,last))
        result.update(status='completed_partial_component_only',numerically_qualified=convergence and protocol,
            thdn_case_id=item['cases'][0]['case_id'],full_thdn_verdict='unverified_noise_model',
            target_thdn_ratio=item['target']['rules'][0]['value'],source_ledger_changed=False)
        save();print(json.dumps({'status':result['status'],'qualified':result['numerically_qualified'],'thd_ratio':last['thd_ratio'],'full_promotions':0}),flush=True)
    except Exception as error:
        result.update(status='error',error=str(error));save();raise
    write_json(out/'ARTIFACTS.json',{'files':{str(p.relative_to(out)):file_hash(p) for p in out.rglob('*') if p.is_file() and p.name!='ARTIFACTS.json'}})


if __name__=='__main__':main()
