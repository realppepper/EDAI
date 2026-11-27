# Specification coverage — LM6172

- Verification target rows (all): **110**
- Electrical (testable) rows: **91**
- Mapped to a deterministic fixture: **50**
- Actually measured: **46** → coverage **92.0 %**
- PDG Causal Gate Status: **PDG_GATE_PASSED**
- Pass among measured rows: **40.0 %** (24/60)
- Pass among unique parameter kinds: **38.5 %** (5/13)
- Sim errors 0 | not observed 0 | no fixture 0 | unsupported kind 39 | not testable 21

| Symbol | Name | Conditions | Limits (canonical) | Measured | Result |
|---|---|---|---|---|---|
| V_S | Supply voltage (VCC+ − VCC−) | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| V_I | Differential input voltage | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VCM | Common-mode voltage | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| IN | Input current | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| ISC | Output current short to ground | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| T_J | Junction temperature | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| T_stg | Storage temperature | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| T_SOLDER | Infrared or convection reflow (20 seco | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| T_SOLDER | Wave soldering lead temp (10 seconds) | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| V_ESD | Electrostatic discharge | Human body model (HBM), per ANSI/E | - / - / - | - | NOT_TESTABLE_ESD |
| V_ESD | Electrostatic discharge | Machine model | - / - / - | - | NOT_TESTABLE_ESD |
| Vs | Supply voltage | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Ambient temperature | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| R_thetaJA | Junction-to-ambient thermal resistance | LM6172, D (SOIC) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_thetaJC(top) | Junction-to-case (top) thermal resista | LM6172, D (SOIC) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_thetaJB | Junction-to-board thermal resistance | LM6172, D (SOIC) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| Psi_JT | Junction-to-top characterization param | LM6172, D (SOIC) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| Psi_JB | Junction-to-board characterization par | LM6172, D (SOIC) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_thetaJC(bot) | Junction-to-case (bottom) thermal resi | LM6172, P (PDIP) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| VOS | Input offset voltage | at TJ = 25C, VCC+ = 15V, VCC- = -1 | - / 400 uV / 3 mV | 26 uV | PASS |
| VOS | Input offset voltage | at TJ = 25C, VCC+ = 15V, VCC- = -1 | - / 4 mV / - | 26 uV | PASS_TYP |
| TCVOS | Input offset voltage average drift | at TJ = 25C, VCC+ = 15V, VCC- = -1 | - / - / - | - | UNSUPPORTED_KIND |
| IB | Input bias current | at TJ = 25C, VCC+ = 15V, VCC- = -1 | - / 1.2 uA / 3 uA | 3.111e-18 A | PASS |
| IB | Input bias current | at TJ = 25C, VCC+ = 15V, VCC- = -1 | - / 4 uA / - | 3.111e-18 A | PASS_TYP |
| IOS | Input offset current | at TJ = 25C, VCC+ = 15V, VCC- = -1 | - / 20 nA / 2 uA | 6.222e-18 A | PASS |
| IOS | Input offset current | at TJ = 25C, VCC+ = 15V, VCC- = -1 | - / 3 uA / - | 6.222e-18 A | PASS_TYP |
| RIN | Input resistance | Common-mode | - / - / - | - | UNSUPPORTED_KIND |
| RIN | Input resistance | Differential-mode | - / - / - | - | UNSUPPORTED_KIND |
| RO | Open-loop output resistance |  | - / - / - | - | UNSUPPORTED_KIND |
| CMRR | Common-mode rejection ratio | VCM = ±10V | 70 dB / 110 dB / - | 67.03 dB | FAIL |
| CMRR | Common-mode rejection ratio | at TJ = 25C, VCC+ = 15V, VCC- = -1 | 65 dB / - / - | 82.92 dB | PASS |
| PSRR | Power supply rejection ratio | VS = ±15V to ±5V | 75 dB / 95 dB / - | 71.35 dB | FAIL |
| VCM | Input common-mode voltage | CMRR > 60dB | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Input common-mode voltage | RL = 1kOhm, VOUT = ±5V | - / - / - | - | UNSUPPORTED_KIND |
| AV | Large-signal voltage gain | RL = 100Ohm, VOUT = ±5V; TA = -40C | - / - / - | 74.55 dB | NO_NUMERIC_LIMIT |
| AV | Large-signal voltage gain | at TJ = 25C, VCC+ = 15V, VCC- = -1 | - / - / - | 94.01 dB | NO_NUMERIC_LIMIT |
| AV | Large-signal voltage gain |  | - / - / - | 109.9 dB | NO_NUMERIC_LIMIT |
| VO | Output swing | RL = 1kOhm, sourcing; TA = -40C to | 12.5 V / 13.2 V / - | 1.416 V | FAIL |
| VO | Output swing | RL = 1kOhm, sourcing | 12 V / - / - | 1.416 V | FAIL |
| VO | Output swing | RL = 1kOhm, sinking; TA = -40C to  | -13.1 V / - / - | 18.01 mV | PASS |
| VO | Output swing | RL = 1kOhm, sinking | -12 V / - / - | 18.01 mV | PASS |
| VO | Output swing | RL = 100Ohm, sourcing | 6 V / 9 V / - | 2.39 V | FAIL |
| VO | Output swing | RL = 100Ohm, sourcing; TA = -40C t | 5 V / - / - | 2.39 V | FAIL |
| VO | Output swing | RL = 100Ohm, sinking | -8.5 V / - / - | 128.2 mV | PASS |
| VO | Output swing | RL = 100Ohm, sinking; TA = -40C to | -5 V / - / - | 128.2 mV | PASS |
| Continuous output current (open loop) | Sourcing, RL = 100Ohm | Sourcing, RL = 100Ohm; TA = -40C t | - / - / - | - | UNSUPPORTED_KIND |
| Continuous output current (open loop) | Sinking, RL = 100Ohm | Sinking, RL = 100Ohm; TA = -40C to | - / - / - | - | UNSUPPORTED_KIND |
| Continuous output current (open loop) | Sinking, RL = 100Ohm | Sinking, RL = 100Ohm; TA = -40C to | - / - / - | - | UNSUPPORTED_KIND |
| Continuous output current (open loop) | Sinking, RL = 100Ohm | Sinking, RL = 100Ohm | - / - / - | - | UNSUPPORTED_KIND |
| ISC | Output short-circuit current | D package; Sourcing | - / 173 mA / - | 1.101 mA | FAIL_TYP |
| ISC | Output short-circuit current |  | - / - / - | 1.101 mA | NO_NUMERIC_LIMIT |
| ts | Settling time (0.1%) | Tj = 25°C, VCC+ = 15V, VCC− = −15V | - / - / - | - | UNSUPPORTED_KIND |
| AD | Differential gain | Tj = 25°C, VCC+ = 15V, VCC− = −15V | - / - / - | - | UNSUPPORTED_KIND |
| ΦD | Differential phase | Tj = 25°C, VCC+ = 15V, VCC− = −15V | - / - / - | - | UNSUPPORTED_KIND |
| e₋ n | Input-referred voltage noise | Tj = 25°C, VCC+ = 15V, VCC− = −15V | - / - / - | - | UNSUPPORTED_KIND |
| in | Input-referred current noise | Tj = 25°C, VCC+ = 15V, VCC− = −15V | - / - / - | - | UNSUPPORTED_KIND |
| HD2 | Second harmonic distortion | Tj = 25°C, VCC+ = 15V, VCC− = −15V | - / - / - | - | UNSUPPORTED_KIND |
| HD2 | Second harmonic distortion | Tj = 25°C, VCC+ = 15V, VCC− = −15V | - / - / - | - | UNSUPPORTED_KIND |
| HD2 | Second harmonic distortion | Tj = 25°C, VCC+ = 15V, VCC− = −15V | - / - / - | - | UNSUPPORTED_KIND |
| HD3 | Third harmonic distortion | Tj = 25°C, VCC+ = 15V, VCC− = −15V | - / - / - | - | UNSUPPORTED_KIND |
| HD3 | Third harmonic distortion | Tj = 25°C, VCC+ = 15V, VCC− = −15V | - / - / - | - | UNSUPPORTED_KIND |
| HD3 | Third harmonic distortion | Tj = 25°C, VCC+ = 15V, VCC− = −15V | - / - / - | - | UNSUPPORTED_KIND |
| HD3 | Third harmonic distortion | Tj = 25°C, VCC+ = 15V, VCC− = −15V | - / - / - | - | UNSUPPORTED_KIND |
| 0.1 | Input offset voltage | VCC+ = 5V, VCC– = −5V, VCM = 0V, a | - / 100 uV / 3 mV | 26 uV | PASS |
| 4 | Input offset voltage average drift | VCC+ = 5V, VCC– = −5V, VCM = 0V, a | - / - / - | - | UNSUPPORTED_KIND |
| 1.4 | Input bias current | VCC+ = 5V, VCC– = −5V, VCM = 0V, a | - / 1.4 uA / 2.5 uA | 3.111e-18 A | PASS |
| 0.02 | Input offset current | VCC+ = 5V, VCC– = −5V, VCM = 0V, a | - / 20 nA / 1.5 uA | 6.222e-18 A | PASS |
| 40 | Input resistance (Common-mode) | VCC+ = 5V, VCC– = −5V, VCM = 0V, a | - / - / - | - | UNSUPPORTED_KIND |
| 4.9 | Input resistance (Differential-mode) | VCC+ = 5V, VCC– = −5V, VCM = 0V, a | - / - / - | - | UNSUPPORTED_KIND |
| 14 | Open loop output resistance | VCC+ = 5V, VCC– = −5V, VCM = 0V, a | - / - / - | - | UNSUPPORTED_KIND |
| 70 | Common-mode rejection ratio | VCM = ±2.5V | 70 dB / 105 dB / - | 67.03 dB | FAIL |
| 75 | Power supply rejection ratio | VS = ±15V to ±5V | 75 dB / 95 dB / - | 71.35 dB | FAIL |
| Input common-mode voltage | Input common-mode voltage | CMRR > 60dB | - / - / - | - | NOT_TESTABLE_CONDITION |
| 70 | Large-signal voltage gain | RL = 1 kΩ, VOUT = ±1V | 70 dB / 82 dB / - | 94.01 dB | PASS |
| 65 | Large-signal voltage gain | RL = 100Ω, VOUT = ±1V | 65 dB / - / - | 74.55 dB | PASS |
| 65 | Large-signal voltage gain | TA = -40°C to +85°C | 65 dB / - / - | 109.9 dB | PASS |
| 60 | Large-signal voltage gain | TA = -40°C to +85°C | 60 dB / - / - | 109.9 dB | PASS |
| 3.1 | Output swing (sourcing, RL=1kΩ) | RL = 1kΩ, sourcing | 3.1 V / 3.4 V / - | 1.416 V | FAIL |
| -3.3 | Output swing (sinking, RL=1kΩ) | RL = 1kΩ, sinking | -3.3 V / -3.1 V / - | 18.01 mV | PASS |
| 2.5 | Output swing (sourcing, RL=100Ω) | RL = 100Ω, sourcing | 2.5 V / 2.9 V / - | 2.39 V | FAIL |
| 2.4 | Output swing (sourcing, RL=100Ω) | TA = -40°C to +85°C | 2.4 V / - / - | 26.16 mV | FAIL |
| -2.7 | Output swing (sinking, RL=100Ω) | RL = 100Ω, sinking | -2.7 V / -2.4 V / - | 128.2 mV | PASS |
| -2.4 | Output swing (sinking, RL=100Ω) | TA = -40°C to +85°C | -2.4 V / - / - | 26.16 mV | PASS |
| 25 | Continuous output current (open loop,  | Sourcing, RL = 100Ω | 25 mA / 29 mA / - | 1.101 mA | FAIL |
| 24 | Continuous output current (open loop,  | TA = -40°C to +85°C | 24 mA / - / - | 1.101 mA | FAIL |
| -27 | Continuous output current (open loop,  | Sinking, RL = 100Ω | -27 mA / -24 mA / - | 213.2 mA | PASS |
| -23 | Continuous output current (open loop,  | TA = -40°C to +85°C | -23 mA / - / - | 1.101 mA | FAIL |
| 155 | Output short-circuit current (D packag | D package, Sourcing | - / 155 mA / - | 1.101 mA | FAIL_TYP |
| -158 | Output short-circuit current (D packag | D package, Sinking | - / -158 mA / - | 213.2 mA | FAIL_TYP |
| 93 | Output short-circuit current (P packag | P package, Sourcing | - / 93 mA / - | 1.101 mA | FAIL_TYP |
| -72 | Output short-circuit current (P packag | P package, Sinking | - / -72 mA / - | 213.2 mA | FAIL_TYP |
| 4.4 | Supply current | VCC+ = 5V, VCC– = −5V | - / 4.4 mA / 6 mA | 1.245 mA | PASS |
| 750 | Slew rate | Av = +2, VIN = 3.5VPP | 750 V/us / - / - | 20.59 V/us | FAIL |
| 70 | Unity-gain bandwidth |  | 70 MHz / - / - | 22.22 MHz | FAIL |
| 130 | −3dB frequency | AV = +1 | - / - / - | - | UNSUPPORTED_KIND |
| 75 | −3dB frequency | AV = +2, D package | - / - / - | - | UNSUPPORTED_KIND |
| 41 | Phase margin | D Package | 41 deg / - / - | 50.14 deg | PASS |
| 57 | Phase margin | P package | 57 deg / - / - | 50.14 deg | FAIL |
| ts | Settling time (0.1%) | Tj = 25°C, VCC+ = 5V, VCC− = −5V,  | - / - / - | - | UNSUPPORTED_KIND |
| AD | Differential gain | Tj = 25°C, VCC+ = 5V, VCC− = −5V,  | - / - / - | - | UNSUPPORTED_KIND |
| φD | Differential phase | Tj = 25°C, VCC+ = 5V, VCC− = −5V,  | - / - / - | - | UNSUPPORTED_KIND |
| en | Input-referred voltage noise | Tj = 25°C, VCC+ = 5V, VCC− = −5V,  | - / - / - | - | UNSUPPORTED_KIND |
| in | Input-referred current noise | Tj = 25°C, VCC+ = 5V, VCC− = −5V,  | - / - / - | - | UNSUPPORTED_KIND |
| HD2 | Second harmonic distortion | Tj = 25°C, VCC+ = 5V, VCC− = −5V,  | - / - / - | - | UNSUPPORTED_KIND |
| HD2 | Second harmonic distortion | Tj = 25°C, VCC+ = 5V, VCC− = −5V,  | - / - / - | - | UNSUPPORTED_KIND |
| HD2 | Second harmonic distortion | Tj = 25°C, VCC+ = 5V, VCC− = −5V,  | - / - / - | - | UNSUPPORTED_KIND |
| HD3 | Third harmonic distortion | Tj = 25°C, VCC+ = 5V, VCC− = −5V,  | - / - / - | - | UNSUPPORTED_KIND |
| HD3 | Third harmonic distortion | Tj = 25°C, VCC+ = 5V, VCC− = −5V,  | - / - / - | - | UNSUPPORTED_KIND |
| HD3 | Third harmonic distortion | Tj = 25°C, VCC+ = 5V, VCC− = −5V,  | - / - / - | - | UNSUPPORTED_KIND |
| HD3 | Third harmonic distortion | Tj = 25°C, VCC+ = 5V, VCC− = −5V,  | - / - / - | - | UNSUPPORTED_KIND |