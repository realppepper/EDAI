"""Independent, deliberately restricted reader for our generated fixture syntax.

Does not evaluate arbitrary SPICE expressions or import the deck generator. Unknown
relevant expressions fail closed when the execution contract asks for their value.
"""
import math
import re
import hashlib
from pathlib import Path

PREFIX = {'': 1, 't': 1e12, 'g': 1e9, 'meg': 1e6, 'k': 1e3,
          'm': 1e-3, 'u': 1e-6, 'n': 1e-9, 'p': 1e-12, 'f': 1e-15}


def number(token):
    match = re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)(meg|[tgkmunpf]?)([a-z]*)', token.strip(), re.I)
    if not match:
        raise ValueError('Unsupported SPICE numeric literal: ' + token)
    value = float(match[1]) * PREFIX[match[2].lower()]
    if not math.isfinite(value):
        raise ValueError('Nonfinite SPICE literal')
    return value


def read_deck(text):
    facts = {'elements': {}, 'commands': {}, 'includes': []}
    joined = []
    for original in text.splitlines():
        line = original.split(';', 1)[0].strip()
        if not line or line.startswith('*'):
            continue
        if line.startswith('+'):
            if not joined:
                raise ValueError('Orphan SPICE continuation')
            joined[-1] += ' ' + line[1:].strip()
        else:
            joined.append(line)
    in_subckt = False
    for line in joined:
        tokens = line.split(); name = tokens[0].lower()
        if name == '.subckt':
            in_subckt = True; continue
        if name == '.ends':
            in_subckt = False; continue
        if in_subckt:
            continue
        if name in {'.include', '.inc'}:
            facts['includes'].append(line.split(None, 1)[1].strip('"')); continue
        if name.startswith('.'):
            facts['commands'].setdefault(name, []).append(tokens[1:]); continue
        if name in facts['elements']:
            raise ValueError('Duplicate fixture element: ' + name)
        facts['elements'][name] = {'tokens': [t.lower() for t in tokens], 'line': line}
    return facts


def element(facts, name):
    return facts['elements'][name.lower()]['tokens']


def dc_value(facts, name):
    tokens = element(facts, name)
    return number(tokens[4] if tokens[3] == 'dc' else tokens[3])


def ac_value(facts,name):
    tokens=element(facts,name)
    index=tokens.index('ac')
    return number(tokens[index+1])


def pwl(facts, name):
    text = facts['elements'][name.lower()]['line']
    match = re.search(r'\bPWL\s*\(([^)]*)\)', text, re.I)
    if not match:
        raise ValueError('Expected explicit PWL input')
    values = [number(t) for t in re.split(r'[\s,]+', match[1].strip())]
    if len(values) % 2 or len(values) < 4:
        raise ValueError('Invalid PWL pairs')
    pairs = list(zip(values[::2], values[1::2]))
    if any(b[0] <= a[0] for a, b in zip(pairs, pairs[1:])):
        raise ValueError('Expected strictly increasing PWL time')
    return pairs


def command(facts, name):
    commands = facts['commands'].get(name, [])
    if len(commands) != 1:
        raise ValueError('Expected exactly one ' + name)
    return commands[0]


def model_signature(path,seen=None):
    seen=set() if seen is None else seen
    path=Path(path).resolve()
    if path in seen:raise ValueError('Cyclic model include')
    content=path.read_bytes();text=content.decode('utf-8-sig');children=[]
    for match in re.finditer(r'^\s*\.inc(?:lude)?\s+(?:"([^"]+)"|(\S+))',text,re.I|re.M):
        child=Path(match[1] or match[2]);child=child if child.is_absolute() else path.parent/child
        children.append(model_signature(child,seen|{path}))
    return {'sha256':hashlib.sha256(content).hexdigest(),'children':children}
