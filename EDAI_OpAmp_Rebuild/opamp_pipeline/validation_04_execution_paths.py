"""Shared retry invariants and conservative content-bound raw-job reuse.

Never cache specification verdicts: callers always run today's metric code again.
Legacy entries without a bound execution signature are misses, not trusted hits.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import re
from .validation_01_results import digest,check_result,report,save_report
from .validation_03_execution_contract import validate_execution,ExecutionContractError,save_contract_receipt
from .validation_02_spice_reader import model_signature
from .tb_02_ltspice import decode_log,parse_measurements

CACHE_VERSION='verified-raw-job/1'


def semantic_deck(deck):
    lines=[];options=[]
    for line in deck.splitlines():
        line=line.split(';',1)[0].strip().lower()
        if not line or line.startswith('*') or line.startswith(('.save ','.nodeset ')):continue
        if line.startswith('.options '):
            options.extend(t for t in line.split()[1:] if not t.startswith('solver='))
        else:lines.append(' '.join(line.split()))
    return {'physical_lines':sorted(lines),'retained_options':sorted(options)}


def require_retry_equivalence(primary,fallback,meta):
    a,b=semantic_deck(primary),semantic_deck(fallback)
    checks=[check_result('retry_same_experiment','retry',a,b,a==b,
                         'only_solver_selection_nodeset_and_saved_traces_may_differ')]
    r=report('execution_contract','retry_invariants',checks)
    folder=meta.get('execution_contract_receipt_dir')
    if folder:save_contract_receipt(folder,'retry_equivalence',r)
    if r['status']!='passed':raise ExecutionContractError(r)
    return r


def _file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def include_signature(path,seen=None):
    """Recursive local include contents; absolute paths do not define equivalence."""
    return model_signature(path,seen)


def execution_signature(deck,meta):
    """Bind consumed parameters, plan/contract, included models and current code."""
    if not meta.get('execution_contract'):
        raise ExecutionContractError(report('execution_contract','cache_binding',[
            check_result('execution_contract_required','cache',True,False,False,'bound_raw_job_reuse_policy')]))
    normalized=deck;includes=[];paths=[]
    for index,m in enumerate(re.finditer(r'^\s*\.inc(?:lude)?\s+"([^"]+)"',deck,re.I|re.M)):
        path=Path(m[1]).resolve();paths.append(str(path));includes.append(include_signature(path))
        normalized=normalized.replace(m[1],f'__MODEL_{index}__')
    contract=deepcopy(meta.get('execution_contract'))
    if contract:
        # Plan fingerprints exclude output/model paths already. The expected
        # include binding is separately proved against the actual stored deck.
        for index,path in enumerate(paths):
            if contract['expected'].get('include')==path:contract['expected']['include']=f'__MODEL_{index}__'
    consumed={k:v for k,v in meta.items() if k not in {'execution_contract','execution_contract_receipt_dir','assumptions'}}
    code={p.name:_file_hash(p) for p in Path(__file__).parent.glob('*.py')}
    code.update({p.name:_file_hash(p) for p in Path(__file__).parents[1].glob('run_*.py')})
    payload={'version':CACHE_VERSION,'deck':normalized,'includes':includes,'contract':contract,
             'consumed_parameters':consumed,'code_sha256':code}
    return {'key':digest(payload),'version':CACHE_VERSION,'payload':payload}


def reusable_job(entry,deck,meta,signature):
    """Return a reusable raw job only with matching semantics and intact artifacts."""
    if not entry or not entry.get('completed') or entry.get('execution_signature')!=signature:return None
    artifacts=entry.get('artifacts',{})
    path=Path(entry['path'])
    required={str(path),str(path.with_suffix('.raw')),str(path.with_suffix('.log'))}
    if not required.issubset(artifacts):return None
    if any(not Path(p).is_file() or _file_hash(p)!=h for p,h in artifacts.items()):return None
    try:
        old_deck=path.read_text(encoding='ascii')
        parsed=parse_measurements(decode_log(path.with_suffix('.log')),meta.get('names',[]))
    except (OSError,UnicodeError,ValueError):return None
    if set(parsed)!=set(meta.get('names',[])) or parsed!=entry.get('measurements'):return None
    # Compare semantic signatures with a contract adapted only to the stored
    # include path; original source goals and all other fields remain immutable.
    old_meta=deepcopy(meta)
    if old_meta.get('execution_contract'):
        inc=re.findall(r'^\s*\.include\s+"([^"]+)"',old_deck,re.I|re.M)
        expected=old_meta['execution_contract']['expected']
        if expected.get('include') is None:
            if inc:return None
        else:
            if len(inc)!=1:return None
            expected['include']=str(Path(inc[0]).resolve())
    try:
        validate_execution(old_deck,old_meta,phase='cache_stored_deck_preflight')
        old_signature=execution_signature(old_deck,old_meta)
    except (OSError,ValueError):return None
    if old_signature!=signature:return None
    return {'path':path,'measurements':entry['measurements'],'cache_reused':True}
