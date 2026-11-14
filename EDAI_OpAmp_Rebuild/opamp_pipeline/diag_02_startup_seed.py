"""Physical-ramp-derived initial guesses; no .ic, UIC, tolerance relaxation or added DUT elements."""
import math,re
from pathlib import Path


def internal_nodes(text):
    nodes=set()
    for line in text.splitlines():
        f=line.split()
        if not f:continue
        if f[0][0].upper()=='M':nodes.update(f[1:5])
        elif f[0][0].upper() in {'R','C'}:nodes.update(f[1:3])
    return sorted(nodes-{'P','N','VP','VM','OUT'})


def startup_deck(model,supply):
    if not math.isfinite(supply) or supply<=0:raise ValueError('Invalid startup supply')
    explicit=' '.join(f'V(xdut:{n})' for n in internal_nodes(Path(model).read_text(encoding='ascii')))
    return f'''* Zero-source physical ramp; steady voltages only seed a later unrestricted solve
.include "{Path(model).resolve()}"
.temp 25
.options plotwinsize=0 numdgt=15 solver=alt itl4=100
VDD vp 0 PWL(0 0 5u 0 15u {supply:.12g} 100u {supply:.12g})
BMID mid 0 V=V(vp)/2
XDUT mid out vp 0 out FIRSTAMP
RL out mid 10k
CL out mid 20p
.save V(*) I(*) {explicit}
.tran 0 100u 0 200n
.end
'''


def seeds_from_waveform(raw,supply,expected_nodes):
    tail=[i for i,t in enumerate(raw['time']) if t>=80e-6]
    if not tail or raw['time'][-1]<99.98e-6:raise ValueError('Incomplete physical startup')
    seeds={n.lower():raw[f'v(xdut:{n.lower()})'][-1] for n in expected_nodes}
    if not all(math.isfinite(v) for v in seeds.values()):raise ValueError('Nonfinite startup seed')
    span=max(max(raw[f'v(xdut:{n.lower()})'][i] for i in tail)-min(raw[f'v(xdut:{n.lower()})'][i] for i in tail) for n in expected_nodes)
    if span>.005 or abs(raw['v(out)'][-1]-supply/2)>.01 or seeds['bias']<=.65:
        raise ValueError('Startup did not settle to an active midpoint state')
    return seeds,{'max_internal_tail_span_V':span,'output_final_V':raw['v(out)'][-1],'bias_final_V':seeds['bias']}


def supply_from_deck(deck):
    def source(name,node):
        m=re.search(rf'^{name}\s+{node}\s+0\s+([-+0-9.eE]+)\s*$',deck,re.M|re.I)
        return float(m[1]) if m else None
    plus=source('VDD','vp');minus=source('VSS','vm') or 0
    total=plus-minus if plus is not None else source('VSW','vsw')
    if total is None or total<=0:raise ValueError('Unknown nominal supply in DUT fixture')
    return total,minus


def seeded_deck(deck,seeds,negative_rail=0):
    if '.ic ' in deck.lower() or ' uic' in deck.lower():raise ValueError('Forced initial state is not allowed')
    instances=re.findall(r'^(X\S+)\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+FIRSTAMP\s*$',deck,re.M|re.I)
    if not instances:raise ValueError('No known DUT instance')
    hints=[f'V({instance}:{node})={value+negative_rail:.15g}' for instance in instances for node,value in sorted(seeds.items())]
    if deck.count('.end\n')!=1:raise ValueError('Expected one top-level end')
    return deck.replace('.end\n','.options solver=alt\n.nodeset '+' '.join(hints)+'\n.end\n')
