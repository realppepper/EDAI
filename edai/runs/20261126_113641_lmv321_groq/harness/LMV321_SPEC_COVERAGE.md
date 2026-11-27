# Specification coverage — LMV321

- Verification target rows (all): **27**
- Electrical (testable) rows: **11**
- Mapped to a deterministic fixture: **9**
- Actually measured: **7** → coverage **77.8 %**
- PDG Causal Gate Status: **PDG_GATE_PASSED**
- Pass among measured rows: **85.7 %** (6/7)
- Pass among unique parameter kinds: **83.3 %** (5/6)
- Sim errors 1 | not observed 0 | no fixture 0 | unsupported kind 1 | not testable 17

| Symbol | Name | Conditions | Limits (canonical) | Measured | Result |
|---|---|---|---|---|---|
| VCC | Supply voltage | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VID | Differential input voltage | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VI | Input voltage range (either input) | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| TJ | Operating virtual junction temperature | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| Tstg | Storage temperature range | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| V(ESD) | Electrostatic discharge | Human body model (HBM), per ANSI/E | - / - / - | - | NOT_TESTABLE_ESD |
| V(ESD) | Electrostatic discharge | Charged device model (CDM), per JE | - / - / - | - | NOT_TESTABLE_ESD |
| VCC | Supply voltage (single-supply operatio | Recommended Operating Conditions | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating free-air temperature | I temperature (LMV321, LMV358, LMV | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating free-air temperature | Q temperature | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| R9JA | Junction-to-ambient thermal resistance | LMV321, DBV (SOT-23), 5 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| R9JA | Junction-to-ambient thermal resistance | LMV321, DCK (SC-70), 5 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RBJA | Junction-to-ambient thermal resistance | LMV358, D (SOIC), 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RBJA | Junction-to-ambient thermal resistance | LMV358, DGK (VSSOP), 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RBJA | Junction-to-ambient thermal resistance | LMV358, DDU (VSSOP), 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RBJA | Junction-to-ambient thermal resistance | LMV358, PW (TSSOP), 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| VIO | Input offset voltage | VCC+ = 2.7 V, TA = 25°C | - / 1.7 mV / 7 mV | 2.084 mV | PASS |
| αVIO | Average temperature coefficient of inp | VCC+ = 2.7 V, TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| IIB | Input bias current | VCC+ = 2.7 V, TA = 25°C | - / 11 nA / 250 nA | 1.71e-19 A | PASS |
| IIO | Input offset current | VCC+ = 2.7 V, TA = 25°C | - / 5 nA / 50 nA | 3.464e-19 A | PASS |
| CMRR | Common-mode rejection ratio | VCC+ = 2.7 V, TA = 25°C, VCM = 0 t | 50 dB / 63 dB / - | - | SIM_ERROR |
| kSVR | Supply-voltage rejection ratio | VCC+ = 2.7 V, TA = 25°C, VCC = 2.7 | 50 dB / 60 dB / - | 66.31 dB | PASS |
| VICR | Common-mode input voltage range | VCC+ = 2.7 V, TA = 25°C, CMRR ≥ 50 | - / - / - | - | NOT_TESTABLE_CONDITION |
| VO | Output swing | VCC+ = 2.7 V, TA = 25°C, RL = 10 k | - / - / - | 63.31 mV | NO_NUMERIC_LIMIT |
| VO | Output swing | VCC+ = 2.7 V, TA = 25°C, RL = 10 k | - / 60 mV / 180 mV | 63.31 mV | PASS |
| ICC | Supply current | VCC+ = 2.7 V, TA = 25°C, LMV321I | - / 80 uA / 170 uA | 304.2 uA | FAIL |
| VIO | Input offset voltage | VCC+ = 5 V, TA = 25°C | - / 1.7 mV / 7 mV | 2.084 mV | PASS |