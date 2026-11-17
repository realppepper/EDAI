"""Retry a numerical failure without changing the circuit, tolerances or acceptance."""
from .tb_02_ltspice import run_bench
import re


def measured_trace_deck(deck,meta):
    """Select saved columns only; retain all solver timepoints and circuit equations."""
    analysis=meta['analysis'];kind=meta.get('kind')
    signals=None
    if analysis=='tran':signals='V(out) V(inp)'
    elif analysis=='dc':
        signals={'vcm':'V(out) V(inp) I(VSENSE)',
                 'cmrr':'V(out) V(mid) V(vid) V(cm)',
                 'psrr':'V(out) V(mid) V(vid) V(vsw)',
                 'aol':'V(out) V(target) V(vid)'}.get(kind)
    elif analysis=='op':
        signals='V(out) I(VSENSE)'
        if kind in {'iq','vos','ib','ios'}:signals+=' V(mid) V(vid) I(VDD) I(EP) I(EN)'
    elif analysis=='ac':
        if kind in {'gbw','ro'}:signals='V(out)'
        elif kind in {'pm','capacitive_drive'}:signals='V(xv) V(xi) V(yv) V(yi) I(Vprobev) I(Vprobei)'
    if signals is None:return deck
    if re.search(r'^\.save\b',deck,re.M|re.I):
        return re.sub(r'^\.save[^\r\n]*','.save '+signals,deck,flags=re.M|re.I)
    return deck.replace('.end\n','.save '+signals+'\n.end\n')


class SolverAttemptsError(RuntimeError):
    def __init__(self,attempts):
        self.attempts=attempts
        super().__init__('; '.join(f"{a['path']}: {a.get('error','')}" for a in attempts))


def run_with_fallback(executable,path,names,ascii_raw,timeout,fallback_deck,meta=None):
    from .validation_03_execution_contract import validate_execution
    from .validation_04_execution_paths import require_retry_equivalence
    if meta is not None:
        # A contract error is not a solver error. Validate both paths outside the
        # retry handler and never use retries to conceal a changed experiment.
        primary=path.read_text(encoding='ascii')
        validate_execution(primary,meta,phase='retry_primary_preflight')
        validate_execution(fallback_deck,meta,phase='retry_fallback_preflight')
        require_retry_equivalence(primary,fallback_deck,meta)
    attempts=[]
    for policy in ('startup_seeded','normal_retry'):
        if policy=='normal_retry':
            folder=path.parent/'normal_retry';folder.mkdir()
            path=folder/'bench.cir';path.write_text(fallback_deck,encoding='ascii')
        record={'policy':policy,'path':str(path)}
        if meta is not None:
            validate_execution(path.read_text(encoding='ascii'),meta,phase='retry_attempt_preflight')
        try:
            run=run_bench(executable,path,names,ascii_raw=ascii_raw,timeout=timeout)
            attempts.append({**record,'status':'computed'})
            return {'run':run,'path':path,'attempts':attempts}
        except Exception as error:
            attempts.append({**record,'status':'execution_error','error':str(error)})
    raise SolverAttemptsError(attempts)
