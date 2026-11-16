"""Reviewed fixed instructions and enforced DUT boundaries; no provider or Harness² calls."""
import json,re
from pathlib import Path
from .loop_02_handoff import validate_dut
from .support.execution_state import file_hash

DEFAULT_POLICY=Path(__file__).resolve().parents[1]/'harness/fixed_v3_history.json'


def load_harness(path=DEFAULT_POLICY):
    path=Path(path);policy=json.loads(path.read_text(encoding='utf-8'))
    if policy['mode']!='fixed' or policy['harness2_enabled'] or policy['external_designer_api_enabled']:
        raise ValueError('This integration requires fixed manual-chat instructions')
    if {c['id'] for c in policy['components']}!={f'C{i}' for i in range(1,9)}:raise ValueError('Incomplete harness inventory')
    return policy,file_hash(path)


def validate_candidate(text):
    text.encode('ascii')
    validate_dut(text)
    nodes=set()
    for line in text.splitlines():
        fields=line.split()
        if not fields or fields[0][0].upper() not in {'M','R','C'}:continue
        local=fields[1:5] if fields[0][0].upper()=='M' else fields[1:3]
        if '0' in local:raise ValueError('DUT internal references must use VM/VP, not external node0')
        nodes.update(n.upper() for n in local)
    if 'BIAS' not in nodes:raise ValueError('BIAS observer is required by the current startup contract')
    return True


def system_text(policy):
    lines=[f"Fixed harness: {policy['id']}",'Instructions are frozen for this loop. No instruction evolution or provider calls.']
    for c in policy['components']:
        if c['enabled']:
            lines+=['',c['id']+' '+c['title'],*[f"[{r['id']}] {r['text']}" for r in c['rules']]]
    return '\n'.join(lines)
