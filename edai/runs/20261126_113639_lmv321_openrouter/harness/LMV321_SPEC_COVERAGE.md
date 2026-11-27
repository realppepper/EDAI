# Specification coverage — LMV321

- Verification target rows (all): **76**
- Electrical (testable) rows: **53**
- Mapped to a deterministic fixture: **43**
- Actually measured: **38** → coverage **88.4 %**
- PDG Causal Gate Status: **PDG_GATE_PASSED**
- Pass among measured rows: **71.1 %** (27/38)
- Pass among unique parameter kinds: **70.0 %** (7/10)
- Sim errors 0 | not observed 0 | no fixture 0 | unsupported kind 7 | not testable 26

| Symbol | Name | Conditions | Limits (canonical) | Measured | Result |
|---|---|---|---|---|---|
| VCC | Supply voltage | LMV321, LMV358, LMV324, LMV324S | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating temperature | LMV321, LMV358, LMV324, LMV324S | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| IQ | Supply current | LMV321 | - / 130 uA / - | 525.6 uA | FAIL_TYP |
| IQ | Supply current | LMV358 | - / 210 uA / - | 525.6 uA | FAIL_TYP |
| IQ | Supply current | LMV324 | - / 410 uA / - | 525.6 uA | PASS_TYP |
| HBM | Human-body model ESD | JESD 22 | - / - / - | - | NOT_TESTABLE_ESD |
| CDM | Charged-device model ESD | JESD 22 | - / - / - | - | NOT_TESTABLE_ESD |
| VCC | Supply voltage | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VID | Differential input voltage | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VI | Input voltage range (either input) | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| Duration of output short circuit (one amplifier) to ground | Duration of output short circuit (one  | At or below TA = 25°C, VCC ≤ 5.5 V | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| TJ | Operating virtual junction temperature | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| Tstg | Storage temperature range | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| V(ESD) | Electrostatic discharge | Human body model (HBM), per ANSI/E | - / - / - | - | NOT_TESTABLE_ESD |
| V(ESD) | Electrostatic discharge | Charged device model (CDM), per JE | - / - / - | - | NOT_TESTABLE_ESD |
| VCC | Supply voltage (single-supply operatio |  | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating free-air temperature | I temperature (LMV321, LMV358, LMV | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating free-air temperature | Q temperature | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| RθJA | Junction-to-ambient thermal resistance | LMV321, DBV (SOT-23), 5 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJA | Junction-to-ambient thermal resistance | LMV321, DCK (SC-70), 5 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJA | Junction-to-ambient thermal resistance | LMV324, D (SOIC), 14 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJA | Junction-to-ambient thermal resistance | LMV324, PW (TSSOP), 14 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJA | Junction-to-ambient thermal resistance | LMV358, D (SOIC), 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJA | Junction-to-ambient thermal resistance | LMV358, DGK (VSSOP), 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJA | Junction-to-ambient thermal resistance | LMV358, DDU (VSSOP), 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJA | Junction-to-ambient thermal resistance | LMV358, PW (TSSOP), 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| VIO | Input offset voltage | VCC+ = 2.7 V, TA = 25°C | - / 1.7 mV / 7 mV | 21 uV | PASS |
| αVIO | Average temperature coefficient of inp | VCC+ = 2.7 V, TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| IIB | Input bias current | VCC+ = 2.7 V, TA = 25°C | - / 11 nA / 250 nA | 4.94e-19 A | PASS |
| IIO | Input offset current | VCC+ = 2.7 V, TA = 25°C | - / 5 nA / 50 nA | 9.882e-19 A | PASS |
| CMRR | Common-mode rejection ratio | VCC+ = 2.7 V, TA = 25°C, VCM = 0 t | 50 dB / 63 dB / - | 103.8 dB | PASS |
| kSVR | Supply-voltage rejection ratio | VCC+ = 2.7 V, TA = 25°C, VCC = 2.7 | 50 dB / 60 dB / - | 116 dB | PASS |
| VICR | Common-mode input voltage range | VCC+ = 2.7 V, TA = 25°C, CMRR ≥ 50 | - / - / - | - | NOT_TESTABLE_CONDITION |
| VO | Output swing | VCC+ = 2.7 V, TA = 25°C, RL = 10 k | - / - / - | 74.27 mV | NO_NUMERIC_LIMIT |
| VO | Output swing | VCC+ = 2.7 V, TA = 25°C, RL = 10 k | - / 60 mV / 180 mV | 74.27 mV | PASS |
| ICC | Supply current | VCC+ = 2.7 V, TA = 25°C, LMV321I | - / 80 uA / 170 uA | 525.6 uA | FAIL |
| ICC | Supply current | VCC+ = 2.7 V, TA = 25°C, LMV358I ( | - / 140 uA / 340 uA | 525.6 uA | FAIL |
| ICC | Supply current | VCC+ = 2.7 V, TA = 25°C, LMV324I ( | - / 260 uA / 680 uA | 525.6 uA | PASS |
| B1 | Unity-gain bandwidth | VCC+ = 2.7 V, TA = 25°C, CL = 200  | - / 1 MHz / - | 6.917 MHz | FAIL_TYP |
| Φm | Phase margin | VCC+ = 2.7 V, TA = 25°C | - / 60 deg / - | 55.76 deg | PASS_TYP |
| Gm | Gain margin | VCC+ = 2.7 V, TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| Vn | Equivalent input noise voltage | VCC+ = 2.7 V, TA = 25°C, f = 1 kHz | - / - / - | - | UNSUPPORTED_KIND |
| In | Equivalent input noise current | VCC+ = 2.7 V, TA = 25°C, f = 1 kHz | - / - / - | - | UNSUPPORTED_KIND |
| VIO | Input offset voltage | TA = 25°C | - / 1.7 mV / 7 mV | 21 uV | PASS |
| VIO | Input offset voltage | TA = -40°C to +125°C | - / - / 9 mV | 21 uV | PASS |
| αVIO | Average temperature coefficient of inp | TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| IIB | Input bias current | TA = 25°C | - / 15 nA / 250 nA | 4.94e-19 A | PASS |
| IIB | Input bias current | TA = -40°C to +125°C | - / - / 500 nA | 4.94e-19 A | PASS |
| IIO | Input offset current | TA = 25°C | - / 5 nA / 50 nA | 9.882e-19 A | PASS |
| IIO | Input offset current | TA = -40°C to +125°C | - / - / 150 nA | 9.882e-19 A | PASS |
| CMRR | Common-mode rejection ratio | VCM = 0 to 4 V, TA = 25°C | 50 dB / 65 dB / - | 103.8 dB | PASS |
| kSVR | Supply-voltage rejection ratio | VCC = 2.7 V to 5 V, VO = 1 V, VCM  | 50 dB / 60 dB / - | 116 dB | PASS |
| VICR | Common-mode input voltage range | CMRR ≥ 50 dB, TA = 25°C | - / - / - | - | NOT_TESTABLE_CONDITION |
| VICR | Common-mode input voltage range | CMRR ≥ 50 dB, TA = 25°C | - / - / - | - | NOT_TESTABLE_CONDITION |
| VO | Output swing | RL = 2 kΩ to 2.5 V, high level, TA | - / - / - | 1.63 V | NO_NUMERIC_LIMIT |
| VO | Output swing | RL = 2 kΩ to 2.5 V, high level, TA | - / - / - | 1.63 V | NO_NUMERIC_LIMIT |
| VO | Output swing | TA = 25°C, low level | - / 120 mV / 300 mV | 74.27 mV | PASS |
| VO | Output swing | TA = -40°C to +125°C, low level | - / - / 400 mV | 74.27 mV | PASS |
| VO | Output swing | RL = 10 kΩ to 2.5 V, high level, T | - / - / - | 74.27 mV | NO_NUMERIC_LIMIT |
| VO | Output swing | RL = 10 kΩ to 2.5 V, high level, T | - / - / - | 74.27 mV | NO_NUMERIC_LIMIT |
| VO | Output swing | TA = 25°C, low level | - / 65 mV / 180 mV | 74.27 mV | PASS |
| VO | Output swing | TA = -40°C to +125°C, low level | - / - / 280 mV | 74.27 mV | PASS |
| AVD | Large-signal differential voltage gain | RL = 2 kΩ, TA = 25°C | 83.52 dB / 100 dB / - | 73.48 dB | FAIL |
| AVD | Large-signal differential voltage gain | RL = 2 kΩ, TA = -40°C to +125°C | 80 dB / - / - | 73.48 dB | FAIL |
| IOS | Output short-circuit current | Sourcing, VO = 0 V, TA = 25°C | - / 5 mA / 40 mA | 9.882e-19 A | PASS |
| IOS | Output short-circuit current | Sinking, VO = 5 V, TA = 25°C | - / 10 mA / 40 mA | 9.882e-19 A | PASS |
| ICC | Supply current | LMV321I, TA = 25°C | - / 130 uA / 250 uA | 525.6 uA | FAIL |
| ICC | Supply current | LMV321I, TA = -40°C to +125°C | - / - / 350 uA | 525.6 uA | FAIL |
| ICC | Supply current | LMV358I (both amplifiers), TA = 25 | - / 210 uA / 440 uA | 525.6 uA | FAIL |
| ICC | Supply current | LMV358I (both amplifiers), TA = -4 | - / - / 615 uA | 525.6 uA | PASS |
| ICC | Supply current | LMV324I (all four amplifiers), TA  | - / 410 uA / 830 uA | 525.6 uA | PASS |
| ICC | Supply current | LMV324I (all four amplifiers), TA  | - / - / 1.16 mA | 525.6 uA | PASS |
| B1 | Unity-gain bandwidth | CL = 200 pF, TA = 25°C | - / 1 MHz / - | 6.917 MHz | FAIL_TYP |
| Φm | Phase margin | TA = 25°C | - / 60 deg / - | 55.76 deg | PASS_TYP |
| Gm | Gain margin | TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| Vn | Equivalent input noise voltage |  | - / - / - | - | UNSUPPORTED_KIND |