"""First transistor op-amp candidate. Educational LEVEL1 models, no PDK claims."""

MODELS='''* Fixed generic MOS assumptions; NOT TI models or a fabrication PDK.
* Parameters are frozen before sizing experiments. Noise/mismatch not qualified.
.model GNM NMOS (LEVEL=1 VTO=0.65 KP=100u LAMBDA=0.02 GAMMA=0.4 PHI=0.7 TOX=20n CGSO=0.2n CGDO=0.2n)
.model GPM PMOS (LEVEL=1 VTO=-0.7 KP=40u LAMBDA=0.025 GAMMA=0.4 PHI=0.7 TOX=20n CGSO=0.2n CGDO=0.2n)
'''


def candidate(compensation_F=60e-12,nulling_Ohm=680):
    if compensation_F<=0 or nulling_Ohm<0:raise ValueError('Invalid compensation')
    return MODELS+f'''* Explicit external pin order: P N VP VM OUT
* NMOS differential pair + PMOS mirror, PMOS second gain stage, NMOS sink.
* Self-contained resistor/diode bias: NO ideal current or controlled sources.
.subckt FIRSTAMP P N VP VM OUT
Rbias VP BIAS 200k
Mref BIAS BIAS VM VM GNM W=20u L=2u
Mtail TAIL BIAS VM VM GNM W=80u L=2u
M1 DIODE N TAIL VM GNM W=80u L=2u
M2 X P TAIL VM GNM W=80u L=2u
M3 DIODE DIODE VP VP GPM W=100u L=2u
M4 X DIODE VP VP GPM W=100u L=2u
M5 OUT X VP VP GPM W=200u L=2u
M6 OUT BIAS VM VM GNM W=250u L=2u
Rzero X COMP {nulling_Ohm:.12g}
Ccomp COMP OUT {compensation_F:.12g}
.ends FIRSTAMP
'''
