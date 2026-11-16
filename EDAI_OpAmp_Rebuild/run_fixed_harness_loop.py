"""Current chat is the designer; the deterministic host executes the full verification pipeline."""
import argparse,json
from pathlib import Path
from opamp_pipeline.harness_03_loop import start,submit,load,resume
from opamp_pipeline.harness_01_fixed import DEFAULT_POLICY


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['start','submit','resume','status']);p.add_argument('--session',type=Path,required=True)
    p.add_argument('--netlist',type=Path);p.add_argument('--response',type=Path);p.add_argument('--ltspice')
    p.add_argument('--run-dir',type=Path,default=Path('runs/lm358b_overview_20261112'));p.add_argument('--harness',type=Path,default=DEFAULT_POLICY)
    p.add_argument('--max-candidates',type=int,default=3);p.add_argument('--import-core',type=Path);p.add_argument('--import-impedance',type=Path);p.add_argument('--import-overload',type=Path)
    p.add_argument('--defer-validation',action='store_true',help='Save an accepted response and exit; resume validates it in a fresh process');a=p.parse_args()
    if a.defer_validation and a.action not in {'start','submit'}:p.error('--defer-validation is only valid for start or submit')
    if a.action=='start':
        if not a.netlist:p.error('netlist required')
        imported=[a.import_core,a.import_impedance,a.import_overload]
        if any(imported) and not all(imported):p.error('All imported stages required')
        state=start(a.session,a.netlist,a.run_dir,a.ltspice,imported if all(imported) else None,a.harness,a.max_candidates,defer_validation=a.defer_validation)
    elif a.action=='submit':
        if not a.response or (not a.ltspice and not a.defer_validation):p.error('response and LTspice required unless deferring validation')
        state=submit(a.session,a.response,a.ltspice,defer_validation=a.defer_validation)
    else:
        state=resume(a.session,a.ltspice) if a.action=='resume' else load(a.session)
    print(json.dumps({'status':state['status'],'candidates':len(state['candidates']),'best_index':state['best_index'],
                      'pending_request':state.get('pending_request'),'external_llm_api_calls':0,'harness2_enabled':False,
                      'schematic':state.get('schematic'),'deliverables_complete':state.get('deliverables_complete',False)},ensure_ascii=False))


if __name__=='__main__':main()
