"""Diagnostic-only numerical changes; never loosen acceptance or force a DC state."""
def numerical_deck(deck, policy, midpoint):
    if policy not in {'normal','alternate','alternate_hint'}:
        raise ValueError('Unknown numerical diagnostic policy')
    extra=''
    if policy!='normal':extra+='.options solver=alt\n'
    if policy=='alternate_hint':
        extra+=f'.nodeset V(out)={midpoint:.12g} V(dout)={midpoint:.12g} V(inp)={midpoint:.12g} V(inn)={midpoint:.12g} V(vid)=0\n'
    if deck.count('.end\n')!=1:raise ValueError('Expected one top-level end')
    return deck.replace('.end\n',extra+'.end\n')
