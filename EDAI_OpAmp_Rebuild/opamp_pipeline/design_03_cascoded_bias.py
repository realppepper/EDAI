"""Supply-insensitive MOS beta-multiplier proposal; frozen models unchanged.

Both PMOS mirror and NMOS ratio branch are cascoded. Startup is a resistor,
an NMOS detector and an NMOS injector, not an ideal bias current/reference.
"""
from .design_01_cmos_candidate import candidate


def cascoded_bias(resistance=4020):
    if resistance<=0:raise ValueError('Positive beta resistance required')
    original=candidate(45e-12,680)
    old='Rbias VP BIAS 200k\nMref BIAS BIAS VM VM GNM W=20u L=2u'
    replacement=f'''* Cascoded beta-multiplier, ratio4, with MOS startup
Mref BIAS BIAS VM VM GNM W=20u L=2u
Mrefcas NC NC BIAS VM GNM W=20u L=2u
Mbeta ND BIAS RS VM GNM W=80u L=2u
Mbetacas PB NC ND VM GNM W=20u L=2u
Rbeta RS VM {resistance:.12g}
MPtopR PG PG VP VP GPM W=100u L=2u
MPcasR PB PB PG VP GPM W=100u L=2u
MPtopL PL PG VP VP GPM W=100u L=2u
MPcasL NC PB PL VP GPM W=100u L=2u
Rstart VP START 5Meg
Mdetect START BIAS VM VM GNM W=20u L=2u
Minject VP START NC VM GNM W=2u L=2u'''
    if old not in original:raise ValueError('Baseline structure changed')
    return original.replace(old,replacement)


def enhanced_output():
    text=cascoded_bias()
    text=text.replace('M5 OUT X VP VP GPM W=200u L=2u',
        '''* Higher gm at unchanged standing sink current; source-current feedback limiter
Rsource VP PSOURCE 27
M5 OUT X PSOURCE VP GPM W=2000u L=2u
Mlimit X PSOURCE VP VP GPM W=200u L=2u
* Sink boost is normally off; first-stage high-side signal requests extra sink
MsinkSense BOOST DIODE X VP GPM W=100u L=2u
MboostRef BOOST BOOST VM VM GNM W=20u L=2u
Mboost OUT BOOST VM VM GNM W=800u L=2u
* Stabilize/filter the self-bias control node
Cbias BIAS VM 5p''')
    return text
