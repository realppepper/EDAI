# Specification coverage — LMV358

- Verification target rows (all): **58**
- Electrical (testable) rows: **43**
- Mapped to a deterministic fixture: **35**
- Actually measured: **28** → coverage **80.0 %**
- PDG Causal Gate Status: **PDG_GATE_PASSED**
- Pass among measured rows: **71.4 %** (20/28)
- Pass among unique parameter kinds: **70.0 %** (7/10)
- Sim errors 0 | not observed 0 | no fixture 0 | unsupported kind 5 | not testable 18

| Symbol | Name | Conditions | Limits (canonical) | Measured | Result |
|---|---|---|---|---|---|
| VCC | Supply voltage | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VID | Differential input voltage | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VI | Input voltage range (either input) | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| Duration of output short circuit (one amplifier) to ground | Duration of output short circuit (one  | At or below TA = 25°C, VCC ≤ 5.5 V | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| TJ | Operating virtual junction temperature | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| Tstg | Storage temperature range | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| V<sub>(ESD) | Electrostatic discharge | Human body model (HBM), per ANSI/E | - / - / - | - | NOT_TESTABLE_ESD |
| V<sub>(ESD) | Electrostatic discharge | Charged device model (CDM), per JE | - / - / - | - | NOT_TESTABLE_ESD |
| VCC | Supply voltage (single-supply operatio | Recommended Operating Conditions | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating free-air temperature | LMV321, LMV358, LMV324, LMV321IDCK | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating free-air temperature | Q temperature | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| R9JA Junction-to-ambient thermal resistance | R9JA Junction-to-ambient thermal resis | LMV321, DBV (SOT-23) 5 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| R9JA Junction-to-ambient thermal resistance | R9JA Junction-to-ambient thermal resis | LMV321, DCK (SC-70) 5 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| R9JA Junction-to-ambient thermal resistance | R9JA Junction-to-ambient thermal resis | LMV324, D (SOIC) 14 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| R9JA Junction-to-ambient thermal resistance | R9JA Junction-to-ambient thermal resis | LMV324, PW (TSSOP) 14 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| Input offset voltage | Input offset voltage | VCC+ = 2.7 V, TA = 25°C | - / 1.7 mV / 7 mV | 36 uV | PASS |
| Average temperature coefficient of input offset voltage | Average temperature coefficient of inp | VCC+ = 2.7 V, TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| Input bias current | Input bias current | VCC+ = 2.7 V, TA = 25°C | - / 11 nA / 250 nA | 3.196e-18 A | PASS |
| Input offset current | Input offset current | VCC+ = 2.7 V, TA = 25°C | - / 5 nA / 50 nA | 6.391e-18 A | PASS |
| Common-mode rejection ratio | Common-mode rejection ratio | VCM = 0 to 1.7 V, VCC+ = 2.7 V, TA | 50 dB / 63 dB / - | 120.6 dB | PASS |
| Supply-voltage rejection ratio | Supply-voltage rejection ratio | VCC = 2.7 V to 5 V, VO = 1 V, TA = | - / - / - | - | UNSUPPORTED_KIND |
| Common-mode input voltage range | Common-mode input voltage range | CMRR ≥ 50 dB, VCC+ = 2.7 V, TA = 2 | - / - / - | - | NOT_TESTABLE_CONDITION |
| Output swing High level | Output swing High level | RL = 10 kΩ to 1.35 V, VCC+ = 2.7 V | - / - / - | 26.16 mV | NO_NUMERIC_LIMIT |
| Output swing Low level | Output swing Low level | RL = 10 kΩ to 1.35 V, VCC+ = 2.7 V | 60 mV / 180 mV / - | 26.16 mV | FAIL |
| Supply current (LMV321I) | Supply current (LMV321I) | VCC+ = 2.7 V, TA = 25°C | - / 80 uA / 170 uA | 1.245 mA | FAIL |
| Supply current (LMV358I both amplifiers) | Supply current (LMV358I both amplifier | VCC+ = 2.7 V, TA = 25°C | - / 140 uA / 340 uA | 1.245 mA | FAIL |
| Supply current (LMV324I all four amplifiers) | Supply current (LMV324I all four ampli | VCC+ = 2.7 V, TA = 25°C | - / 260 uA / 680 uA | 1.245 mA | FAIL |
| Unity-gain bandwidth | Unity-gain bandwidth | CL = 200 pF, VCC+ = 2.7 V, TA = 25 | 1 MHz / - / - | 12.77 MHz | PASS |
| Phase margin | Phase margin | CL = 200 pF, VCC+ = 2.7 V, TA = 25 | 60 deg / - / - | 1.93 deg | FAIL |
| Gain margin | Gain margin | CL = 200 pF, VCC+ = 2.7 V, TA = 25 | - / - / - | - | UNSUPPORTED_KIND |
| Equivalent input noise voltage | Equivalent input noise voltage | f = 1 kHz, VCC+ = 2.7 V, TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| Equivalent input noise current | Equivalent input noise current | f = 1 kHz, VCC+ = 2.7 V, TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| VIO | Input offset voltage | VCC+ = 5 V, TA = 25°C | - / 1.7 mV / 7 mV | 36 uV | PASS |
| VIO | Input offset voltage | VCC+ = 5 V, TA = -40°C to +125°C | - / - / 9 mV | 36 uV | PASS |
| VIO | Input offset voltage | VCC+ = 5 V, TA = 25°C | - / - / - | 36 uV | NO_NUMERIC_LIMIT |
| IIB | Input bias current | VCC+ = 5 V, TA = 25°C | - / 15 nA / 250 nA | 3.196e-18 A | PASS |
| IIB | Input bias current | VCC+ = 5 V, TA = -40°C to +125°C | - / - / 500 nA | 3.196e-18 A | PASS |
| IIO | Input offset current | VCC+ = 5 V, TA = 25°C | - / 5 nA / 50 nA | 6.391e-18 A | PASS |
| IIO | Input offset current | VCC+ = 5 V, TA = -40°C to +125°C | - / - / 150 nA | 6.391e-18 A | PASS |
| CMRR | Common-mode rejection ratio | VCC+ = 5 V, VCM = 0 to 4 V, TA = 2 | 50 dB / 65 dB / - | 120.6 dB | PASS |
| kSVR | Supply-voltage rejection ratio | VCC = 2.7 V to 5 V, VO = 1 V, VCM  | 50 dB / 60 dB / - | 73.85 dB | PASS |
| VICR | Common-mode input voltage range | VCC+ = 5 V, CMRR ≥ 50 dB, TA = 25° | - / - / - | - | NOT_TESTABLE_CONDITION |
| VICR | Common-mode input voltage range | VCC+ = 5 V, CMRR ≥ 50 dB, TA = 25° | - / - / - | - | NOT_TESTABLE_CONDITION |
| VO Output swing | Output swing | RL = 2 kΙ to 2.5 V, high level, TA | - / - / - | 388.3 mV | NO_NUMERIC_LIMIT |
| VO Output swing | Output swing | RL = 2 kΙ to 2.5 V, high level, TA | - / - / - | 388.3 mV | NO_NUMERIC_LIMIT |
| VO Output swing | Output swing | RL = 2 kΙ to 2.5 V, low level, TA  | 120 mV / 300 mV / - | 388.3 mV | PASS |
| VO Output swing | Output swing | RL = 2 kΙ to 2.5 V, low level, TA  | - / - / 400 mV | 388.3 mV | PASS |
| VO Output swing | Output swing | RL = 10 kΙ to 2.5 V, high level, T | - / - / - | 26.16 mV | NO_NUMERIC_LIMIT |
| VO Output swing | Output swing | RL = 10 kΙ to 2.5 V, high level, T | - / - / - | 26.16 mV | NO_NUMERIC_LIMIT |
| VO Output swing | Output swing | RL = 10 kΙ to 2.5 V, low level, TA | 65 mV / 180 mV / - | 26.16 mV | FAIL |
| VO Output swing | Output swing | RL = 10 kΙ to 2.5 V, low level, TA | - / - / 280 mV | 26.16 mV | PASS |
| AVD | Large-signal differential voltage gain | VCC+ = 5 V, RL = 2 kΙ, TA = 25°C | 83.52 dB / 100 dB / - | 100.4 dB | PASS |
| AVD | Large-signal differential voltage gain | VCC+ = 5 V, RL = 2 kΙ, TA = -40°C  | 80 dB / - / - | 100.4 dB | PASS |
| IOS | Output short-circuit current | VCC+ = 5 V, Sourcing, VO = 0 V, TA | - / 5 mA / 40 mA | 6.391e-18 A | PASS |
| IOS | Output short-circuit current | VCC+ = 5 V, Sinking, VO = 5 V, TA  | - / 10 mA / 40 mA | 6.391e-18 A | PASS |
| ICC | Supply current | VCC+ = 5 V, LMV321I, TA = 25°C | - / 130 uA / 250 uA | 1.245 mA | FAIL |
| ICC | Supply current | VCC+ = 5 V, LMV321I, TA = -40°C to | - / - / 350 uA | 1.245 mA | FAIL |
| ICC | None |  | - / - / - | 1.245 mA | NO_NUMERIC_LIMIT |