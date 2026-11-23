# Specification coverage — TLV271

- Verification target rows (all): **109**
- Electrical (testable) rows: **90**
- Mapped to a deterministic fixture: **27**
- Actually measured: **27** → coverage **100.0 %**
- PDG Causal Gate Status: **PDG_GATE_PASSED**
- Pass among measured rows: **70.4 %** (19/27)
- Pass among unique parameter kinds: **44.4 %** (4/9)
- Sim errors 0 | not observed 0 | no fixture 0 | unsupported kind 62 | not testable 20

| Symbol | Name | Conditions | Limits (canonical) | Measured | Result |
|---|---|---|---|---|---|
| VCC | Supply Voltage Range | Full temperature range | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| Iq/Ch | Supply Current per Channel | 5 V, 25°C | - / 550 uA / - | 803.7 uA | FAIL_TYP |
| Vio | Input Offset Voltage | 5 V, 25°C | - / 500 uV / - | 39 uV | PASS_TYP |
| IIB | Input Bias Current | 5 V, 25°C | - / 1 pA / - | 4.2e-20 A | PASS_TYP |
| GBW | Gain Bandwidth Product | 5 V, 25°C | - / 3 MHz / - | 38.8 MHz | FAIL_TYP |
| SR | Slew Rate | 5 V, 25°C | - / 2.4 V/us / - | 23.44 V/us | FAIL_TYP |
| In | Input Noise Voltage | 5 V, 25°C | - / - / - | - | UNSUPPORTED_KIND |
| SD | Shutdown | N/A | - / - / - | - | NOT_TESTABLE_CONDITION |
| VBHC | VMAX AT PACKAGED DEVICES | TLV271CD, TA = 0°C to 70°C | - / - / - | - | UNSUPPORTED_KIND |
| VBHI | VMAX AT PACKAGED DEVICES | TLV271ID, TA = 0°C to 70°C | - / - / - | - | UNSUPPORTED_KIND |
| VBHC | VMAX AT PACKAGED DEVICES | TLV271CD, TA = -40°C to 125°C | - / - / - | - | UNSUPPORTED_KIND |
| VBHI | VMAX AT PACKAGED DEVICES | TLV271ID, TA = -40°C to 125°C | - / - / - | - | UNSUPPORTED_KIND |
| AVF | VMAX AT PACKAGED DEVICES | TLV272CD, TA = 0°C to 70°C | - / - / - | - | UNSUPPORTED_KIND |
| AVG | VMAX AT PACKAGED DEVICES | TLV272ID, TA = 0°C to 70°C | - / - / - | - | UNSUPPORTED_KIND |
| AVF | VMAX AT PACKAGED DEVICES | TLV272CD, TA = -40°C to 125°C | - / - / - | - | UNSUPPORTED_KIND |
| AVG | VMAX AT PACKAGED DEVICES | TLV272ID, TA = -40°C to 125°C | - / - / - | - | UNSUPPORTED_KIND |
| VMAX AT PACKAGED DEVICES | VMAX AT PACKAGED DEVICES | TLV274CD, TA = 0°C to 70°C | - / - / - | - | UNSUPPORTED_KIND |
| VMAX AT PACKAGED DEVICES | VMAX AT PACKAGED DEVICES | TLV274ID, TA = -40°C to 125°C | - / - / - | - | UNSUPPORTED_KIND |
| 2.7 | Supply voltage V (Single supply) | Single supply | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| 16 | Supply voltage V (Single supply) | Single supply | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| 2.7 | Supply voltage VDD | Single supply | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| 16.5 | Supply voltage VDD | Absolute maximum ratings | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| 16.5 | Supply voltage VDD | Absolute maximum ratings | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| 1 | Differential input voltage VID | Absolute maximum ratings | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| -16.5 | Differential input voltage VID | Absolute maximum ratings | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| -0.2 | Input voltage range VI | Absolute maximum ratings | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VDD + 0.2 | Input voltage range VI upper limit | Absolute maximum ratings | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| Common-mode input voltage range VICR | Common-mode input voltage range VICR | Recommended operating conditions | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| VDD-1.35 | Common-mode input voltage range VICR u | Recommended operating conditions | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| Operating free-air temperature TA | Operating free-air temperature TA | C-suffix | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| 70 | Operating free-air temperature TA | C-suffix | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| -40 | Operating free-air temperature TA | I-suffix | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| 125 | Operating free-air temperature TA | I-suffix | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| 150 | Maximum junction temperature TJ | Absolute maximum ratings | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| -65 | Storage temperature range Tstg | Absolute maximum ratings | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| 260 | Lead temperature 1,6 mm | Absolute maximum ratings | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VIO | Input offset voltage | VIC = VDD/2, RL = 10 kΩ, VO = VDD/ | 500 uV / 5 mV / - | 27 uV | PASS |
| VIO | Input offset voltage | Full range, VDD = 2.7 V, 5 V, and  | 7 mV / - / - | 27 uV | PASS |
| αVIO | Offset voltage drift | RL = 10 kΩ, RS = 50 Ω, VDD = 2.7 V | - / - / - | - | UNSUPPORTED_KIND |
| αVIO | Offset voltage drift | VIC = 0 to VDD−1.35V, VDD = 2.7 V, | - / - / - | - | UNSUPPORTED_KIND |
| αVIO | Offset voltage drift | VIC = 0 to VDD−1.35V, RS = 50 Ω, V | - / - / - | - | UNSUPPORTED_KIND |
| CMRR | Common mode rejection ratio | VIC = 0 to VDD−1.35V, VDD = 5 V, 2 | 65 dB / 80 dB / - | 100.1 dB | PASS |
| CMRR | Common-mode rejection ratio | VIC = 0 to VDD−1.35V, RS = 50 Ω, V | 62 dB / - / - | 100.1 dB | PASS |
| CMRR | Common-mode rejection ratio | VIC = −5 to VDD−1.35V, VDD = ±5 V, | 69 dB / 85 dB / - | 90.09 dB | PASS |
| CMRR | Common-mode rejection ratio | VIC = −5 to VDD−1.35V, RS = 50 Ω,  | 66 dB / - / - | 90.09 dB | PASS |
| AVD | Large-signal differential voltage ampl | VO(PP) = VDD/2, VDD = 5 V, 25°C | 97 dB / 106 dB / - | 87.98 dB | FAIL |
| AVD | Large-signal differential voltage ampl | VO(PP) = VDD/2, RL = 10 kΩ, VDD =  | 86 dB / - / - | 87.98 dB | PASS |
| AVD | Large-signal differential voltage ampl | VO(PP) = VDD/2, VDD = ±5 V, 25°C | 100 dB / 115 dB / - | 57.12 dB | FAIL |
| AVD | Large-signal differential voltage ampl | VO(PP) = VDD/2, VDD = ±5 V, Full r | 90 dB / - / - | 57.12 dB | FAIL |
| IIO | Input offset current | VDD = 5 V, VIC = VDD/2, 25°C | 1 pA / 60 pA / - | 8.402e-20 A | PASS |
| IIO | Input offset current | VDD = 5 V, VIC = VDD/2, 70°C | 100 pA / - / - | 8.402e-20 A | PASS |
| IIO | Input offset current | VDD = 5 V, VIC = VDD/2, 125°C | 1 nA / - / - | 8.402e-20 A | PASS |
| IIB | Input bias current | VDD = 5 V, VIC = VDD/2, VO = VDD/2 | 1 pA / 60 pA / - | 4.2e-20 A | PASS |
| IIB | Input bias current | VDD = 5 V, VIC = VDD/2, VO = VDD/2 | 100 pA / - / - | 4.2e-20 A | PASS |
| IIB | Input bias current | VDD = 5 V, VIC = VDD/2, VO = VDD/2 | 1 nA / - / - | 4.2e-20 A | PASS |
| rid | Differential input resistance | 25°C | - / - / - | - | UNSUPPORTED_KIND |
| CIC | Common-mode input capacitance | f = 21 kHz, 25°C | - / - / - | - | UNSUPPORTED_KIND |
| 2.55 | Positive rail output voltage | 25°C | - / - / - | - | UNSUPPORTED_KIND |
| 2.58 | Positive rail output voltage | Full range | - / - / - | - | UNSUPPORTED_KIND |
| Positive rail output voltage | Positive rail output voltage | Full range | - / - / - | - | UNSUPPORTED_KIND |
| 4.9 | Positive rail output voltage | 25°C | - / - / - | - | UNSUPPORTED_KIND |
| 4.93 | Positive rail output voltage | 25°C | - / - / - | - | UNSUPPORTED_KIND |
| Positive rail output voltage | Positive rail output voltage | Full range | - / - / - | - | UNSUPPORTED_KIND |
| 4.92 | Positive rail output voltage | 25°C | - / - / - | - | UNSUPPORTED_KIND |
| 4.96 | Positive rail output voltage | 25°C | - / - / - | - | UNSUPPORTED_KIND |
| Positive rail output voltage | Positive rail output voltage | Full range | - / - / - | - | UNSUPPORTED_KIND |
| 1.9 | High-level output voltage | 25°C | - / - / - | - | UNSUPPORTED_KIND |
| 2.1 | High-level output voltage | Full range | - / - / - | - | UNSUPPORTED_KIND |
| High-level output voltage | High-level output voltage | Full range | - / - / - | - | UNSUPPORTED_KIND |
| 4.6 | High-level output voltage | 25°C | - / - / - | - | UNSUPPORTED_KIND |
| 4.68 | High-level output voltage | 25°C | - / - / - | - | UNSUPPORTED_KIND |
| High-level output voltage | High-level output voltage | Full range | - / - / - | - | UNSUPPORTED_KIND |
| 4.7 | High-level output voltage | 25°C | - / - / - | - | UNSUPPORTED_KIND |
| 4.84 | High-level output voltage | 25°C | - / - / - | - | UNSUPPORTED_KIND |
| High-level output voltage | High-level output voltage | Full range | - / - / - | - | UNSUPPORTED_KIND |
| 0.1 | Low-level output voltage | 25°C | - / - / - | - | UNSUPPORTED_KIND |
| 0.15 | Low-level output voltage | Full range | - / - / - | - | UNSUPPORTED_KIND |
| Low-level output voltage | Low-level output voltage | Full range | - / - / - | - | UNSUPPORTED_KIND |
| 0.05 | Low-level output voltage | 25°C | - / - / - | - | UNSUPPORTED_KIND |
| 0.1 | Low-level output voltage | Full range | - / - / - | - | UNSUPPORTED_KIND |
| Low-level output voltage | Low-level output voltage | Full range | - / - / - | - | UNSUPPORTED_KIND |
| 0.5 | Low-level output voltage | 25°C | - / - / - | - | UNSUPPORTED_KIND |
| 0.7 | Low-level output voltage | Full range | - / - / - | - | UNSUPPORTED_KIND |
| Low-level output voltage | Low-level output voltage | Full range | - / - / - | - | UNSUPPORTED_KIND |
| 0.28 | Low-level output voltage | 25°C | - / - / - | - | UNSUPPORTED_KIND |
| 0.4 | Low-level output voltage | Full range | - / - / - | - | UNSUPPORTED_KIND |
| Low-level output voltage | Low-level output voltage | Full range | - / - / - | - | UNSUPPORTED_KIND |
| -4.95 | Low-level output voltage | 25°C | - / - / - | - | UNSUPPORTED_KIND |
| -4.92 | Low-level output voltage | 25°C | - / - / - | - | UNSUPPORTED_KIND |
| Low-level output voltage | Low-level output voltage | Full range | - / - / - | - | UNSUPPORTED_KIND |
| 4 | Output voltage from rail | 25°C | - / - / - | - | UNSUPPORTED_KIND |
| 5 | Output current | VO = 0.5 V from rail, VDD = 2.7 V | 5 mA / - / - | 473.6 uA | FAIL |
| 7 | Output current | VO = 0.5 V from rail, VDD = 5 V | 7 mA / - / - | 655.6 uA | FAIL |
| 10 | Output current | VO = 0.5 V from rail, VDD = 10 V | 10 mA / - / - | 27.51 mA | PASS |
| 13 | Output current | VO = 0.5 V from rail, VDD = 10 V | 13 mA / - / - | 27.51 mA | PASS |
| 2500 | Input offset voltage | VDD = 5 V, VO = 2.5 V, VOUT = 0 V  | - / 2.5 V / - | 39 uV | PASS_TYP |
| 2500 | Input offset voltage | VDD = 5 V, VO = 2.5 V, VOUT = 0 V  | - / - / 2.5 V | 39 uV | PASS |
| 200 | Input offset voltage drift | VDD = 5 V, VO = 2.5 V, VOUT = 0 V  | - / - / - | - | UNSUPPORTED_KIND |
| 200 | Input offset voltage drift | VDD = 5 V, VO = 2.5 V, VOUT = 0 V  | - / - / - | - | UNSUPPORTED_KIND |
| 200 | Input offset voltage drift | VDD = 2.7 V, VO = VDD/2, Full rang | - / - / - | - | UNSUPPORTED_KIND |
| 200 | Input offset voltage drift | VDD = 5 V, VO = VDD/2, Full range | - / - / - | - | UNSUPPORTED_KIND |
| 200 | Input offset voltage drift | VDD = 10 V, VO = VDD/2, Full range | - / - / - | - | UNSUPPORTED_KIND |
| 200 | Input offset voltage drift | VDD = ±5 V, VO = 0 V, Full range | - / - / - | - | UNSUPPORTED_KIND |
| 200 | Input offset voltage drift | VDD = ±5 V, VO = 0 V, TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| 200 | Input offset voltage drift | VDD = ±5 V, VO = 0 V, Full range | - / - / - | - | UNSUPPORTED_KIND |
| 200 | Input offset voltage drift | VDD = ±5 V, VO = 0 V, TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| 200 | Input offset voltage drift | VDD = 2.7 V, VO = VDD/2, Full rang | - / - / - | - | UNSUPPORTED_KIND |
| 200 | Input offset voltage drift | VDD = 5 V, VO = VDD/2, Full range | - / - / - | - | UNSUPPORTED_KIND |
| 200 | Input offset voltage drift |  | - / - / - | - | UNSUPPORTED_KIND |