"""Analytical calibration fixtures, not an op-amp design or datasheet pass test."""
import math

def reference_benches():
    return [dict(name='divider',netlist="""Divider calibration: expected 2.5 V and 250 uA
Vsup supply 0 5
Rtop supply out 10k
Rbot out 0 10k
.temp 25
.op
.tran 1u 1m
.meas tran output_v FIND V(out) AT=1m
.meas tran supply_a FIND (-I(Vsup)) AT=1m
.end
""",expected={'output_v':(2.5,1e-6),'supply_a':(250e-6,1e-9)}),
    dict(name='rc_ac',netlist="""RC calibration: tau=1ms, fc=159.154943Hz
Vin inp 0 PULSE(0 1 0 1n 1n 10m 20m) AC 1
R1 inp out 1k
C1 out 0 1u
.temp 25
.options meascplxfmt=cartesian
.ac dec 100 1 100k
.meas ac corner_gain FIND mag(V(out)) AT=159.154943091895
.meas ac corner_phase FIND ph(V(out)) AT=159.154943091895
.end
""",expected={'corner_gain':(1/math.sqrt(2),0.001),'corner_phase':(-45,0.05)}),
    dict(name='rc_tran',netlist="""RC transient calibration: tau=1ms
Vin inp 0 PULSE(0 1 0 1n 1n 10m 20m)
R1 inp out 1k
C1 out 0 1u
.temp 25
.tran 1u 5m 0 1u
.meas tran step_tau FIND V(out) AT=1m
.end
""",expected={'step_tau':(1-math.exp(-1),0.001)}),
    dict(name='mos' ,netlist="""General NMOS LEVEL=1 calibration; NOT process-qualified
Vsup supply 0 5
Vgate gate 0 1.5
Rload supply drain 10k
M1 drain gate 0 0 NREF W=10u L=1u
.model NREF NMOS (LEVEL=1 VTO=1 KP=100u LAMBDA=0)
.temp 25
.options tnom=25
.op
.tran 1u 1m
.meas tran drain_v FIND V(drain) AT=1m
.meas tran supply_a FIND (-I(Vsup)) AT=1m
.end
""",expected={'drain_v':(3.75,0.002),'supply_a':(125e-6,0.2e-6)})]
