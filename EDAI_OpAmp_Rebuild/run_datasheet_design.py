"""Cold document handoffs and first-DUT generation; no historical netlist input."""
import argparse,json
from pathlib import Path
from opamp_pipeline import startup_02_datasheet as startup


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['start','submit','resume','status'])
    p.add_argument('--session',type=Path,required=True);p.add_argument('--pdf',type=Path)
    p.add_argument('--target',default='LM358B');p.add_argument('--settings',type=Path)
    p.add_argument('--env-file',type=Path);p.add_argument('--response',type=Path);p.add_argument('--ltspice')
    p.add_argument('--max-rounds',type=int,default=2);p.add_argument('--revisions-per-round',type=int,default=1);a=p.parse_args()
    if a.action=='start':
        if not a.pdf or not a.settings:p.error('PDF and engineering settings required')
        s=startup.start(a.session,a.pdf,a.target,a.settings,a.env_file,a.max_rounds,a.revisions_per_round)
    elif a.action=='submit':
        if not a.response:p.error('Response required')
        s=startup.submit(a.session,a.response)
    elif a.action=='resume':s=startup.resume(a.session,a.ltspice)
    else:s=startup.load(a.session)
    print(json.dumps({'status':s['status'],'workflow_status':s.get('workflow_status'),
        'pending_request':s['pending_request'],'workflow_session':s.get('workflow_session'),
        'past_circuit_imported':False,'schematic':s.get('schematic'),
        'deliverables_complete':s.get('deliverables_complete',False)},ensure_ascii=False))


if __name__=='__main__':main()
