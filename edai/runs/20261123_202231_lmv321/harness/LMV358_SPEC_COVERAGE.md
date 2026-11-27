# Specification coverage — LMV358

- Verification target rows (all): **63**
- Electrical (testable) rows: **44**
- Mapped to a deterministic fixture: **36**
- Actually measured: **33** → coverage **91.7 %**
- PDG Causal Gate Status: **PDG_GATE_PASSED**
- Pass among measured rows: **66.7 %** (22/33)
- Pass among unique parameter kinds: **50.0 %** (5/10)
- Sim errors 0 | not observed 0 | no fixture 0 | unsupported kind 5 | not testable 22

| Symbol | Name | Conditions | Limits (canonical) | Measured | Result |
|---|---|---|---|---|---|
| VCC | Supply voltage | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VID | Differential input voltage | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VI | Input voltage range (either input) | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| Duration of output short circuit (one amplifier) to ground | Duration of output short circuit (one  | At or below TA = 25°C, VCC ≤ 5.5 V | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| TJ | Operating virtual junction temperature | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| Tstg | Storage temperature range | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| V(ESD) | Electrostatic discharge | Human body model (HBM), per ANSI/E | - / - / - | - | NOT_TESTABLE_ESD |
| V(ESD) | Electrostatic discharge | Charged device model (CDM), per JE | - / - / - | - | NOT_TESTABLE_ESD |
| VCC | Supply voltage (single-supply operatio | single-supply operation | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating free-air temperature | I temperature (LMV321, LMV358, LMV | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating free-air temperature | Q temperature | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| R9JA Junction-to-ambient thermal resistance | R9JA Junction-to-ambient thermal resis | LMV321, DBV (SOT-23) 5 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| R9JA Junction-to-ambient thermal resistance | R9JA Junction-to-ambient thermal resis | LMV321, DCK (SC-70) 5 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| R9JA Junction-to-ambient thermal resistance | R9JA Junction-to-ambient thermal resis | LMV324, D (SOIC) 14 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| R9JA Junction-to-ambient thermal resistance | R9JA Junction-to-ambient thermal resis | LMV324, PW (TSSOP) 14 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJA | Junction-to-ambient thermal resistance | LMV358, D (SOIC), 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJA | Junction-to-ambient thermal resistance | LMV358, **DGK** **(VSSOP)**, 8 PIN | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJA | Junction-to-ambient thermal resistance | LMV358, DDU (VSSOP), 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJA | Junction-to-ambient thermal resistance | LMV358, PW (TSSOP), 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| VIO | Input offset voltage | VCC+ = 2.7 V, TA = 25°C | 1.7 mV / 7 mV / 7 mV | 5.124 mV | PASS |
| aVIO | Average temperature coefficient of inp | VCC+ = 2.7 V, TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| IIB | Input bias current | VCC+ = 2.7 V, TA = 25°C | 11 nA / 250 nA / 250 nA | 5.575e-20 A | PASS |
| IIO | Input offset current | VCC+ = 2.7 V, TA = 25°C | 5 nA / 50 nA / 50 nA | 1.115e-19 A | PASS |
| CMRR | Common-mode rejection ratio | VCC+ = 2.7 V, TA = 25°C, VCM = 0 t | 50 dB / 63 dB / 63 dB | 70.53 dB | FAIL |
| kSVR | Supply-voltage rejection ratio | VCC+ = 2.7 V, TA = 25°C, VCC = 2.7 | 50 dB / 60 dB / 60 dB | 48.98 dB | FAIL |
| VICR | Common-mode input voltage range | VCC+ = 2.7 V, TA = 25°C, CMRR ≥ 50 | - / - / - | - | NOT_TESTABLE_CONDITION |
| VO | Output swing | VCC+ = 2.7 V, TA = 25°C, RL = 10 k | - / - / - | 48.48 mV | NO_NUMERIC_LIMIT |
| VO | Output swing | VCC+ = 2.7 V, TA = 25°C, RL = 10 k | 60 mV / - / 180 mV | 48.48 mV | FAIL |
| ICC | Supply current | VCC+ = 2.7 V, TA = 25°C, LMV321I | 80 uA / 170 uA / 170 uA | 451.8 uA | FAIL |
| ICC | Supply current | VCC+ = 2.7 V, TA = 25°C, LMV358I ( | 140 uA / 340 uA / 340 uA | 451.8 uA | FAIL |
| ICC | Supply current | VCC+ = 2.7 V, TA = 25°C, LMV324I ( | 260 uA / 680 uA / 680 uA | 451.8 uA | PASS |
| B1 | Unity-gain bandwidth | VCC+ = 2.7 V, TA = 25°C, CL = 200  | 1 MHz / - / - | 2.32 MHz | PASS |
| Φm | Phase margin | VCC+ = 2.7 V, TA = 25°C | - / 60 deg / - | 62.09 deg | PASS_TYP |
| Gm | Gain margin | VCC+ = 2.7 V, TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| Vn | Equivalent input noise voltage | VCC+ = 2.7 V, TA = 25°C, f = 1 kHz | - / - / - | - | UNSUPPORTED_KIND |
| In | Equivalent input noise current | VCC+ = 2.7 V, TA = 25°C, f = 1 kHz | - / - / - | - | UNSUPPORTED_KIND |
| VIO | Input offset voltage | VCC+ = 5 V, TA = 25°C | - / 1.7 mV / 7 mV | 5.124 mV | PASS |
| VIO | Input offset voltage | VCC+ = 5 V, TA = -40°C to +125°C | - / - / 9 mV | 5.124 mV | PASS |
| αVIO | Average temperature coefficient of inp | VCC+ = 5 V, TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| IIB | Input bias current | VCC+ = 5 V, TA = 25°C | - / 15 nA / 250 nA | 5.575e-20 A | PASS |
| IIB | Input bias current | VCC+ = 5 V, TA = -40°C to +125°C | - / - / 500 nA | 5.575e-20 A | PASS |
| IIO | Input offset current | VCC+ = 5 V, TA = 25°C | - / 5 nA / 50 nA | 1.115e-19 A | PASS |
| IIO | Input offset current | VCC+ = 5 V, TA = -40°C to +125°C | - / - / 150 nA | 1.115e-19 A | PASS |
| CMRR | Common-mode rejection ratio | VCC+ = 5 V, VCM = 0 to 4 V, TA = 2 | 50 dB / 65 dB / - | 70.53 dB | PASS |
| kSVR | Supply-voltage rejection ratio | VCC+ = 5 V, VCC = 2.7 V to 5 V, VO | 50 dB / 60 dB / - | 48.98 dB | FAIL |
| VICR | Common-mode input voltage range | VCC+ = 5 V, CMRR ≥ 50 dB, TA = 25° | - / - / - | - | NOT_TESTABLE_CONDITION |
| VICR | Common-mode input voltage range | VCC+ = 5 V, CMRR ≥ 50 dB, TA = 25° | - / - / - | - | NOT_TESTABLE_CONDITION |
| VO Output swing | Output swing | VCC+ = 5 V, RL = 2 kΩ to 2.5 V, hi | - / - / - | 646.9 mV | NO_NUMERIC_LIMIT |
| VO Output swing | Output swing | VCC+ = 5 V, TA = 25°C, low level | - / 120 mV / 300 mV | 48.48 mV | PASS |
| VO Output swing | Output swing | VCC+ = 5 V, TA = -40°C to +125°C,  | - / - / 400 mV | 48.48 mV | PASS |
| VO Output swing | Output swing | VCC+ = 5 V, RL = 10 kΩ to 2.5 V, h | - / - / - | 48.48 mV | NO_NUMERIC_LIMIT |
| VO Output swing | Output swing | VCC+ = 5 V, TA = 25°C, low level | - / 65 mV / 180 mV | 48.48 mV | PASS |
| VO Output swing | Output swing | VCC+ = 5 V, TA = -40°C to +125°C,  | - / - / 280 mV | 48.48 mV | PASS |
| AVD | Large-signal differential voltage gain | VCC+ = 5 V, RL = 2 kΩ, TA = 25°C | 83.52 dB / 100 dB / - | 20.31 dB | FAIL |
| AVD | Large-signal differential voltage gain | VCC+ = 5 V, RL = 2 kΩ, TA = -40°C  | 80 dB / - / - | 20.31 dB | FAIL |
| IOS | Output short-circuit current | VCC+ = 5 V, Sourcing, VO = 0 V, TA | - / 5 mA / 40 mA | 1.115e-19 A | PASS |
| IOS | Output short-circuit current | VCC+ = 5 V, Sinking, VO = 5 V, TA  | - / 10 mA / 40 mA | 1.115e-19 A | PASS |
| ICC | Supply current | VCC+ = 5 V, LMV321I, TA = 25°C | - / 130 uA / 250 uA | 451.8 uA | FAIL |
| ICC | Supply current | VCC+ = 5 V, LMV321I, TA = -40°C to | - / - / 350 uA | 451.8 uA | FAIL |
| ICC | Supply current | VCC+ = 5 V, LMV358I (both amplifie | - / 210 uA / 440 uA | 451.8 uA | FAIL |
| ICC | Supply current | VCC+ = 5 V, LMV358I (both amplifie | - / - / 615 uA | 451.8 uA | PASS |
| ICC | Supply current | VCC+ = 5 V, LMV324I (all four ampl | - / 410 uA / 830 uA | 451.8 uA | PASS |
| ICC | Supply current | VCC+ = 5 V, LMV324I (all four ampl | - / - / 1.16 mA | 451.8 uA | PASS |