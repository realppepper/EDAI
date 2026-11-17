* Fixed generic MOS assumptions; NOT TI models or a fabrication PDK.
* Parameters are frozen before sizing experiments. Noise/mismatch not qualified.
.model GNM NMOS (LEVEL=1 VTO=0.65 KP=100u LAMBDA=0.02 GAMMA=0.4 PHI=0.7 TOX=20n CGSO=0.2n CGDO=0.2n)
.model GPM PMOS (LEVEL=1 VTO=-0.7 KP=40u LAMBDA=0.025 GAMMA=0.4 PHI=0.7 TOX=20n CGSO=0.2n CGDO=0.2n)
* Fresh physical design. Performance and startup are unverified.
.subckt FIRSTAMP P N VP VM OUT
* Active-started cascoded beta multiplier; BIAS is observable.
MRN1 BIAS BIAS VM VM GNM W=20u L=10u
MRN2 RND BIAS RS RS GNM W=80u L=10u
RRSET RS VM 22360
MRNC PRF NC RND RND GNM W=200u L=10u
MRP1 RPT1 PRF VP VP GPM W=100u L=10u
MRP2 PRF PC RPT1 RPT1 GPM W=100u L=10u
MRP3 RPT2 PRF VP VP GPM W=100u L=10u
MRP4 BIAS PC RPT2 RPT2 GPM W=100u L=10u
* Permanent weak seed removes startup switch overdrive branch.
RSEED VP BIAS 50000000
* Physical feedforward charge starts BIAS during the rising supply.
CBIASBOOT BIAS VP 1e-12
* Physical NC bootstrap and charge reservoir break reference mutual cutoff.
RNCBOOT VP NC 1200000
* Supply-ramp displacement current starts NC; fixed-supply reservoir retained.
CNCRES NC VP 100p
* NMOS and wide-swing PMOS cascode bias generation.
MNCFEED NC PRF VP VP GPM W=100u L=10u
MNC1 NC NC NCLOW NCLOW GNM W=1000u L=10u
MNC2 NCLOW NCLOW VM VM GNM W=1000u L=10u
MPC PC PC VP VP GPM W=20u L=10u
MPCSINK PC BIAS VM VM GNM W=20u L=10u
* Weak PC sink pre-biases the PMOS cascode during low-supply startup.
RPCBOOT PC VM 10000000
* Three diode-connected PMOS drops set AB level-shift reference.
MAB1 AB1 AB1 VP VP GPM W=2200u L=10u
MAB2 AB2 AB2 AB1 AB1 GPM W=2200u L=10u
MAB3 AB3 AB3 AB2 AB2 GPM W=2200u L=10u
MABSINK AB3 BIAS VM VM GNM W=20u L=10u
* PMOS input pair and NMOS folding branches.
MTAIL TS PRF VP VP GPM W=400u L=10u
MINP A P TS TS GPM W=6u L=2u
MINN B N TS TS GPM W=6u L=2u
MSINKA A BIAS VM VM GNM W=80u L=10u
MSINKB B BIAS VM VM GNM W=80u L=10u
MFOLDP Y NC A A GNM W=400u L=10u
MFOLDN LREF NC B B GNM W=400u L=10u
* Symmetric physical excursion clamps on the folding nodes.
MCLA1 A A AX AX GNM W=100u L=2u
MCLA2 AX AX VM VM GNM W=100u L=2u
MCLB1 B B BX BX GNM W=100u L=2u
MCLB2 BX BX VM VM GNM W=100u L=2u
* Upper cascoded mirror: P increasing pulls Y down.
MLTOP1 LP1 LREF VP VP GPM W=200u L=10u
MLCAS1 LREF PC LP1 LP1 GPM W=200u L=10u
MLTOP2 LP2 LREF VP VP GPM W=200u L=10u
MLCAS2 Y PC LP2 LP2 GPM W=200u L=10u
* Buffered level shifter prevents DC loading of high-gain node Y.
MBUF VP Y YT YT GNM W=2000u L=2u
MBUFSINK BSD BIAS VM VM GNM W=100u L=10u
MBUFCAS YT NC BSD BSD GNM W=1000u L=10u
MTRAN Z AB3 YT YT GPM W=2000u L=2u
MZDIO Z Z VM VM GNM W=2000u L=2u
* Complementary common-source output and source-current limit feedback.
RPS VP PS 25
MOUTP OUT Y PS PS GPM W=4000u L=2u
MOUTN OUT Z VM VM GNM W=12000u L=2u
MLIMP Y PS VP VP GPM W=100u L=2u
* Physical lower excursion clamp for Y, inactive near nominal AB bias.
MCL1 YC1 YC1 VP VP GPM W=100u L=2u
MCL2 YC2 YC2 YC1 YC1 GPM W=100u L=2u
MCL3 Y Y YC2 YC2 GPM W=100u L=2u
* Miller compensation around the inverting output stage.
CCOMP Y CZ 4.5p
RZERO CZ OUT 150
.ends FIRSTAMP
