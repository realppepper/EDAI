"""Explicit five-terminal op-amp fixtures. Calibration defaults are NOT DUT specs."""
from pathlib import Path
import math

REFERENCE_MODEL='''* Linear one-pole calibration model; NOT a physical IC or rail-limited model.
* P N VP VM OUT. Supply current is an artificial fixed calibration observable.
.subckt CALAMP P N VP VM OUT
Ggain 0 X P N 1m
Ioffset 0 X 0.5u
Rpole X 0 100Meg
Cpole X 0 {cap}
Bbuffer BUF 0 V=(V(VP)+V(VM))/2+V(X)
Rout BUF OUT 100
Ibias VP VM 200u
.ends CALAMP
'''.format(cap=1/(2*math.pi*1e8*10))


def generate_fixtures(model_path,subcircuit='CALAMP'):
    """Require explicit pin order P,N,VP,VM,OUT; never guess pin mapping.

    Current fixture binds one amplifier, 5 V, 25 C, RL=1 Mohm to midrail,
    CL=20 pF to midrail. No untested source range or two-channel inference.
    """
    model_path=Path(model_path).resolve()
    if not model_path.is_file():raise FileNotFoundError(model_path)
    if not subcircuit.isidentifier():raise ValueError('Invalid subcircuit name')
    common=f'''* Calibration fixture, single channel; NOT the full LM358B test plan
.include "{model_path}"
.temp 25
.options plotwinsize=0 meascplxfmt=cartesian
VDD vp 0 5
VMID mid 0 2.5
RL out mid 1Meg
CL out mid 20p
'''
    dut=f'XDUT inp inn vp 0 out {subcircuit}\n'
    return [
        {'name':'opamp_op','analysis':'op','deck':common+'VIN inp 0 2.5\nVFB out inn 0\n'+dut+'.op\n.end\n','names':[]},
        {'name':'opamp_dc','analysis':'dc','deck':common+'VIN inp 0 2.5\nVFB out inn 0\n'+dut+'''.dc VIN 2 3 0.01
.meas dc output_mid FIND V(out) AT=2.5
.meas dc tracking_error MAX abs(V(out)-V(inp))
.end
''','names':['output_mid','tracking_error']},
        {'name':'opamp_ac','analysis':'ac','deck':common+'''VIN inp mid DC 0 AC 1
* DC servo only: feedback closed at DC, effectively broken over this AC sweep.
Lservo out inn 1e15
Cservo inn mid 1
'''+dut+'''.ac dec 200 0.01 100Meg
.meas ac gain_low FIND mag(V(out)) AT=0.01
.meas ac unity_hz WHEN mag(V(out))=1 FALL=1
.meas ac unity_phase FIND ph(V(out)) WHEN mag(V(out))=1 FALL=1
.end
''','names':['gain_low','unity_hz','unity_phase']},
        *[{'name':'opamp_tran_'+direction,'analysis':'tran','direction':direction,
           'step':{'initial_V':initial,'final_V':final,'start_s':5e-6,'transition_s':10e-9,
                   'stop_s':20e-6,'max_step_s':2e-9,'error_fraction':0.001},
           'deck':common+f'VIN inp 0 PWL(0 {initial} 5u {initial} 5.01u {final} 20u {final})\nVFB out inn 0\n'+dut+
                  '.tran 0 20u 0 2n\n.end\n','names':[]}
          for direction,initial,final in [('rising',1,3),('falling',3,1)]]]


def reference_transfer():
    """Independent algebra of Rpole/Cpole + loaded Rout; not simulator readback."""
    gain=1e5/(1+100/1e6)
    tau1=1/(2*math.pi*10);tau2=100*20e-12/(1+100/1e6)
    b=1/tau1**2+1/tau2**2
    d=(gain**2-1)/(tau1*tau2)**2
    w=math.sqrt(2*d/(math.sqrt(b*b+4*d)+b))
    phase=-math.degrees(math.atan(w*tau1)+math.atan(w*tau2))
    return {'gain':gain,'unity_hz':w/(2*math.pi),'phase_deg':phase,'tau1':tau1,'tau2':tau2}
