# Deterministic testbench calibration against vendor models

## lm393 — class `comparator`

rows 38 | planned 16 | measured 16 (coverage 100.0 %) | PASS 14 / FAIL 0 | PASS_TYP 1 / FAIL_TYP 1 | sim errors 0 | not observed 0 | no fixture 0

| symbol | name | conditions | limits (canonical) | measured | result |
|---|---|---|---|---|---|
| VIO | Input offset voltage | VCC = 5V to 30V, VIC = VICR min, VO = 1. | None / 0.002 / 0.005 V | 0.0004053 | PASS |
| VIO | Input offset voltage | VCC = 5V to 30V, VIC = VICR min, VO = 1. | None / None / 0.009000000000000001 V | 0.0004053 | PASS |
| IIO | Input offset current | VO = 1.4V, 25°C; VCC = 5V, LM393 column  | None / 5e-09 / 5.0000000000000004e-08 A | 7.52e-14 | PASS |
| IIO | Input offset current | VO = 1.4V, Full range; VCC = 5V, LM393 c | None / None / 2.5000000000000004e-07 A | 7.52e-14 | PASS |
| IIB | Input bias current | VO = 1.4V, 25°C; VCC = 5V, LM393 column  | None / -2.5000000000000002e-08 / -2.5000000000000004e-07 A | 2.499e-08 | PASS |
| IIB | Input bias current | VO = 1.4V, Full range; VCC = 5V, LM393 c | None / None / -4.0000000000000003e-07 A | 2.499e-08 | PASS |
| AVD | Large-signal differential-voltage amplif | VCC = 15V, VO = 1.4V to 11.4V, RL ≥ 15kΩ | 93.97940008672037 / 106.02059991327963 / None dB | 95.6 | PASS |
| IOH | High-level output current | VOH = 5V, VID = 1V, 25°C | None / 1.0000000000000002e-10 / 5.0000000000000004e-08 A | 4.984e-12 | PASS |
| IOH | High-level output current | VOH = 30V, VID = 1V, Full range | None / None / 1e-06 A | 4.984e-12 | PASS |
| VOL | Low-level output voltage | IOL = 4mA, VID = –1V, 25°C; VCC = 5V, LM | None / 0.13 / 0.4 V | 0.09609 | PASS |
| VOL | Low-level output voltage | IOL = 4mA, VID = –1V, Full range | None / None / 0.7000000000000001 V | 0.09609 | PASS |
| IOL | Low-level output current | VOL = 1.5V, VID = –1V, 25°C | 0.006 / None / None A | 2.028 | PASS |
| ICC | Supply current | RL = ∞, VCC = 5V, 25°C; VCC = 5V, LM393  | None / 0.00045000000000000004 / 0.001 A | 0.000316 | PASS |
| ICC | Supply current | RL = ∞, VCC = 30V, Full range; VCC = 5V, | None / 0.00055 / 0.0025 A | 0.001396 | PASS |
| tresp | Response time | VCC = 5V, TA = 25°C, RL to 5V through 5. | None / 1.3e-06 / None s | 1.407e-06 | PASS_TYP |
| tresp | Response time | VCC = 5V, TA = 25°C, RL to 5V through 5. | None / 3e-07 / None s | 1.407e-06 | FAIL_TYP |

## ne555 — class `timer`

rows 50 | planned 28 | measured 28 (coverage 100.0 %) | PASS 26 / FAIL 0 | PASS_TYP 2 / FAIL_TYP 0 | sim errors 0 | not observed 0 | no fixture 0

