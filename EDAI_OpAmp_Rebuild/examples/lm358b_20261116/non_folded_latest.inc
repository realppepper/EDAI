* Fixed generic MOS assumptions; NOT TI models or a fabrication PDK.
* Parameters are frozen before sizing experiments. Noise/mismatch not qualified.
.model GNM NMOS (LEVEL=1 VTO=0.65 KP=100u LAMBDA=0.02 GAMMA=0.4 PHI=0.7 TOX=20n CGSO=0.2n CGDO=0.2n)
.model GPM PMOS (LEVEL=1 VTO=-0.7 KP=40u LAMBDA=0.025 GAMMA=0.4 PHI=0.7 TOX=20n CGSO=0.2n CGDO=0.2n)

.subckt FIRSTAMP P N VP VM OUT
* Cascoded physical beta reference with two explicit cold-start paths
MNB1 BIAS BIAS VM VM GNM W=10u L=1u
MNB2 NB2 BIAS RS RS GNM W=40u L=1u
RBIAS RS VM 15k
MNC1 BN1 NC BIAS BIAS GNM W=10u L=1u
MNC2 BN2 NC NB2 NB2 GNM W=10u L=1u
MPB1 PB PB VP VP GPM W=10u L=1u
MPB2 PBM PB VP VP GPM W=10u L=1u
MPC1 BN2 PC PB PB GPM W=10u L=1u
MPC2 BN1 PC PBM PBM GPM W=10u L=1u
MPNC NC PB VP VP GPM W=10u L=1u
MNNC1 NC NC NC1 NC1 GNM W=10u L=1u
MNNC2 NC1 NC1 VM VM GNM W=10u L=1u
MNPC PC BIAS VM VM GNM W=10u L=1u
MPPC1 PC1 PC1 VP VP GPM W=10u L=1u
MPPC2 PC PC PC1 PC1 GPM W=10u L=1u
RSTART VP BIAS 100Meg
RSTARTNC VP NC 100Meg
* Cascode-isolated current sink for floating level-reference stack
MNSTACK0 NSB BIAS VM VM GNM W=10u L=1u
MNSTACK BP2 NC NSB NSB GNM W=10u L=1u
MPSTACK1 BP1 BP1 VP VP GPM W=5u L=1u
MPSTACK2 BP2 BP2 BP1 BP1 GPM W=5u L=1u
* Conventional PMOS differential pair with ordinary NMOS mirror load
MTAIL TAIL BP1 VP VP GPM W=200u L=1u
MIP DREF P TAIL TAIL GPM W=100u L=1u
MIN X N TAIL TAIL GPM W=100u L=1u
MNREF DREF DREF VM VM GNM W=200u L=0.1u
MNLOAD X DREF VM VM GNM W=200u L=0.1u
* Signal-steering-derived physical recharge current for the VAS gate node
MNCHARGE0 NCH DREF VM VM GNM W=200u L=0.1u
MNCHARGE BPC NC NCH NCH GNM W=200u L=0.1u
MPCHREF BPC BPC VP VP GPM W=20u L=1u
MPCHARGE YP BPC VP VP GPM W=20u L=1u
* Common-source intermediate stage and faster shunt translator
MNGAIN YP X VM VM GNM W=600u L=0.1u
MPDRIVER YP BP1 VP VP GPM W=20u L=1u
MPLEVEL YN BP2 YP YP GPM W=10u L=1u
MNDIODE YN YN VM VM GNM W=200u L=1u
* Complementary common-source output; sink current bounded through gate mirror
MPOUT OUT YP PSOUT PSOUT GPM W=20u L=0.1u
RPLIMIT VP PSOUT 200
MNOUT OUT YN VM VM GNM W=6000u L=0.1u
* Physical VAS recovery path and earlier compensation lead zero
RRECHARGE VP YP 50k
* Adjacent-stage compensation; final unmeasured joint hypothesis
RCOMP1 X CX 3k
CCOMP1 CX YP 47p
RCOMP2 YP CY 330
CCOMP2 CY OUT 100p
* Physical anti-saturation bounds around the VAS input operating range
MNCLHI1 X X XHI XHI GNM W=10u L=0.1u
MNCLHI2 XHI XHI VM VM GNM W=10u L=0.1u
RCLHI XHI VM 1Meg
RCLTOP NC XLO 20Meg
RCLBOT XLO VM 80Meg
MNCLLO VP XLO X X GNM W=100u L=0.1u
* Physical soft bound on deep VAS saturation, inactive near normal YP bias
MPVASCL1 YPC YPC VP VP GPM W=100u L=0.1u
MPVASCL2 YP YP YPC YPC GPM W=100u L=0.1u
RVASCL VP YPC 1Meg
.ends FIRSTAMP
