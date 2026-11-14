"""Manual-chat designer bridge. No polling and no paid LLM API invocation."""
import argparse,json
from pathlib import Path
from opamp_pipeline.loop_03_controller import start,submit,resume,load


def main():
    parser=argparse.ArgumentParser();commands=parser.add_subparsers(dest='action',required=True)
    init=commands.add_parser('start');init.add_argument('--session',type=Path,required=True)
    init.add_argument('--context',type=Path,required=True);init.add_argument('--seed-result',type=Path,required=True)
    init.add_argument('--challenge-gbw',type=float)
    init.add_argument('--include-pm',action='store_true',help='Require qualified dual-injection PM at the declared5V fixture')
    for name in ('submit','resume','status'):
        command=commands.add_parser(name);command.add_argument('--session',type=Path,required=True)
        if name!='status':command.add_argument('--ltspice',type=Path,required=True)
        if name=='submit':command.add_argument('--response',type=Path,required=True)
    args=parser.parse_args()
    if args.action=='start':state=start(args.session,args.context,args.seed_result,args.challenge_gbw,args.include_pm)
    elif args.action=='submit':state=submit(args.session,args.response,args.ltspice)
    elif args.action=='resume':state=resume(args.session,args.ltspice)
    else:state=load(args.session)
    print(json.dumps({'status':state['status'],'candidates':len(state['candidates']),
        'best':state['best_candidate_id'],'simulation_seconds':state['simulation_seconds'],
        'pending_request':state.get('pending_request'),'full_datasheet_success':False},ensure_ascii=False))

if __name__=='__main__':main()