| symbol | name | conditions | limits (canonical) | measured | result |
|---|---|---|---|---|---|
| VTH | THRES voltage level | VCC = 15V; NA555, NE555, SA555 rows | 8.8 / 10.0 / 11.2 V | 10 | PASS |
| VTH | THRES voltage level | VCC = 5V; NA555, NE555, SA555 rows | 2.4 / 3.3 / 4.2 V | 3.335 | PASS |
| ITH | THRES current |  | None / 3.0000000000000004e-08 / 2.5000000000000004e-07 A | 1.03e-08 | PASS |
| VTRIG | TRIG voltage level | VCC = 15V; NA555, NE555, SA555 rows | 4.5 / 5.0 / 5.6 V | 4.995 | PASS |
| VTRIG | TRIG voltage level | VCC = 5V; NA555, NE555, SA555 rows | 1.1 / 1.67 / 2.2 V | 1.664 | PASS |
| ITRIG | TRIG current | TRIG at 0V; NA555, NE555, SA555 rows | None / 5e-07 / 2e-06 A | 0 | PASS |
| VRESET | RESET voltage level | TA = 25°C (all devices) | 0.3 / 0.7 / 1.0 V | 0.6975 | PASS |
| IRESET | RESET current | RESET at VCC | None / 0.0001 / 0.0004 A | 8.933e-05 | PASS |
| IRESET | RESET current | RESET at 0V; NA555, NE555, SA555 rows | None / -0.0004 / -0.0015 A | 0.0004 | PASS |
| IDISCH(off) | DISCH switch off-state current |  | None / 2e-08 / 1.0000000000000001e-07 A | 2.002e-08 | PASS |
| VDISCH(on) | DISCH switch on-state voltage | VCC = 5V, IO = 8mA; NA555, NE555, SA555  | None / 0.15 / 0.4 V | 0.048 | PASS |
| VCONT | CONT voltage (open circuit) | VCC = 15V; NA555, NE555, SA555 rows | 9.0 / 10.0 / 11.0 V | 10 | PASS |
| VCONT | CONT voltage (open circuit) | VCC = 5V; NA555, NE555, SA555 rows | 2.6 / 3.3 / 4.0 V | 3.333 | PASS |
| VOL | Low-level output voltage | VCC = 15V, IOL = 10mA; NA555, NE555, SA5 | None / 0.1 / 0.25 V | 0.1191 | PASS |
| VOL | Low-level output voltage | VCC = 15V, IOL = 50mA; NA555, NE555, SA5 | None / 0.4 / 0.75 V | 0.577 | PASS |
| VOL | Low-level output voltage | VCC = 15V, IOL = 100mA; NA555, NE555, SA | None / 2.0 / 2.5 V | 1.111 | PASS |
| VOL | Low-level output voltage | VCC = 15V, IOL = 200mA (all devices) | None / 2.5 / None V | 2.069 | PASS_TYP |
| VOL | Low-level output voltage | VCC = 5V, IOL = 5mA; NA555, NE555, SA555 | None / 0.1 / 0.35 V | 0.05932 | PASS |
| VOL | Low-level output voltage | VCC = 5V, IOL = 8mA; NA555, NE555, SA555 | None / 0.15 / 0.4 V | 0.09422 | PASS |
| VOH | High-level output voltage | VCC = 15V, IOH = –100mA; NA555, NE555, S | 12.75 / 13.3 / None V | 13.89 | PASS |
| VOH | High-level output voltage | VCC = 15V, IOH = –200mA (all devices) | None / 12.5 / None V | 12.93 | PASS_TYP |
| VOH | High-level output voltage | VCC = 5V, IOH = –100mA; NA555, NE555, SA | 2.75 / 3.3 / None V | 4.032 | PASS |
| ICC | Supply current | Output low, no load, VCC = 15V; NA555, N | None / 0.01 / 0.015 A | 0.004854 | PASS |
| ICC | Supply current | Output low, no load, VCC = 5V; NA555, NE | None / 0.003 / 0.006 A | 0.001611 | PASS |
| ICC | Supply current | Output high, no load, VCC = 15V; NA555,  | None / 0.009000000000000001 / 0.013000000000000001 A | 0.004854 | PASS |
| ICC | Supply current | Output high, no load, VCC = 5V; NA555, N | None / 0.002 / 0.005 A | 0.001611 | PASS |
| tr | Output-pulse rise time | CL = 15pF, TA = 25°C, 20% to 80%; NA555, | None / 1.0000000000000001e-07 / 3.0000000000000004e-07 s | 8.8e-09 | PASS |
| tf | Output-pulse fall time | CL = 15pF, TA = 25°C, 80% to 20%; NA555, | None / 1.0000000000000001e-07 / 3.0000000000000004e-07 s | 9.384e-09 | PASS |

## lm358_vs_lm741 — class `opamp`

rows 62 | planned 31 | measured 31 (coverage 100.0 %) | PASS 13 / FAIL 14 | PASS_TYP 3 / FAIL_TYP 1 | sim errors 0 | not observed 0 | no fixture 0

