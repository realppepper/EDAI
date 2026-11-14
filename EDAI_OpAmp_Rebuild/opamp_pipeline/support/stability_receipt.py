"""Apply the numerical PM qualification only to the verified fixture/topology."""
import json
from pathlib import Path
from ..design_01_cmos_candidate import MODELS
from ..tb_06_loop_gain import METHOD
from .source_checks import fingerprint
from .execution_state import file_hash


def topology_signature(text):
    if not text.startswith(MODELS):raise ValueError('Unqualified MOS models')
    rows=[]
    for line in text[len(MODELS):].splitlines():
        tokens=line.upper().split()
        if not tokens or tokens[0].startswith('*'):continue
        if tokens[0].startswith('.'):
            rows.append(tokens)
        elif tokens[0].startswith('M'):rows.append(tokens[:6])
        elif tokens[0][0] in 'RC':rows.append(tokens[:3])
        else:raise ValueError('Unqualified topology')
    return fingerprint(rows)


def current_qualification(model,receipt_path,load_R=10000,load_C=20e-12):
    receipt_path=Path(receipt_path)
    try:
        receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
        module=Path(__file__).resolve().parents[1]/'tb_06_loop_gain.py'
        result_path=Path(receipt['result_path'])
        if receipt.get('status')!='passed' or receipt.get('method')!=METHOD:raise ValueError('Receipt not passed')
        if file_hash(module)!=receipt['module_sha256'] or file_hash(result_path)!=receipt['result_sha256']:raise ValueError('Qualification evidence changed')
        result=json.loads(result_path.read_text(encoding='utf-8'))
        if result.get('status')!='passed' or not result.get('checks') or not all(c['passed'] for c in result['checks']):raise ValueError('Reference validation failed')
        tested=result_path.parent/'actual_candidate.inc'
        if file_hash(tested)!=receipt['tested_actual_candidate_sha256']:raise ValueError('Tested candidate changed')
        if topology_signature(Path(model).read_text(encoding='ascii'))!=topology_signature(tested.read_text(encoding='ascii')):
            raise ValueError('Topology outside validated scope')
        if load_R!=10000 or not any(abs(load_C*1e12-c)<1e-6 for c in receipt['tested_actual_loads_pF']):raise ValueError('Load outside validated scope')
        return {'qualified':True,'status':'validated_for_current_fixture','receipt_path':str(receipt_path.resolve()),
            'receipt_sha256':file_hash(receipt_path),'scope':'Same frozen models/connectivity,5V/25C,unity feedback,10kOhm,20pF or100pF; single downward crossover required.'}
    except (OSError,ValueError,KeyError,TypeError) as error:
        return {'qualified':False,'status':'not_qualified_for_current_fixture','reason':str(error)}
