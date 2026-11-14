* Fixed generic MOS assumptions; NOT TI models or a fabrication PDK.
* Parameters are frozen before sizing experiments. Noise/mismatch not qualified.
.model GNM NMOS (LEVEL=1 VTO=0.65 KP=100u LAMBDA=0.02 GAMMA=0.4 PHI=0.7 TOX=20n CGSO=0.2n CGDO=0.2n)
.model GPM PMOS (LEVEL=1 VTO=-0.7 KP=40u LAMBDA=0.025 GAMMA=0.4 PHI=0.7 TOX=20n CGSO=0.2n CGDO=0.2n)
* Explicit external pin order: P N VP VM OUT
* PMOS folded-cascode input, PMOS second gain stage, conditional NMOS sink.
* Self-contained resistor/diode bias: NO ideal current or controlled sources.
.subckt FIRSTAMP P N VP VM OUT
* Cascoded beta-multiplier, ratio4, with MOS startup
Mref BIAS BIAS VM VM GNM W=20u L=2u
Mrefcas NC NC BIAS VM GNM W=20u L=2u
Mbeta ND BIAS RS VM GNM W=80u L=2u
Mbetacas PB NC ND VM GNM W=20u L=2u
Rbeta RS VM 4020
MPtopR PG PG VP VP GPM W=100u L=2u
MPcasR PB PB PG VP GPM W=100u L=2u
MPtopL PL PG VP VP GPM W=100u L=2u
MPcasL NC PB PL VP GPM W=100u L=2u
Rstart VP START 5Meg
Mdetect START BIAS VM VM GNM W=20u L=2u
Minject VP START NC VM GNM W=2u L=2u
* Low-common-mode PMOS input, folded into a high-side cascoded mirror
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
M4cas X PCLOAD PL2 VP GPM W=100u L=2u
* Higher gm at unchanged standing sink current; source-current feedback limiter
Rsource VP PSOURCE 27
M5 OUT X PSOURCE VP GPM W=2400u L=2u
Mlimit X PSOURCE VP VP GPM W=200u L=2u
* Sink boost is normally off; first-stage high-side signal requests extra sink
MsinkSense SENSE PCLOAD X VP GPM W=100u L=2u
MsenseRef SENSE SENSE VM VM GNM W=20u L=2u
MsenseAmp PBOOST SENSE VM VM GNM W=80u L=2u
Mpd1 PF PF VP VP GPM W=100u L=2u
Mpd2 PBOOST PBOOST PF VP GPM W=100u L=2u
Rpull PBOOST VP 100k
Rpf PF VP 10Meg
McapTop PCAP PG VP VP GPM W=500u L=2u
McapCas BOOSTSUP PB PCAP VP GPM W=500u L=2u
Mdriver BOOST PBOOST BOOSTSUP VP GPM W=200u L=2u
MboostRef BOOST BOOST VM VM GNM W=20u L=2u
Rboost BOOST VM 100k
Mboost OUT BOOST VM VM GNM W=10000u L=2u
* Stabilize/filter the self-bias control node
Cbias BIAS VM 5p
M6 OUT BIAS VM VM GNM W=180u L=2u
Rzero X COMP 680
Ccomp COMP OUT 1.8e-11
* Three diode-connected PMOS devices limit deep second-stage gate windup
Maw1 AW1 AW1 VP VP GPM W=100u L=2u
Maw2 AW2 AW2 AW1 VP GPM W=100u L=2u
Maw3 X X AW2 VP GPM W=100u L=2u
* Weak off-state paths define intermediate nodes without forced initial states
Raw1 VP AW1 10000000
Raw2 AW1 AW2 10000000
Raw3 AW2 X 10000000
.ends FIRSTAMP