| symbol | name | conditions | limits (canonical) | measured | result |
|---|---|---|---|---|---|
| VOS | Input offset voltage | LM358B, TA = 25°C (±) | None / 0.0003 / 0.003 V | 0.001 | PASS |
| VOS | Input offset voltage | LM358B, TA = –40°C to +85°C (±) | None / None / 0.004 V | 0.001 | PASS |
| VOS | Input offset voltage | LM358BA, TA = 25°C (±) | None / None / 0.002 V | 0.001 | PASS |
| VOS | Input offset voltage | LM358BA, TA = –40°C to +85°C (±) | None / None / 0.0025 V | 0.001 | PASS |
| PSRR | Power supply rejection ratio | (typ ±) | 96.47817481888637 / 113.97940008672037 / None dB | 96 | FAIL |
| CMRR | Common-mode rejection ratio | (V–) ≤ VCM ≤ (V+) – 1.5 V, VS = 3 V to 3 | 80.0 / 93.97940008672037 / None dB | 90 | PASS |
| CMRR | Common-mode rejection ratio | (V–) ≤ VCM ≤ (V+) – 2.0 V, VS = 5 V to 3 | 70.00625834763193 / 92.04119982655925 / None dB | 90 | PASS |
| IB | Input bias current | TA = 25°C | None / -1e-08 / -3.5e-08 A | 8e-08 | FAIL |
| IB | Input bias current | TA = –40°C to +85°C | None / None / -5.0000000000000004e-08 A | 8e-08 | FAIL |
| IOS | Input offset current | TA = 25°C | None / 5e-10 / 4e-09 A | 2e-08 | FAIL |
| IOS | Input offset current | TA = –40°C to +85°C | None / None / 5e-09 A | 2e-08 | FAIL |
| en | Input voltage noise density | f = 1 kHz | None / 40.0 / None nV/rtHz | 0.02142 | FAIL_TYP |
| AOL | Open-loop voltage gain | VS = 15 V; VO = 1 V to 11 V; RL ≥ 10 kΩ, | 96.90196080028514 / 102.92256071356476 / None dB | 107.4 | PASS |
| AOL | Open-loop voltage gain | TA = –40°C to +85°C | 90.88136088700551 / None / None dB | 107.4 | PASS |
| GBW | Gain bandwidth product |  | None / 1200000.0 / None Hz | 1.01e+06 | PASS_TYP |
| SR | Slew rate | G = + 1 | None / 0.5 / None V/us | 0.5149 | PASS_TYP |
| Θm | Phase margin | G = + 1, RL = 10kΩ, CL = 20 pF | None / 56.0 / None deg | 64.27 | PASS_TYP |
| VO | Voltage output swing from rail (positive | Positive rail (V+), IOUT = 50 µA | None / 1.35 / 1.42 V | 1.503 | FAIL |
| VO | Voltage output swing from rail (positive | Positive rail (V+), IOUT = 1 mA | None / 1.4 / 1.48 V | 1.559 | FAIL |
| VO | Voltage output swing from rail (positive | Positive rail (V+), IOUT = 5 mA | None / 1.5 / 1.61 V | 1.786 | FAIL |
| VO | Voltage output swing from rail (negative | Negative rail (V–), IOUT = 50 µA | None / 0.1 / 0.15 V | 1.503 | FAIL |
| VO | Voltage output swing from rail (negative | Negative rail (V–), IOUT = 1 mA | None / 0.75 / 1.0 V | 1.559 | FAIL |
| VO | Voltage output swing from rail (negative | VS = 5 V, RL ≤ 10 kΩ connected to (V–),  | None / 0.005 / 0.02 V | 1.507 | FAIL |
| IO | Output current (source) | VS = 15 V; VO = V–; VID = 1 V | -0.02 / -0.03 / None A | 0.02 | PASS |
| IO | Output current (source) | VS = 15 V; VO = V–; VID = 1 V, TA = –40° | -0.01 / None / None A | 0.02 | PASS |
| IO | Output current (sink) | VS = 15 V; VO = V+; VID = –1 V | 0.01 / 0.02 / None A | 0.02 | PASS |
| IO | Output current (sink) | VS = 15 V; VO = V+; VID = –1 V, TA = –40 | 0.005 / None / None A | 0.02 | PASS |
| IO | Output current (sink) | VID = –1 V; VO = (V–) + 200 mV | 5.9999999999999995e-05 / 9.999999999999999e-05 / None A | 0.01733 | PASS |
| ISC | Short-circuit current | VS = 20 V, (V+) = 10 V, (V–) = –10 V, VO | None / 0.04 / 0.06 A | 0.1133 | FAIL |
| IQ | Quiescent current per amplifier | VS = 5 V; IO = 0 A; TA = –40°C to +85°C | None / 0.0003 / 0.00045999999999999996 A | 0.0017 | FAIL |
| IQ | Quiescent current per amplifier | VS = 36 V; IO = 0 A | None / None / 0.0007999999999999999 A | 0.0017 | FAIL |
