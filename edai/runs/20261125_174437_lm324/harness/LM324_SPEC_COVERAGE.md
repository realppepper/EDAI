# Specification coverage — LM324

- Verification target rows (all): **195**
- Electrical (testable) rows: **162**
- Mapped to a deterministic fixture: **114**
- Actually measured: **89** → coverage **78.1 %**
- PDG Causal Gate Status: **PDG_GATE_PASSED**
- Pass among measured rows: **50.5 %** (48/95)
- Pass among unique parameter kinds: **50.0 %** (7/14)
- Sim errors 0 | not observed 0 | no fixture 0 | unsupported kind 37 | not testable 44

| Symbol | Name | Conditions | Limits (canonical) | Measured | Result |
|---|---|---|---|---|---|
| VCC | Supply voltage | LM324B, LM324BA, LM2902B, LM2902BA | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VCC | Supply voltage | LM324B, LM324BA, LM2902B, LM2902BA | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VCC | Supply voltage | LM2902, TA = operating free-air te | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VID | Differential input voltage | LM324xx, LM224xx, LM2902xxx, LM124 | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VID | Differential input voltage | LM324B, LM324BA, LM2902B, LM2902BA | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VID | Differential input voltage | LM2902, TA = operating free-air te | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VI | Input voltage | LM324xx, LM224xx, LM2902xxx, LM124 | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VI | Input voltage | LM324B, LM324BA, LM2902B, LM2902BA | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VI | Input voltage | LM2902, TA = operating free-air te | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| t_short | Duration of output short circuit (one  | TA = 25°C, VCC ≤ 15V, LM324B, LM32 | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| t_short | Duration of output short circuit (one  | TA = 25°C, VCC ≤ 15V, LM2902, TA = | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| t_short | Duration of output short circuit (one  | TA = 25°C, VCC ≤ 15V, LM324xx, LM2 | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| TJ | Operating virtual junction temperature | TA = operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| T_case_60s | Case temperature for 60 seconds | FK package | - / - / - | - | NOT_TESTABLE_THERMAL |
| T_lead_60s | Lead temperature 1.6mm (1/16 inch) fro | J or W package | - / - / - | - | NOT_TESTABLE_THERMAL |
| T_stg | Storage temperature | TA = operating free-air temperatur | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| V_ESD_HBM | Electrostatic discharge (HBM) | LM324B, LM324BA, LM2902B, LM2902BA | - / - / - | - | NOT_TESTABLE_ESD |
| V_ESD_CDM | Electrostatic discharge (CDM) | LM324B, LM324BA, LM2902B, LM2902BA | - / - / - | - | NOT_TESTABLE_ESD |
| V_ESD_HBM | Electrostatic discharge (HBM) | LM124, LM124A, LM224, LM224A, LM32 | - / - / - | - | NOT_TESTABLE_ESD |
| V_ESD_CDM | Electrostatic discharge (CDM) | LM124, LM124A, LM224, LM224A, LM32 | - / - / - | - | NOT_TESTABLE_ESD |
| VCC | Supply voltage | LM324B, LM324BA, LM2902B, LM2902BA | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| VCM | Common-mode voltage | LM324B, LM324BA, LM2902B, LM2902BA | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating free air temperature | LM124x | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating free air temperature | LM2902xxx, LM2902Bx | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating free air temperature | LM324Bx | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating free air temperature | LM224xx | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating free air temperature | LM324xx | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| RβJA | Junction-to-ambient thermal resistance | D (SOIC) to W (CFP) | - / - / - | - | NOT_TESTABLE_THERMAL |
| RβJC(top) | Junction-to-case (top) thermal resista | D (SOIC) to W (CFP) | - / - / - | - | NOT_TESTABLE_THERMAL |
| RβJB | Junction-to-board thermal resistance | D (SOIC) to W (CFP) | - / - / - | - | NOT_TESTABLE_THERMAL |
| ΨJT | Junction-to-top characterization param | D (SOIC) to W (CFP) | - / - / - | - | NOT_TESTABLE_THERMAL |
| ΨJB | Junction-to-board characterization par | D (SOIC) to W (CFP) | - / - / - | - | NOT_TESTABLE_THERMAL |
| RβJC(bot) | Junction-to-case (bottom) thermal resi | D (SOIC) to W (CFP) | - / - / - | - | NOT_TESTABLE_THERMAL |
| VOS | Input offset voltage | Vs = (V+) – (V–) = 5V to 36V (±2.5 | -600 uV / - / 3 mV | 21 uV | PASS |
| VOS | Input offset voltage | Vs = (V+) – (V–) = 5V to 36V (±2.5 | -4 mV / - / - | 21 uV | PASS |
| VOS | Input offset voltage | Vs = (V+) – (V–) = 5V to 36V (±2.5 | -300 uV / - / 2 mV | 21 uV | PASS |
| dVOS/dT | Input offset voltage drift | Vs = (V+) – (V–) = 5V to 36V (±2.5 | - / - / - | - | UNSUPPORTED_KIND |
| PSRR | Input offset voltage versus power supp | Vs = (V+) – (V–) = 5V to 36V (±2.5 | - / - / - | 21 uV | NO_NUMERIC_LIMIT |
| Channel separation | Channel separation | Vs = (V+) – (V–) = 5V to 36V (±2.5 | - / - / - | - | UNSUPPORTED_KIND |
| VCM | Common-mode voltage | Vs = 3V to 36V, V- | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage | Vs = 5V to 36V, TA = -40°C to +85° | - / - / - | - | NOT_TESTABLE_CONDITION |
| CMRR | Common-mode rejection ratio | Vs = 3V to 36V, (V-) ≤ VCM ≤ (V+)  | 70 dB / 80 dB / - | 111.2 dB | PASS |
| CMRR | Common-mode rejection ratio | Vs = 5V to 36V, (V-) ≤ VCM ≤ (V+)  | 65 dB / 80 dB / - | 111.2 dB | PASS |
| IB | Input bias current | Vs = (V+) – (V–) = 5V to 36V (±2.5 | -10 nA / - / -35 nA | 2.585e-19 A | PASS |
| IB | Input bias current | Vs = (V+) – (V–) = 5V to 36V (±2.5 | - / - / -60 nA | 2.585e-19 A | PASS |
| dlOS/dT | Input offset current drift | Vs = (V+) – (V–) = 5V to 36V (±2.5 | - / - / - | - | UNSUPPORTED_KIND |
| IOS | Input offset current | Vs = (V+) – (V–) = 5V to 36V (±2.5 | -500 pA / - / 4 nA | 5.159e-19 A | PASS |
| IOS | Input offset current | Vs = (V+) – (V–) = 5V to 36V (±2.5 | - / - / -5 nA | 5.159e-19 A | PASS |
| EN | Input voltage noise | f = 0.1Hz to 10Hz | - / - / - | - | UNSUPPORTED_KIND |
| eN | Input voltage noise density | RS = 100Ω, VI = 0V, f = 1kHz | 35 nV/rtHz / - / - | 347 nV/rtHz | PASS |
| ZID | Differential |  | - / - / - | - | UNSUPPORTED_KIND |
| ZID | Differential |  | - / - / - | - | NOT_TESTABLE_CONDITION |
| ZICM | Common-mode |  | - / - / - | - | UNSUPPORTED_KIND |
| ZICM | Common-mode |  | - / - / - | - | NOT_TESTABLE_CONDITION |
| AOL | Open-loop voltage gain | Vs = 15V, VO = 1V to 11V, RL ≥ 10k | 93.98 dB / 100 dB / - | 90.29 dB | FAIL |
| AOL | Open-loop voltage gain | Vs = 15V, VO = 1V to 11V, RL ≥ 10k | 87.96 dB / - / - | 90.29 dB | PASS |
| GBW | Gain-bandwidth product | RL = 1MΩ, CL = 20pF | 1.2 MHz / - / - | 16.41 MHz | PASS |
| SR | Slew rate | RL = 1MΩ, CL = 30pF, VI = ±10V | 0.5 V/us / - / - | 13.64 V/us | PASS |
| Θm | Phase margin | G = +1, RL = 10kΩ, CL = 20pF | 56 deg / - / - | 68.56 deg | PASS |
| tS | Settling time | To 0.1%, VS = 5V, 2V step, G = +1, | - / - / - | - | UNSUPPORTED_KIND |
| tS | Settling time | Overload recovery time, VIN × gain | - / - / - | - | UNSUPPORTED_KIND |
| THD+N | Total harmonic distortion + noise | G = +1, f = 1kHz, VO = 3.53VRMS, V | - / - / - | - | UNSUPPORTED_KIND |
| VO | Voltage output swing from rail | LM324B, TA = 25°C, VCM = VOUT = VS | 1.35 V / 1.5 V / 1.5 V | 4.974 mV | FAIL |
| VO | Voltage output swing from rail | LM324B, TA = 25°C, VCM = VOUT = VS | 1.4 V / 1.6 V / 1.6 V | 153.5 mV | FAIL |
| VO | Voltage output swing from rail | LM324B, TA = 25°C, VCM = VOUT = VS | 1.5 V / 1.75 V / 1.75 V | 1.953 V | FAIL |
| VO | Voltage output swing from rail | LM324B, TA = 25°C, VCM = VOUT = VS | 100 mV / 150 mV / 150 mV | 6.939 mV | FAIL |
| VO | Voltage output swing from rail | LM324B, TA = 25°C, VCM = VOUT = VS | 750 mV / 1 V / 1 V | 12.5 mV | FAIL |
| VO | Voltage output swing from rail | LM324B, TA = -40°C to +85°C, Vs =  | 5 mV / 20 mV / 20 mV | 6.642 mV | PASS |
| IO | Output current | LM324B, TA = -40°C to +85°C, Sourc | -20 mA / -30 mA / - | 1.135 mA | FAIL |
| IO | Output current | LM324B, TA = -40°C to +85°C, Sourc | -10 mA / - / - | 1.135 mA | FAIL |
| IO | Output current | LM324B, TA = -40°C to +85°C, Sink, | 10 mA / 20 mA / - | 150.1 mA | PASS |
| IO | Output current | LM324B, TA = -40°C to +85°C, Sink, | 5 mA / - / - | 150.1 mA | PASS |
| IO | Output current | LM324B, Vid = -1V, VO = (V-) + 200 | 50 uA / 85 uA / 85 uA | 1.13 mA | FAIL |
| Isc | Short-circuit current | LM324B, Vs = 20V, (V+) = 10V, (V-) | -40 mA / - / 40 mA | 1.101 mA | PASS |
| C₂LOAD | Capacitive load drive | LM324B | - / - / - | - | UNSUPPORTED_KIND |
| R₂O | Open-loop output impedance | LM324B, f = 1MHz, IO = 0A | - / - / - | - | UNSUPPORTED_KIND |
| IQ | Quiescent current per amplifier | LM324B, Vs = 5V, IQ = 0A, TA = -40 | 240 uA / - / 300 uA | 1.186 mA | FAIL |
| IQ | Quiescent current per amplifier | LM324B, Vs = 36V, IQ = 0A, TA = -4 | 350 uA / - / 750 uA | 1.186 mA | FAIL |
| VOS | Input offset voltage | LM2902B, VS = (V+) – (V–) = 5V to  | -600 uV / 3 mV / - | 21 uV | PASS |
| VOS | Input offset voltage | LM2902BA, TA = -40°C to +125°C, VS | - / 4 mV / - | 21 uV | PASS_TYP |
| VOS | Input offset voltage | LM2902BA, TA = -40°C to +125°C, VS | 300 uV / 2 mV / 2.5 mV | 21 uV | PASS |
| dVOS/dT | Input offset voltage drift | LM2902B/LM2902BA, RS = 0Ω, TA = -4 | - / - / - | - | UNSUPPORTED_KIND |
| PSRR | Input offset voltage versus power supp | LM2902B/LM2902BA, VS = (V+) – (V–) | - / - / - | 21 uV | NO_NUMERIC_LIMIT |
| Channel separation | Channel separation | LM2902B/LM2902BA, f = 1kHz to 20kH | - / - / - | - | UNSUPPORTED_KIND |
| VCM | Common-mode voltage range | LM2902B/LM2902BA, Vs = 3V to 36V,  | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | LM2902B/LM2902BA, Vs = 5V to 36V,  | - / - / - | - | NOT_TESTABLE_CONDITION |
| CMRR | Common-mode rejection ratio | LM2902B/LM2902BA, Vs = 3V to 36V,  | 70 dB / 80 dB / - | 111.2 dB | PASS |
| CMRR | Common-mode rejection ratio | LM2902B/LM2902BA, Vs = 5V to 36V,  | 65 dB / 80 dB / - | 111.2 dB | PASS |
| IB | Input bias current | LM2902B/LM2902BA, VS = (V+) – (V–) | -10 nA / -35 nA / - | 2.585e-19 A | PASS |
| IB | Input bias current | LM2902B/LM2902BA, TA = -40°C to +1 | - / - / -60 nA | 2.585e-19 A | PASS |
| dIB/dT | Input offset current drift | LM2902B/LM2902BA, TA = -40°C to +1 | - / - / - | - | UNSUPPORTED_KIND |
| IOS | Input offset current | LM2902B/LM2902BA, VS = (V+) – (V–) | -500 pA / 4 nA / - | 5.159e-19 A | PASS |
| IOS | Input offset current | LM2902B/LM2902BA, TA = -40°C to +1 | - / - / 5 nA | 5.159e-19 A | PASS |
| dIOS/dT | Input offset current drift | LM2902B/LM2902BA, TA = -40°C to +1 | - / - / - | - | UNSUPPORTED_KIND |
| EN | Input voltage noise | LM2902B/LM2902BA, f = 0.1Hz to 10H | - / - / - | - | UNSUPPORTED_KIND |
| eN | Input voltage noise density | LM2902B/LM2902BA, RS = 100Ω, VI =  | 35 nV/rtHz / - / - | 347 nV/rtHz | PASS |
| ZID | Differential Input Capacitance | LM2902B/LM2902BA, VS = (V+) – (V–) | - / - / - | - | UNSUPPORTED_KIND |
| ZICM | Common-mode Input Capacitance | LM2902B/LM2902BA, VS = (V+) – (V–) | - / - / - | - | UNSUPPORTED_KIND |
| AOL | Open-loop voltage gain | LM2902B/LM2902BA, Vs = 15V, VO = 1 | 93.98 dB / 100 dB / - | 90.29 dB | FAIL |
| GBW | Gain-bandwidth product | LM2902B/LM2902BA, RL = 1MΩ, CL = 2 | 1.2 MHz / - / - | 16.41 MHz | PASS |
| VO | Voltage output swing from rail | Positive Rail (V+), IOUT = -50µA,  | 1.35 V / 1.5 V / 1.5 V | 4.974 mV | FAIL |
| VO | Voltage output swing from rail | Positive Rail (V+), IOUT = -1mA, V | 1.4 V / 1.6 V / 1.6 V | 153.5 mV | FAIL |
| VO | Voltage output swing from rail | Positive Rail (V+), IOUT = -5mA, V | 1.5 V / 1.75 V / 1.75 V | 1.953 V | FAIL |
| VO | Voltage output swing from rail | Negative Rail (V-), IOUT = 50µA, V | 100 mV / 150 mV / 150 mV | 4.974 mV | FAIL |
| VO | Voltage output swing from rail | Negative Rail (V-), IOUT = 1mA, VS | 750 mV / 1 V / 1 V | 153.5 mV | FAIL |
| VO | Voltage output swing from rail | Vs = 5V, RL ≤ 10kΩ connected to (V | 5 mV / 20 mV / 20 mV | 6.642 mV | PASS |
| IO | Output current | Source, Vs = 15V, VO = V-, VD = 1V | -20 mA / -30 mA / - | 1.135 mA | FAIL |
| IO | Output current | Source, Vs = 15V, VO = V-, VD = 1V | -10 mA / - / - | 1.135 mA | FAIL |
| IO | Output current | Sink, Vs = 15V, VO = V+, VD = -1V, | 10 mA / 20 mA / - | 150.1 mA | PASS |
| IO | Output current | Sink, Vs = 15V, VO = V+, VD = -1V, | 5 mA / - / - | 150.1 mA | PASS |
| IO | Output current | Vid = -1V, VO = (V-) + 200mV, VS = | 50 uA / 85 uA / 85 uA | 1.13 mA | FAIL |
| Isc | Short-circuit current | Vs = 20V, (V+) = 10V, (V-) = -10V, | -40 mA / - / 60 mA | 1.101 mA | PASS |
| CLOAD | Capacitive load drive | Not specified | - / - / - | - | UNSUPPORTED_KIND |
| RO | Open-loop output impedance | f = 1MHz, IO = 0A | - / - / - | - | UNSUPPORTED_KIND |
| IQ | Quiescent current per amplifier | Vs = 5V, IQ = 0A, TA = -40°C to +1 | - / 240 uA / 300 uA | 1.186 mA | FAIL |
| IQ | Quiescent current per amplifier | Vs = 36V, IQ = 0A, TA = -40°C to + | 750 uA / - / - | 1.186 mA | PASS |
| VIO | Input offset voltage | VCC = 5V to MAX, VIC = VICRmin, VO | - / 3 mV / 5 mV | 21 uV | PASS |
| PARAM_117 |  | VIO, Full range, LM324, LM324K, TA | - / - / - | - | UNSUPPORTED_KIND |
| IIO | Input offset current | VO = 1.4V, LM324, LM324K, TA = 25° | - / 2 nA / 30 nA | 5.159e-19 A | PASS |
| PARAM_119 |  | IIO, Full range, LM324, LM324K, TA | - / - / - | - | UNSUPPORTED_KIND |
| IIB | Input bias current | VO = 1.4V, LM324, LM324K, TA = 25° | -20 nA / -150 nA / -20 nA | 2.585e-19 A | PASS |
| PARAM_121 |  | IIB, Full range, LM324, LM324K, TA | - / - / - | - | UNSUPPORTED_KIND |
| VICR | Common-mode input voltage range | VCC = 5V to MAX, LM324, LM324K, TA | - / - / - | - | NOT_TESTABLE_CONDITION |
| PARAM_123 |  | VICR, Full range, LM324, LM324K, T | - / - / - | - | UNSUPPORTED_KIND |
| VOH | High-level output voltage | RL = 2kΩ, LM324, LM324K, TA = 25°C | - / - / - | 388.3 mV | NO_NUMERIC_LIMIT |
| PARAM_125 |  | VCC = MAX, RL = 2kΩ, LM324, LM324K | - / - / - | - | UNSUPPORTED_KIND |
| PARAM_126 |  | RL ≥ 10kΩ, LM324, LM324K, TA = 25° | - / - / - | - | UNSUPPORTED_KIND |
| VOL | Low-level output voltage | RL ≤ 10kΩ, LM324, LM324K, TA = 25° | - / 5 mV / 20 mV | 26.16 mV | FAIL |
| AVD | Large-signal differential voltage ampl | VCC+ = 15V, VO = 1V to 11V, RL ≥ 2 | 93.98 dB / 100 dB / - | 80.76 dB | FAIL |
| PARAM_129 |  | AVD, Full range, LM324, LM324K, TA | - / - / - | - | UNSUPPORTED_KIND |
| CMRR | Common-mode rejection ratio | VIC = VICrmin, LM324, LM324K, TA = | 70 dB / 80 dB / - | 111.2 dB | PASS |
| kSVR | Supply-voltage rejection ratio (ΔVCC / | LM324, LM324K, TA = 25°C | 65 dB / 100 dB / - | 115.9 dB | PASS |
| VOI/ VO2 | Crosstalk attenuation | f = 1kHz to 20kHz, LM324, LM324K,  | - / - / - | - | UNSUPPORTED_KIND |
| IO | Output current | Source, VCC = 15V, VID = 1V, VO =  | -20 mA / -30 mA / -60 mA | 1.101 mA | FAIL |
| PARAM_134 |  | IO, Full range, LM324, LM324K, TA  | - / - / - | - | UNSUPPORTED_KIND |
| IO | Output current | VCC = 15V, VID = -1V, VO = 15V, LM | 10 mA / 20 mA / - | 1.101 mA | FAIL |
| PARAM_136 |  | IO, Full range, LM324, LM324K, TA  | - / - / - | - | UNSUPPORTED_KIND |
| PARAM_137 |  | VID = -1V, VO = 200mV, LM324, LM32 | - / - / - | - | UNSUPPORTED_KIND |
| IOS | Short-circuit output current | VCC at 5V, VO = 0V, VCC– at -5V, L | - / - / 40 mA | 5.159e-19 A | PASS |
| ICC | Supply current (four amplifiers) | VO = 2.5V, no load, LM324, LM324K, | - / 700 uA / 1.2 mA | 1.186 mA | PASS |
| PARAM_140 |  | VCC = MAX, VO = 0.5VCC, no load, L | - / - / - | - | UNSUPPORTED_KIND |
| VIO | Input offset voltage | LM2902, LM2902K, TA = 25°C, VCC =  | - / - / - | 21 uV | NO_NUMERIC_LIMIT |
| VIO | Input offset voltage | LM2902, LM2902K, TA = 25°C, VCC =  | - / - / - | 21 uV | NO_NUMERIC_LIMIT |
| VIO | Input offset voltage | LM2902, LM2902K, TA = 25°C, VCC =  | - / - / - | 21 uV | NO_NUMERIC_LIMIT |
| ΔVIO/ΔT | Input offset voltage temperature drift | LM2902, LM2902K, TA = 25°C, RS = 0 | - / - / - | - | UNSUPPORTED_KIND |
| IIO | Input offset current | LM2902, LM2902K, TA = 25°C, VO = 1 | 2 nA / 50 nA / 50 nA | 5.159e-19 A | PASS |
| ΔIIO/ΔT | Input offset voltage temperature drift | LM2902, LM2902K, TA = 25°C, Full r | - / - / - | - | UNSUPPORTED_KIND |
| IIB | Input bias current | LM2902, LM2902K, TA = 25°C, VO = 1 | -20 nA / -250 nA / -250 nA | 2.585e-19 A | PASS |
| IIB | Input bias current | LM2902, LM2902K, TA = 25°C, Full r | - / -500 nA / -500 nA | 2.585e-19 A | PASS |
| VICR | Common-mode input voltage range | LM2902, LM2902K, TA = 25°C, VCC =  | - / - / - | - | NOT_TESTABLE_CONDITION |
| VICR | Common-mode input voltage range | LM2902, LM2902K, TA = 25°C, Full r | - / - / - | - | NOT_TESTABLE_CONDITION |
| VOH | High-level output voltage | LM2902, LM2902K, TA = 25°C, RL = 1 | - / - / - | 26.16 mV | NO_NUMERIC_LIMIT |
| VOH | High-level output voltage | LM2902, LM2902K, TA = 25°C, VCC =  | 22 V / - / 26 V | 388.3 mV | FAIL |
| VOH | High-level output voltage | LM2902, LM2902K, TA = 25°C, RL ≥ 1 | 23 V / 24 V / 27 V | 26.16 mV | FAIL |
| VOL | Low-level output voltage | LM2902, LM2902K, TA = 25°C, RL ≤ 1 | - / 5 mV / 20 mV | 26.16 mV | FAIL |
| AVD | Large-signal differential voltage ampl | LM2902, LM2902K, TA = 25°C, VCC =  | 87.96 dB / 100 dB / 100 dB | 80.76 dB | FAIL |
| AVD | Large-signal differential voltage ampl | LM2902, LM2902K, TA = 25°C, VCC =  | 83.52 dB / - / - | 80.76 dB | FAIL |
| CMRR | Common-mode rejection ratio | LM2902, LM2902K, TA = 25°C, VIC =  | 50 dB / 80 dB / 80 dB | 111.2 dB | FAIL |
| kSVR | Supply-voltage rejection ratio (ΔVCC / | LM2902, LM2902K, TA = 25°C | 50 dB / 100 dB / 100 dB | 115.9 dB | FAIL |
| VO1/ VO2 | Crosstalk attenuation | LM2902, LM2902K, TA = 25°C, f = 1k | - / - / - | - | UNSUPPORTED_KIND |
| IO | Output current | LM2902, LM2902K, TA = 25°C, Source | - / - / - | 1.101 mA | NO_NUMERIC_LIMIT |
| IO | Output current | LM2902, LM2902K, TA = 25°C, Full r | - / - / - | 1.101 mA | NO_NUMERIC_LIMIT |
| IO | Output current | LM2902, LM2902K, TA = 25°C, Sink,  | - / - / - | 144.7 mA | NO_NUMERIC_LIMIT |
| IO | Output current | LM2902, LM2902K, TA = 25°C, Full r | - / - / - | 1.101 mA | NO_NUMERIC_LIMIT |
| IO | Output current | LM2902, LM2902K, TA = 25°C, VID =  | - / 30 uA / 12 uA | 1.101 mA | FAIL |
| IO | Output current | LM2902, LM2902K, TA = 25°C, VID =  | - / 40 uA / 40 uA | 1.101 mA | FAIL |
| IOS | Short-circuit output current | LM2902, LM2902K, TA = 25°C, VCC at | - / - / - | 5.159e-19 A | NO_NUMERIC_LIMIT |
| IOS | Short-circuit output current | LM2902, LM2902K, TA = 25°C, VCC at | - / - / - | 5.159e-19 A | NO_NUMERIC_LIMIT |
| ICC | Supply current (four amplifiers) | LM2902, LM2902K, TA = 25°C, VO = 2 | - / - / - | 1.186 mA | NO_NUMERIC_LIMIT |
| ICC | Supply current (four amplifiers) | LM2902, LM2902K, TA = 25°C, VCC =  | - / - / - | 1.186 mA | NO_NUMERIC_LIMIT |
| VIO | Input offset voltage | VCC = 5V to 30V, VIC = VICRmin, VO | - / - / - | 21 uV | NO_NUMERIC_LIMIT |
| VIO | Input offset voltage | VCC = 5V to 30V, VIC = VICRmin, VO | - / - / - | 21 uV | NO_NUMERIC_LIMIT |
| IIO | Input offset current | VO = 1.4V, TA = 25°C | - / - / - | 5.159e-19 A | NO_NUMERIC_LIMIT |
| IIO | Input offset current | VO = 1.4V, Full range | - / - / - | 5.159e-19 A | NO_NUMERIC_LIMIT |
| IIB | Input bias current | VO = 1.4V, TA = 25°C | -15 nA / - / -80 nA | 2.585e-19 A | PASS |
| IIB | Input bias current | VO = 1.4V, Full range | -200 nA / - / - | 2.585e-19 A | PASS |
| VICR | Common-mode input voltage range | VCC = 30V, TA = 25°C | - / - / - | - | NOT_TESTABLE_CONDITION |
| VICR | Common-mode input voltage range | VCC = 30V, Full range | - / - / - | - | NOT_TESTABLE_CONDITION |
| VOH | High-level output voltage | RL = 2kΩ, VCC = 30V, Full range | 26 V / - / - | 388.3 mV | FAIL |
| VOH | High-level output voltage | RL ≥ 10kΩ, Full range | 27 V / - / 28 V | 26.16 mV | FAIL |
| VOL | Low-level output voltage | RL ≤ 10kΩ, Full range | - / 5 mV / 20 mV | 26.16 mV | FAIL |
| AVD | Large-signal differential voltage ampl | VCC = 15V, VO = 1V to 11V, RL ≥ 2k | - / - / - | 80.76 dB | NO_NUMERIC_LIMIT |
| AVD | Large-signal differential voltage ampl | VCC = 15V, VO = 1V to 11V, RL ≥ 2k | - / - / - | 80.76 dB | NO_NUMERIC_LIMIT |
| CMRR | Common-mode rejection ratio | VIC = VICRmin, TA = 25°C | 65 dB / - / 80 dB | 111.2 dB | FAIL |
| kSVR | Supply-voltage rejection ratio |  | 65 dB / - / 100 dB | 115.9 dB | FAIL |
| VO1/VO2 | Crosstalk attenuation | f = 1kHz to 20kHz, TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| IO | Output current (Source) | VCC = 15V, VD = 1V, VO = 0V, TA =  | - / - / - | 1.101 mA | NO_NUMERIC_LIMIT |
| IO | Output current (Sink) | VCC = 15V, VD = -1V, VO = 15V, TA  | - / - / - | 1.101 mA | NO_NUMERIC_LIMIT |
| IO | Output current | VID = -1V, VO = 200mV, TA = 25°C | 12 uA / - / 30 uA | 1.101 mA | FAIL |
| IOS | Short-circuit output current | VCC at 5V, VCC- at -5V, VO = 0V, T | - / - / - | 5.159e-19 A | NO_NUMERIC_LIMIT |
| Icc | Supply current (four amplifiers) | VO = 2.5V, no load, TA = Full rang | - / 700 uA / 1.2 mA | 1.186 mA | PASS |
| Icc | Supply current (four amplifiers) | VCC = 30V, VO = 15V, no load, Full | - / 1.4 mA / 3 mA | 1.186 mA | PASS |
| SR | Slew rate at unity gain | RL = 1MΩ, CL = 30pF, V1 = ±10V, TA | - / - / - | 15.61 MHz | NO_NUMERIC_LIMIT |
| B1 | Unity-gain bandwidth | RL = 1MΩ, CL = 20pF, TA = 25°C | - / 1.2 MHz / - | 16.41 MHz | FAIL_TYP |
| Vn | Equivalent input noise voltage | RS = 100Ω, V1 = 0V, f = 1kHz, TA = | - / - / - | - | UNSUPPORTED_KIND |