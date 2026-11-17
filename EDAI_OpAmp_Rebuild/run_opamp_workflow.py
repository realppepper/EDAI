"""Continuous operational circuit/instruction rounds; no effect-comparison branch."""
import argparse
import json
from pathlib import Path
from opamp_pipeline import harness_07_workflow as workflow
from opamp_pipeline.harness_01_fixed import DEFAULT_POLICY


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['start', 'propose', 'submit', 'resume', 'status'])
    p.add_argument('--session', type=Path, required=True)
    p.add_argument('--baseline-pipeline', type=Path); p.add_argument('--netlist', type=Path)
    p.add_argument('--run-dir', type=Path, default=Path('runs/lm358b_overview_20261112'))
    p.add_argument('--harness', type=Path, default=DEFAULT_POLICY)
    p.add_argument('--max-rounds', type=int, default=3); p.add_argument('--revisions-per-round', type=int, default=2)
    p.add_argument('--optuna-config',type=Path);p.add_argument('--optuna-trials',type=int,default=4);p.add_argument('--optuna-rounds',type=int,default=1)
    p.add_argument('--optuna-from-designer',action='store_true')
    p.add_argument('--response', type=Path); p.add_argument('--ltspice')
    p.add_argument('--defer-validation', action='store_true'); a = p.parse_args()
    if a.action == 'start':
        if not a.baseline_pipeline or not a.netlist: p.error('Baseline pipeline and netlist required')
        s = workflow.start(a.session, a.baseline_pipeline, a.netlist, a.run_dir,
            a.harness, a.max_rounds, a.revisions_per_round,a.optuna_config,a.optuna_trials,a.optuna_rounds,a.optuna_from_designer)
    elif a.action == 'propose':
        if not a.response: p.error('Instruction response required')
        s = workflow.propose(a.session, a.response)
    elif a.action == 'submit':
        if not a.response or not a.ltspice and not a.defer_validation: p.error('Response and LTspice required unless deferred')
        s = workflow.submit(a.session, a.response, a.ltspice, a.defer_validation)
    elif a.action == 'resume': s = workflow.resume(a.session, a.ltspice)
    else: s = workflow.resume(a.session) if workflow.load(a.session)['status'] in workflow.DONE else workflow.load(a.session)
    print(json.dumps({'status': s['status'], 'round_count': len(s['rounds']),
        'pending_request': s['pending_request'], 'best_candidate': s['active']['candidate_path'],
        'active_policy': s['active']['policy_path'], 'effect_comparison': False,
        'external_llm_api_calls': 0, 'schematic':s.get('schematic'),
        'deliverables_complete':s.get('deliverables_complete',False)}, ensure_ascii=False))


if __name__ == '__main__': main()
