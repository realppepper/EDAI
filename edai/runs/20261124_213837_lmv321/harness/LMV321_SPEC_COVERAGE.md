# Specification coverage — LMV321

- Verification target rows (all): **64**
- Electrical (testable) rows: **48**
- Mapped to a deterministic fixture: **38**
- Actually measured: **34** → coverage **89.5 %**
- PDG Causal Gate Status: **PDG_GATE_PASSED**
- Pass among measured rows: **55.9 %** (19/34)
- Pass among unique parameter kinds: **60.0 %** (6/10)
- Sim errors 0 | not observed 0 | no fixture 0 | unsupported kind 5 | not testable 21

| Symbol | Name | Conditions | Limits (canonical) | Measured | Result |
|---|---|---|---|---|---|
| null | 1IN+ | LMV321 | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCC | Supply voltage | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VID | Differential input voltage | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VI | Input voltage range (either input) | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| Duration of output short circuit (one amplifier) to ground | Duration of output short circuit (one  | At or below TA = 25°C, VCC ≤ 5.5 V | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| TJ | Operating virtual junction temperature | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| Tstg | Storage temperature range | over operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| V(ESD) HBM | Electrostatic discharge | Human body model (HBM), per ANSI/E | - / - / - | - | NOT_TESTABLE_ESD |
| V(ESD) CDM | Electrostatic discharge | Charged device model (CDM), per JE | - / - / - | - | NOT_TESTABLE_ESD |
| VCC | Supply voltage (single-supply operatio | single-supply operation | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating free-air temperature | Operating free-air temperature (LM | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| R9JA Junction-to-ambient thermal resistance | R9JA Junction-to-ambient thermal resis | LMV321, DBV (SOT-23) 5 PINS, DCK ( | - / - / - | - | NOT_TESTABLE_THERMAL |
| R9JA Junction-to-ambient thermal resistance | R9JA Junction-to-ambient thermal resis | LMV324, D (SOIC) 14 PINS, PW (TSSO | - / - / - | - | NOT_TESTABLE_THERMAL |
| VIO | Input offset voltage | VCC+ = 2.7 V, TA = 25°C | - / 1.7 mV / 7 mV | 36 uV | PASS |
| αVIO | Average temperature coefficient of inp | VCC+ = 2.7 V, TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| IIB | Input bias current | VCC+ = 2.7 V, TA = 25°C | 11 nA / - / 250 nA | 2.535e-18 A | PASS |
| IIO | Input offset current | VCC+ = 2.7 V, TA = 25°C | 5 nA / - / 50 nA | 5.071e-18 A | PASS |
| CMRR | Common-mode rejection ratio | VCC+ = 2.7 V, TA = 25°C, VCM = 0 t | 50 dB / 63 dB / - | 120.6 dB | PASS |
| kSVR | Supply-voltage rejection ratio | VCC+ = 2.7 V, TA = 25°C, VCC = 2.7 | 50 dB / 60 dB / - | 73.85 dB | PASS |
| V▌ICR | Common-mode input voltage range | VCC+ = 2.7 V, TA = 25°C, CMRR ≥ 50 | - / - / - | - | NOT_TESTABLE_CONDITION |
| V▌O | Output swing | VCC+ = 2.7 V, TA = 25°C, RL = 10 k | - / - / - | 26.16 mV | NO_NUMERIC_LIMIT |
| V▌O | Output swing | VCC+ = 2.7 V, TA = 25°C, RL = 10 k | - / - / - | 26.16 mV | NO_NUMERIC_LIMIT |
| ICC | Supply current | VCC+ = 2.7 V, TA = 25°C, LMV321I | 80 uA / - / 170 uA | 1.245 mA | FAIL |
| ICC | Supply current | VCC+ = 2.7 V, TA = 25°C, LMV358I ( | 140 uA / - / 340 uA | 1.245 mA | FAIL |
| ICC | Supply current | VCC+ = 2.7 V, TA = 25°C, LMV324I ( | 260 uA / - / 680 uA | 1.245 mA | FAIL |
| B▁ | Unity-gain bandwidth | VCC+ = 2.7 V, TA = 25°C, CL = 200  | - / 1 MHz / - | 12.77 MHz | FAIL_TYP |
| Φm | Phase margin | VCC+ = 2.7 V, TA = 25°C | - / 60 deg / - | 6.164 deg | FAIL_TYP |
| Gm | Gain margin | VCC+ = 2.7 V, TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| Vn | Equivalent input noise voltage | VCC+ = 2.7 V, TA = 25°C, f = 1 kHz | - / - / - | - | UNSUPPORTED_KIND |
| In | Equivalent input noise current | VCC+ = 2.7 V, TA = 25°C, f = 1 kHz | - / - / - | - | UNSUPPORTED_KIND |
| R⁻BJA | Junction-to-ambient thermal resistance | VCC+ = 2.7 V, TA = 25°C, LMV358, D | - / - / - | - | NOT_TESTABLE_THERMAL |
| R⁻BJA | Junction-to-ambient thermal resistance | VCC+ = 2.7 V, TA = 25°C, LMV358, * | - / - / - | - | NOT_TESTABLE_THERMAL |
| R⁻BJA | Junction-to-ambient thermal resistance | VCC+ = 2.7 V, TA = 25°C, LMV358, D | - / - / - | - | NOT_TESTABLE_THERMAL |
| R⁻BJA | Junction-to-ambient thermal resistance | VCC+ = 2.7 V, TA = 25°C, LMV358, P | - / - / - | - | NOT_TESTABLE_THERMAL |
| VIO | Input offset voltage | VCC+ = 5 V, TA = 25°C | - / 1.7 mV / 7 mV | 36 uV | PASS |
| VIO | Input offset voltage | VCC+ = 5 V, TA = -40°C to +125°C | - / - / 9 mV | 36 uV | PASS |
| αVIO | Average temperature coefficient of inp | VCC+ = 5 V, TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| IIB | Input bias current | VCC+ = 5 V, TA = 25°C | - / 15 nA / 250 nA | 2.535e-18 A | PASS |
| IIB | Input bias current | VCC+ = 5 V, TA = -40°C to +125°C | - / - / 500 nA | 2.535e-18 A | PASS |
| IIO | Input offset current | VCC+ = 5 V, TA = 25°C | - / 5 nA / 50 nA | 5.071e-18 A | PASS |
| IIO | Input offset current | VCC+ = 5 V, TA = -40°C to +125°C | - / - / 150 nA | 5.071e-18 A | PASS |
| CMRR | Common-mode rejection ratio | VCC+ = 5 V, VCM = 0 to 4 V, TA = 2 | 50 dB / 65 dB / - | 120.6 dB | PASS |
| kSVR | Supply-voltage rejection ratio | VCC = 2.7 V to 5 V, VO = 1 V, VCM  | 50 dB / 60 dB / - | 73.85 dB | PASS |
| VICR | Common-mode input voltage range | VCC+ = 5 V, CMRR ≥ 50 dB, TA = 25° | - / - / - | - | NOT_TESTABLE_CONDITION |
| VICR | Common-mode input voltage range | VCC+ = 5 V, CMRR ≥ 50 dB, TA = 25° | - / - / - | - | NOT_TESTABLE_CONDITION |
| VO Output swing | Output swing | VCC+ = 5 V, RL = 2 kΩ to 2.5 V, hi | - / - / - | 388.3 mV | NO_NUMERIC_LIMIT |
| VO Output swing | Output swing | VCC+ = 5 V, TA = 25°C, low level | 120 mV / - / 300 mV | 26.16 mV | FAIL |
| VO Output swing | Output swing | VCC+ = 5 V, TA = -40°C to +125°C,  | - / - / 400 mV | 26.16 mV | PASS |
| VO Output swing | Output swing | VCC+ = 5 V, RL = 10 kΩ to 2.5 V, h | - / - / - | 26.16 mV | NO_NUMERIC_LIMIT |
| VO Output swing | Output swing | VCC+ = 5 V, TA = 25°C, low level | 65 mV / - / 180 mV | 26.16 mV | FAIL |
| VO Output swing | Output swing | VCC+ = 5 V, TA = -40°C to +125°C,  | - / - / 280 mV | 26.16 mV | PASS |
| AVD | Large-signal differential voltage gain | VCC+ = 5 V, RL = 2 kΩ, TA = 25°C | 83.52 dB / 100 dB / - | 100.4 dB | PASS |
| AVD | Large-signal differential voltage gain | VCC+ = 5 V, RL = 2 kΩ, TA = -40°C  | 80 dB / - / - | 100.4 dB | PASS |
| IOS | Output short-circuit current | VCC+ = 5 V, Sourcing, VO = 0 V, TA | - / 5 mA / 40 mA | 5.071e-18 A | PASS |
| IOS | Output short-circuit current | VCC+ = 5 V, Sinking, VO = 5 V, TA  | - / 10 mA / 40 mA | 5.071e-18 A | PASS |
| ICC | Supply current | VCC+ = 5 V, LMV321I, TA = 25°C | - / 130 uA / 250 uA | 1.245 mA | FAIL |
| ICC | Supply current | VCC+ = 5 V, LMV321I, TA = -40°C to | - / - / 350 uA | 1.245 mA | FAIL |
| ICC | Supply current | VCC+ = 5 V, LMV358I (both amplifie | - / 210 uA / 440 uA | 1.245 mA | FAIL |
| ICC | Supply current | VCC+ = 5 V, LMV358I (both amplifie | - / - / 615 uA | 1.245 mA | FAIL |
| ICC | Supply current | VCC+ = 5 V, LMV324I (all four ampl | - / 410 uA / 830 uA | 1.245 mA | FAIL |
| ICC | Supply current | VCC+ = 5 V, LMV324I (all four ampl | - / - / 1.16 mA | 1.245 mA | FAIL |
| B1 | Unity-gain bandwidth | VCC+ = 5 V, CL = 200 pF, TA = 25°C | - / 1 MHz / - | 12.77 MHz | FAIL_TYP |
| Φm | Phase margin | VCC+ = 5 V, TA = 25°C | - / 60 deg / - | 6.164 deg | FAIL_TYP |
| Gm | Gain margin |  | - / - / - | - | NOT_TESTABLE_CONDITION |