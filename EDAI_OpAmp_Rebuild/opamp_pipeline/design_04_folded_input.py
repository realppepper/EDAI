"""PMOS input folded-cascode proposal for the remaining input-range/gain goals."""
from .design_03_cascoded_bias import enhanced_output


def folded_candidate():
    text=enhanced_output()
    old='''Mtail TAIL BIAS VM VM GNM W=80u L=2u
M1 DIODE N TAIL VM GNM W=80u L=2u
M2 X P TAIL VM GNM W=80u L=2u
M3 DIODE DIODE VP VP GPM W=100u L=2u
M4 X DIODE VP VP GPM W=100u L=2u'''
    new='''* Low-common-mode PMOS input, folded into a high-side cascoded mirror
Mpcbot PCN BIAS VM VM GNM W=30u L=2u
Mpccas PCLOAD NC PCN VM GNM W=30u L=2u
Mpc PCLOAD PCLOAD VP VP GPM W=8u L=2u
Mtailtop TP PG VP VP GPM W=300u L=2u
Mtail TAILP PCLOAD TP VP GPM W=300u L=2u
M1 F1 N TAILP VP GPM W=200u L=2u
M2 F2 P TAILP VP GPM W=200u L=2u
Mbottom1 F1 BIAS VM VM GNM W=90u L=2u
Mbottom2 F2 BIAS VM VM GNM W=90u L=2u
Mfold1 DIODE NC F1 VM GNM W=40u L=2u
Mfold2 X NC F2 VM GNM W=40u L=2u
M3 PL1 DIODE VP VP GPM W=100u L=2u
M3cas DIODE PCLOAD PL1 VP GPM W=100u L=2u
M4 PL2 DIODE VP VP GPM W=100u L=2u
M4cas X PCLOAD PL2 VP GPM W=100u L=2u'''
    if old not in text:raise ValueError('Baseline input block changed')
    return (text.replace(old,new)
        .replace('M5 OUT X PSOURCE VP GPM W=2000u','M5 OUT X PSOURCE VP GPM W=2400u')
        .replace('MsinkSense BOOST DIODE X VP','MsinkSense BOOST PCLOAD X VP')
        .replace('Mboost OUT BOOST VM VM GNM W=800u','Mboost OUT BOOST VM VM GNM W=8000u')
        .replace('M6 OUT BIAS VM VM GNM W=250u','M6 OUT BIAS VM VM GNM W=180u'))


def buffered_sink_candidate():
    """Amplify the conditional sink request without loading the high-gain node heavily."""
    text=folded_candidate()
    old='''MsinkSense BOOST PCLOAD X VP GPM W=100u L=2u
MboostRef BOOST BOOST VM VM GNM W=20u L=2u
Mboost OUT BOOST VM VM GNM W=8000u L=2u'''
    new='''MsinkSense SENSE PCLOAD X VP GPM W=100u L=2u
MsenseRef SENSE SENSE VM VM GNM W=20u L=2u
MsenseAmp PBOOST SENSE VM VM GNM W=800u L=2u
Mpd1 PF PF VP VP GPM W=100u L=2u
Mpd2 PBOOST PBOOST PF VP GPM W=100u L=2u
Rpull PBOOST VP 200k
McapTop PCAP PG VP VP GPM W=500u L=2u
McapCas BOOSTSUP PB PCAP VP GPM W=500u L=2u
Mdriver BOOST PBOOST BOOSTSUP VP GPM W=200u L=2u
MboostRef BOOST BOOST VM VM GNM W=20u L=2u
Rboost BOOST VM 100k
Mboost OUT BOOST VM VM GNM W=10000u L=2u'''
    if old not in text:raise ValueError('Conditional sink block changed')
    return text.replace(old,new)


def damped_sink_candidate(compensation_F=60e-12):
    """Reduce conditional-path gain and strengthen physical Miller compensation."""
    return (buffered_sink_candidate()
        .replace('MsenseAmp PBOOST SENSE VM VM GNM W=800u','MsenseAmp PBOOST SENSE VM VM GNM W=80u')
        .replace('Rpull PBOOST VP 200k','Rpull PBOOST VP 100k')
        .replace('Ccomp COMP OUT 4.5e-11',f'Ccomp COMP OUT {compensation_F:.12g}'))


def stabilized_sink_candidate():
    """Give the off-state clamp midpoint a defined, weak physical path to the rail."""
    return (damped_sink_candidate(20e-12)
        .replace('Rpull PBOOST VP 100k','Rpull PBOOST VP 100k\nRpf PF VP 10Meg')
        .replace('* NMOS differential pair + PMOS mirror, PMOS second gain stage, NMOS sink.',
                 '* PMOS folded-cascode input, PMOS second gain stage, conditional NMOS sink.'))
