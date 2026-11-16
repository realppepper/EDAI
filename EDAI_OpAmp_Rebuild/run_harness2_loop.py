"""Instruction proposal -> fixed control/probe loops -> whole-policy decision."""
import argparse
import json
from pathlib import Path
from opamp_pipeline import harness_06_evolution as evolution
from opamp_pipeline.harness_01_fixed import DEFAULT_POLICY


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['start', 'propose', 'submit', 'resume', 'decide', 'status', 'rollback'])
    p.add_argument('--session', type=Path, required=True)
    p.add_argument('--baseline-pipeline', type=Path)
    p.add_argument('--netlist', type=Path)
    p.add_argument('--run-dir', type=Path, default=Path('runs/lm358b_overview_20261112'))
    p.add_argument('--harness', type=Path, default=DEFAULT_POLICY)
    p.add_argument('--response', type=Path)
    p.add_argument('--branch')
    p.add_argument('--ltspice')
    p.add_argument('--defer-validation', action='store_true')
    p.add_argument('--reason')
    a = p.parse_args()
    if a.action == 'start':
        if not a.baseline_pipeline or not a.netlist:
            p.error('start requires baseline-pipeline and netlist')
        s = evolution.start(a.session, a.baseline_pipeline, a.netlist, a.run_dir, a.harness)
    elif a.action == 'propose':
        if not a.response: p.error('proposal response required')
        s = evolution.propose(a.session, a.response)
    elif a.action == 'submit':
        if not a.branch or not a.response or (not a.ltspice and not a.defer_validation):
            p.error('branch, response and LTspice required unless deferring validation')
        evolution.submit(a.session, a.branch, a.response, a.ltspice, a.defer_validation)
        s = evolution.load(a.session)
    elif a.action == 'resume':
        if not a.branch or not a.ltspice: p.error('branch and LTspice required')
        evolution.resume(a.session, a.branch, a.ltspice); s = evolution.load(a.session)
    elif a.action == 'decide': s = evolution.decide(a.session)
    elif a.action == 'rollback': s = evolution.rollback(a.session, a.reason)
    else: s = evolution.load(a.session)
    print(json.dumps({'status': s['status'], 'harness2_enabled': True,
        'branches': s['branches'], 'decision': s['decision'],
        'external_llm_api_calls': 0, 'global_default_modified': False}, ensure_ascii=False))


if __name__ == '__main__': main()
