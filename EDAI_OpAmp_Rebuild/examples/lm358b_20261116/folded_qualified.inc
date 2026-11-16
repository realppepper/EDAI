* Fixed generic MOS assumptions; NOT TI models or a fabrication PDK.
* Parameters are frozen before sizing experiments. Noise/mismatch not qualified.
.model GNM NMOS (LEVEL=1 VTO=0.65 KP=100u LAMBDA=0.02 GAMMA=0.4 PHI=0.7 TOX=20n CGSO=0.2n CGDO=0.2n)
.model GPM PMOS (LEVEL=1 VTO=-0.7 KP=40u LAMBDA=0.025 GAMMA=0.4 PHI=0.7 TOX=20n CGSO=0.2n CGDO=0.2n)
.subckt FIRSTAMP P N VP VM OUT
* Cascoded resistor-set beta reference and physical cold-start paths.
MNBR BIAS BIAS VM VM GNM W=20u L=8u
MNBL NB BIAS RS VM GNM W=80u L=8u
MNBC BP NC2 NB VM GNM W=160u L=4u
MPBR BP BP VP VP GPM W=200u L=8u
MPBL PB BP VP VP GPM W=200u L=8u
MPBC BIAS PC PB VP GPM W=400u L=4u
RBETA RS VM 8.2k
RSTART VP BIAS 10Meg
RBOOTN VP NC2 5Meg
RBOOTP PC VM 5Meg
* Low-side current and folded-cascode gate biases.
MPNL1 PNL BP VP VP GPM W=200u L=8u
MPNL2 NL PC PNL VP GPM W=400u L=4u
MNNL NL NL VM VM GNM W=160u L=4u
MPNC1 PNC BP VP VP GPM W=200u L=8u
MPNC2 NC PC PNC VP GPM W=400u L=4u
MNNC NC NC VM VM GNM W=35.6u L=8u
MPNB1 PNB BP VP VP GPM W=200u L=8u
MPNB2 NC2 PC PNB VP GPM W=400u L=4u
MNNB1 NC1 NC1 VM VM GNM W=160u L=4u
MNNB2 NC2 NC2 NC1 VM GNM W=160u L=4u
* High-side wide-swing cascode bias, with cascoded current sink.
MPPC PC PC VP VP GPM W=25u L=4u
MNPC1 NPC NL VM VM GNM W=160u L=4u
MNPC2 PC NC2 NPC VM GNM W=160u L=4u
* Ground-sensing PMOS input pair and cascoded tail.
MPT1 TS BP VP VP GPM W=400u L=8u
MPT2 S PC TS VP GPM W=400u L=4u
MIP FP P S S GPM W=32u L=2u
MIN FN N S S GPM W=32u L=2u
* Folded currents and wide-swing cascoded P mirror.
MNFP0 FP NL VM VM GNM W=320u L=4u
MNFN0 FN NL VM VM GNM W=320u L=4u
MNFP1 X NC FP VM GNM W=100u L=4u
MNFN1 PT NC FN VM GNM W=100u L=4u
MPR1 PA PT VP VP GPM W=400u L=4u
MPR2 PT PC PA VP GPM W=400u L=4u
MPS1 PS PT VP VP GPM W=400u L=4u
MPS2 X PC PS VP GPM W=400u L=4u
* Common-source output, standing sink, and source-drive gate clamp.
MPOUT OUT X VP VP GPM W=1600u L=1u
MNSTAND OUT NL VM VM GNM W=1280u L=4u
MPCL1 CP CP VP VP GPM W=320u L=4u
MPCL2 X X CP CP GPM W=320u L=4u
* Floating high-rail detector reference, with a physical sink buffer.
MPH1 H1 H1 VP VP GPM W=900u L=1u
MNH2 H1 H1 H2 H2 GNM W=360u L=1u
MPH3 HBUF HBUF H2 H2 GPM W=900u L=1u
MNHB1 HB NL VM VM GNM W=80u L=4u
MNHB2 HBUF NC2 HB VM GNM W=160u L=4u
MPHR HREF BP VP VP GPM W=200u L=8u
MPHF VM HBUF HREF HREF GPM W=1000u L=1u
* Additional sinking is demanded when the main P output turns off.
MNDET PD X HREF HREF GNM W=20u L=2u
MPAR1 AP PD VP VP GPM W=1000u L=1u
MPAR2 PD PC AP VP GPM W=1000u L=1u
MPAS1 AQ PD VP VP GPM W=1000u L=1u
MPAS2 ND PC AQ VP GPM W=1000u L=1u
MNAR ND ND VM VM GNM W=160u L=1u
MNAOUT OUT ND VM VM GNM W=32000u L=1u
* These paths discharge otherwise-off detector mirror nodes.
RPD VP PD 1Meg
RAP VP AP 1Meg
RAQ VP AQ 1Meg
RND ND VM 50k
* Miller capacitor and estimated output-stage zero compensation.
RCOMP X CCN 330
CCOMP CCN OUT 12p
.ends FIRSTAMP
