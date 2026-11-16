"""Deterministic LTspice DUT drawings for the current physical M/R/C adapter.

Same-name labels join terminals. This is a DUT sheet, not a powered testbench.
No simulator or design provider is invoked by publication.
"""
import json
from pathlib import Path
from .harness_01_fixed import validate_candidate
from .support.atomic_files import atomic_write_bytes, atomic_write_text
from .support.execution_state import file_hash


def _elements(text):
    return {s.split()[0].upper(): [t.upper() for t in s.split()[1:]]
            for s in text.splitlines() if s.strip() and s.strip()[0].upper() in 'MRC'
            and not s.lstrip().startswith('*')}


def drawing(text):
    validate_candidate(text)
    parts = _elements(text)
    columns = 4
    height = 240 + ((len(parts) + columns - 1) // columns) * 272
    lines = ['Version 4', f'SHEET 1 2200 {height + 160}',
        'TEXT 32 24 Left 4 ;FIRSTAMP - final selected circuit',
        'TEXT 32 80 Left 2 ;P: input+ | N: input- | VP/VM: supply | OUT: output',
        'TEXT 32 112 Left 2 ;Matching net labels connect. Explicit MOS bulk terminals are retained.',
        'TEXT 32 144 Left 2 ;DUT only: power, input, load and analyses belong to the separate testbench.']
    for i, (name, fields) in enumerate(parts.items()):
        x, y = 80 + i % columns * 528, 224 + i // columns * 272
        kind = name[0]
        if kind == 'M':
            symbol = 'nmos4' if fields[4] == 'GNM' else 'pmos4'
            # Both symbols share these R0 pin coordinates: drain, gate, source, bulk.
            pins = [(x+48,y), (x,y+80), (x+48,y+96), (x+48,y+48)]
            ends = [(x+48,y-32), (x-32,y+80), (x+48,y+128), (x+112,y+48)]
            nodes = fields[:4]
            attrs = [f'SYMATTR Value {fields[4]}', 'SYMATTR SpiceLine '+' '.join(fields[5:])]
        else:
            symbol = 'res' if kind == 'R' else 'cap'
            pins = [(x+16,y+(16 if kind == 'R' else 0)),
                    (x+16,y+(96 if kind == 'R' else 64))]
            ends = [(pins[0][0],pins[0][1]-32),(pins[1][0],pins[1][1]+32)]
            nodes = fields[:2]
            attrs = [f'SYMATTR Value {fields[2]}']
        for a, b, node in zip(pins, ends, nodes):
            lines += [f'WIRE {a[0]} {a[1]} {b[0]} {b[1]}', f'FLAG {b[0]} {b[1]} {node}']
        lines += [f'SYMBOL {symbol} {x} {y} R0', 'WINDOW 0 128 8 Left 2',
                  'WINDOW 3 128 104 Left 1', f'SYMATTR InstName {name}', *attrs]
    for i, line in enumerate(s for s in text.splitlines() if s.lower().startswith('.model')):
        lines.append(f'TEXT 32 {height+i*40} Left 1 !{line}')
    return '\r\n'.join(lines)+'\r\n'


def verify_drawing(text, asc):
    """Independently recover connectivity from symbol pins, wires and labels."""
    flags, wires, devices, models = {}, {}, [], []
    for line in asc.splitlines():
        f = line.split()
        if not f: continue
        if f[0] == 'FLAG': flags[tuple(map(int,f[1:3]))] = f[3].upper()
        elif f[0] == 'WIRE':
            a,b=tuple(map(int,f[1:3])),tuple(map(int,f[3:5]))
            wires.setdefault(a,[]).append(b); wires.setdefault(b,[]).append(a)
        elif f[0] == 'SYMBOL': devices.append({'symbol':f[1], 'x':int(f[2]), 'y':int(f[3]), 'attrs':{}})
        elif f[0] == 'SYMATTR': devices[-1]['attrs'][f[1]]=' '.join(f[2:])
        elif f[0] == 'TEXT' and ' !.model ' in line.lower(): models.append(line.split(' !',1)[1].upper().split())
    def net(point):
        todo, seen, names = [point], set(), set()
        while todo:
            p=todo.pop()
            if p in seen: continue
            seen.add(p)
            if p in flags: names.add(flags[p])
            todo.extend(wires.get(p,[]))
        if len(names)!=1: raise ValueError('Ambiguous or missing schematic terminal label')
        return next(iter(names))
    recovered = {}
    for dev in devices:
        x,y,a=dev['x'],dev['y'],dev['attrs']; sym=dev['symbol']
        if sym in ('nmos4','pmos4'):
            points=[(x+48,y),(x,y+80),(x+48,y+96),(x+48,y+48)]
            tail=[a['Value'],*a['SpiceLine'].split()]
            if sym != ('nmos4' if a['Value']=='GNM' else 'pmos4'): raise ValueError('Wrong MOS symbol')
        elif sym in ('res','cap'):
            points=[(x+16,y+(16 if sym=='res' else 0)),(x+16,y+(96 if sym=='res' else 64))]
            tail=[a['Value']]
        else: raise ValueError('Unsupported schematic symbol')
        name=a['InstName'].upper()
        if name in recovered: raise ValueError('Duplicate schematic device')
        recovered[name]=[net(p) for p in points]+[v.upper() for v in tail]
    original_models=[s.upper().split() for s in text.splitlines() if s.lower().startswith('.model')]
    if recovered != _elements(text) or models != original_models:
        raise ValueError('Schematic/source device, connection, parameter or model mismatch')
    return len(recovered)


def export(source, folder):
    source, folder = Path(source).resolve(), Path(folder).resolve()
    raw=source.read_bytes(); text=raw.decode('ascii').replace('\r\n','\n')
    asc=drawing(text); count=verify_drawing(text,asc)
    payloads={'FIRSTAMP.asc':asc.encode('ascii'),'candidate_source.inc':raw}
    # Preserve conflicting artifacts; never silently replace an edited schematic.
    for name, data in payloads.items():
        p=folder/name
        if p.exists() and p.read_bytes()!=data: raise ValueError('Existing schematic artifact differs: '+str(p))
    manifest=folder/'MANIFEST.json'
    expected={'schema_version':1,'source_path':str(source),'source_sha256':file_hash(source),
        'schematic_path':str(folder/'FIRSTAMP.asc'),'matched_elements':count,
        'connectivity_and_parameters':'passed_static_roundtrip',
        'native_netlist_verification':'not_run','simulation_performed':False,
        'scope':'Current generic MOS M/R/C adapter; DUT only; same-name labels connect.'}
    if manifest.exists():
        old=json.loads(manifest.read_text(encoding='utf-8'))
        if old != expected: raise ValueError('Existing schematic manifest differs')
    for name,data in payloads.items():
        if not (folder/name).exists(): atomic_write_bytes(folder/name,data)
    if not manifest.exists(): atomic_write_text(manifest,json.dumps(expected,indent=2)+'\n')
    paths=[folder/name for name in payloads]+[manifest]
    return {'status':'completed','source_sha256':expected['source_sha256'],
        'schematic_path':str(folder/'FIRSTAMP.asc'),'manifest_path':str(manifest),
        'artifact_hashes':{str(p):file_hash(p) for p in paths}}


def complete(session, state, candidate):
    """Publish after electrical success; retry publication independently on resume."""
    state['deliverables_complete']=False
    try:
        if file_hash(candidate['candidate_path']) != candidate['candidate_sha256']:
            raise ValueError('Selected successful candidate changed')
        old=state.get('schematic',{})
        if old.get('status')=='completed':
            if old['source_sha256'] != candidate['candidate_sha256']: raise ValueError('Schematic belongs to another candidate')
            for p,sha in old['artifact_hashes'].items():
                if file_hash(p)!=sha: raise ValueError('Published schematic artifact changed')
        state['schematic']=export(candidate['candidate_path'],Path(session)/'schematic')
        state['deliverables_complete']=True
    except Exception as error:
        state['schematic']={'status':'export_failed','error_type':type(error).__name__,
            'error':str(error),'previous_artifact_hashes':state.get('schematic',{}).get('artifact_hashes',{})}
    return state['schematic']


def report_lines(state):
    item=state.get('schematic',{})
    if not item: return []
    return ['', '## Final schematic', f"Artifact completion: {state.get('deliverables_complete',False)}",
        f"Schematic export: {item['status']}",
        f"File: {item.get('schematic_path','not available')}",
        *([f"Export error: {item['error']}"] if item.get('error') else []),
        'Electrical scope success is distinct from full datasheet/manufacturing qualification.']
