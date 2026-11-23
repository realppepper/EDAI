# Specification coverage — LM324B

- Verification target rows (all): **163**
- Electrical (testable) rows: **148**
- Mapped to a deterministic fixture: **106**
- Actually measured: **0** → coverage **0.0 %**
- PDG Causal Gate Status: **PDG_STAGE2_DC_TRANSFER**
- Pass among measured rows: **25.0 %** (2/8)
- Pass among unique parameter kinds: **0.0 %** (0/0)
- Sim errors 106 | not observed 0 | no fixture 0 | unsupported kind 32 | not testable 25

| Symbol | Name | Conditions | Limits (canonical) | Measured | Result |
|---|---|---|---|---|---|
| V(ESD) CDM | Electrostatic discharge | LM124, LM124A, LM224, LM224A, LM32 | - / - / - | - | NOT_TESTABLE_ESD |
| VCC | Supply voltage | LM324B, LM324BA, LM2902B, LM2902BA | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| VCM | Common-mode voltage | LM324B, LM324BA, LM2902B, LM2902BA | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating free air temperature | LM124x | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating free air temperature | LM2902xxx, LM2902Bx | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating free air temperature | LM324Bx | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating free air temperature | LM224xx | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating free air temperature | LM324xx | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| RTE | Junction-to-ambient thermal resistance | LMx24, LM2902 | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJA | Junction-to-ambient thermal resistance | LMx24, LM2902 | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJC(top) | Junction-to-case (top) thermal resista | LMx24, LM2902 | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJB | Junction-to-board thermal resistance | LMx24, LM2902 | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJT | Junction-to-top characterization param | LMx24, LM2902 | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJB | Junction-to-board characterization par | LMx24, LM2902 | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJC(bot) | Junction-to-case (bottom) thermal resi | LMx24, LM2902 | - / - / - | - | NOT_TESTABLE_THERMAL |
| VOS | Input offset voltage | LM324B, VS = 5V to 36V (±2.5V to ± | -600 uV / 3 mV / - | - | SIM_ERROR |
| VOS | Input offset voltage | LM324BA, VS = 5V to 36V (±2.5V to  | -300 uV / 2 mV / - | - | SIM_ERROR |
| dVOS/dT | Input offset voltage drift | LM324B, RS = 0Ω, TA = –40°C to +85 | - / - / - | - | UNSUPPORTED_KIND |
| PSRR | Input offset voltage versus power supp | LM324B, Channel separation f = 1kH | - / - / - | - | SIM_ERROR |
| PSRR | Channel separation | LM324B, Channel separation f = 1kH | - / - / - | - | UNSUPPORTED_KIND |
| VCM | Common-mode voltage | LM324B, VS = 3V to 36V | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage | LM324BA, VS = 5V to 36V, TA = –40° | - / - / - | - | NOT_TESTABLE_CONDITION |
| CMRR | Common-mode rejection ratio | LM324B, VS = 3V to 36V, (V–) ≤ VCM | 70 dB / 80 dB / - | - | SIM_ERROR |
| CMRR | Common-mode rejection ratio | LM324BA, VS = 5V to 36V, (V–) ≤ VC | 65 dB / 80 dB / - | - | SIM_ERROR |
| IB | Input bias current | LM324B, TA = –40°C to +85°C | -10 nA / -35 nA / - | - | SIM_ERROR |
| IB | Input bias current | LM324BA, TA = –40°C to +85°C | -60 nA / - / - | - | SIM_ERROR |
| dIOS/dT | Input offset current drift | LM324B, TA = –40°C to +85°C | - / - / - | - | UNSUPPORTED_KIND |
| dIOS/dT | Input offset current drift | LM324BA, TA = –40°C to +85°C | - / - / - | - | UNSUPPORTED_KIND |
| IOS | Input offset current | LM324B, TA = –40°C to +85°C | -500 pA / 4 nA / - | - | SIM_ERROR |
| IOS | Input offset current | LM324BA, TA = –40°C to +85°C | -5 nA / - / 5 nA | - | SIM_ERROR |
| eN | Input voltage noise density | LM324B, RS = 100Ω, VI = 0V, f = 1k | 35 nV/rtHz / - / - | - | SIM_ERROR |
| eN | Input voltage noise | LM324B, f = 0.1Hz to 10Hz | - / - / - | - | UNSUPPORTED_KIND |
| ZID | Differential INPUT CAPACITANCE | LM324B | - / - / - | - | UNSUPPORTED_KIND |
| ZICM | Common-mode INPUT CAPACITANCE | LM324B | - / - / - | - | UNSUPPORTED_KIND |
| AOL | Open-loop voltage gain | LM324B, VS = 15V, VO = 1V to 11V,  | 93.98 dB / 100 dB / - | - | SIM_ERROR |
| GBW | Gain-bandwidth product | LM324B, RL = 1MΩ, CL = 20pF | 1.2 MHz / - / - | - | SIM_ERROR |
| SR | Slew rate | LM324B, RL = 1MΩ, CL = 30pF, VI =  | 0.5 V/us / - / - | - | SIM_ERROR |
| Θm | Phase margin | LM324B, G = +1, RL = 10kΩ, CL = 20 | 56 deg / - / - | - | SIM_ERROR |
| tS | Settling time | LM324B, To 0.1%, VS = 5V, 2V step, | - / - / - | - | UNSUPPORTED_KIND |
| tOR | Overload recovery time | LM324B, VIN × gain > VS | - / - / - | - | UNSUPPORTED_KIND |
| THD+N | Total harmonic distortion + noise | LM324B, G = +1, f = 1kHz, VO = 3.5 | - / - / - | - | UNSUPPORTED_KIND |
| VO | Voltage output swing from rail | VS = (V+) – (V–) = 5V to 36V (±2.5 | 1.35 V / 1.5 V / 1.5 V | - | SIM_ERROR |
| VO | Voltage output swing from rail | VS = (V+) – (V–) = 5V to 36V (±2.5 | 1.4 V / 1.4 V / 1.6 V | - | SIM_ERROR |
| VO | Voltage output swing from rail | VS = (V+) – (V–) = 5V to 36V (±2.5 | 1.5 V / 1.5 V / 1.75 V | - | SIM_ERROR |
| VO | Voltage output swing from rail | VS = (V+) – (V–) = 5V to 36V (±2.5 | 100 uV / 100 mV / 150 mV | - | SIM_ERROR |
| VO | Voltage output swing from rail | VS = 5V, RL ≤ 10kΩ connected to (V | 750 mV / 750 mV / 1 V | - | SIM_ERROR |
| IO | Output current | VS = 5V, RL ≤ 10kΩ connected to (V | - / - / - | - | SIM_ERROR |
| IO | Output current | Source, VS = 15V, VO = V–, VID = 1 | -20 mA / -20 mA / -30 mA | - | SIM_ERROR |
| IO | Output current | Sink, VS = 15V, VO = V+, VID = –1V | -10 mA / -10 mA / 20 mA | - | SIM_ERROR |
| IO | Output current | VID = –1V, VO = (V–) + 200mV, TA = | 5 uA / 5 uA / 5 uA | - | SIM_ERROR |
| ISC | Short-circuit current | VS = 20V, (V+) = 10V, (V–) = –10V, | -40 mA / -40 mA / 60 mA | - | SIM_ERROR |
| CLOAD | Capacitive load drive | Not specified | - / - / - | - | UNSUPPORTED_KIND |
| RO | Open-loop output impedance | f = 1MHz, IO = 0A | - / - / - | - | UNSUPPORTED_KIND |
| IQ | Quiescent current per amplifier | VS = 5V, IO = 0A, TA = –40°C to +8 | 240 uA / 240 uA / 300 uA | - | SIM_ERROR |
| IQ | Quiescent current per amplifier | VS = 36V, IO = 0A, TA = –40°C to + | 350 uA / 350 uA / 750 uA | - | SIM_ERROR |
| VOS | Input offset voltage | LM2902B, VS = (V+) – (V–) = 5V to  | -600 uV / 3 mV / - | - | SIM_ERROR |
| VOS | Input offset voltage | LM2902BA, VS = (V+) – (V–) = 5V to | -300 uV / 2 mV / - | - | SIM_ERROR |
| dVOS/dT | Input offset voltage drift | LM2902B, TA = –40°C to +125°C | - / - / - | - | UNSUPPORTED_KIND |
| dVOS/dT | Input offset voltage drift | LM2902BA, TA = –40°C to +125°C | - / - / - | - | UNSUPPORTED_KIND |
| dVOS/dT | Input offset voltage drift | RS = 0∓, TA = –40°C to +125°C | - / - / - | - | UNSUPPORTED_KIND |
| PSRR | Input offset voltage versus power supp | Channel separation f = 1kHz to 20k | - / - / - | - | SIM_ERROR |
| PSRR | Input offset voltage versus power supp | Channel separation f = 1kHz to 20k | - / - / - | - | SIM_ERROR |
| VCM | Common-mode voltage range | VS = 3V to 36V | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | VS = 5V to 36V, TA = –40°C to +125 | - / - / - | - | NOT_TESTABLE_CONDITION |
| CMRR | Common-mode rejection ratio | VS = 3V to 36V, (V–) ≤ VCM ≤ (V+)  | 70 dB / 80 dB / - | - | SIM_ERROR |
| CMRR | Common-mode rejection ratio | VS = 5V to 36V, (V–) ≤ VCM ≤ (V+)  | 65 dB / 80 dB / - | - | SIM_ERROR |
| IB | Input bias current | TA = –40°C to +125°C | -10 nA / - / -35 nA | - | SIM_ERROR |
| IB | Input bias current | TA = –40°C to +125°C | -60 nA / - / - | - | SIM_ERROR |
| dIOS/dT | Input offset current drift | TA = –40°C to +125°C | - / - / - | - | UNSUPPORTED_KIND |
| IOS | Input offset current | TA = –40°C to +125°C | -500 pA / - / 4 nA | - | SIM_ERROR |
| dIOS/dT | Input offset current drift | TA = –40°C to +125°C | - / - / - | - | UNSUPPORTED_KIND |
| EN | Input voltage noise | f = 0.1Hz to 10Hz | - / - / - | - | UNSUPPORTED_KIND |
| eN | Input voltage noise density | RS = 100Ω, VI = 0V, f = 1kHz (see  | - / - / - | - | SIM_ERROR |
| ZID | Differential Input Capacitance |  | - / - / - | - | NOT_TESTABLE_CONDITION |
| ZICM | Common-mode Input Capacitance |  | - / - / - | - | NOT_TESTABLE_CONDITION |
| AOL | Open-loop voltage gain | VS = 15V, VO = 1V to 11V, RL ≥ 10k | 93.98 dB / 100 dB / - | - | SIM_ERROR |
| GBW | Gain-bandwidth product | RL = 1MΩ, CL = 20pF (see Figure 6- | 1.2 MHz / - / - | - | SIM_ERROR |
| SR | Slew rate | RL = 1MΩ, CL = 30pF, VI = ±10V (se | 0.5 V/us / - / - | - | SIM_ERROR |
| Θm | Phase margin | G = +1, RL = 10kΩ, CL = 20pF | 56 deg / - / - | - | SIM_ERROR |
| tS | Settling time | To 0.1%, VS = 5V, 2V step , G = +1 | - / - / - | - | UNSUPPORTED_KIND |
| tOR | Overload recovery time | VIN × gain > VS | - / - / - | - | UNSUPPORTED_KIND |
| THD+N | Total harmonic distortion + noise | G = +1, f = 1kHz, VO = 3.53VRMS, V | - / - / - | - | UNSUPPORTED_KIND |
| VO | Voltage output swing from rail | VS = (V+) – (V–) = 5V to 36V (±2.5 | 1.4 V / 1.5 V / 1.6 V | - | SIM_ERROR |
| VO | Voltage output swing from rail | VS = 5V, RL ≤ 10kΩm connected to ( | 750 mV / 1 V / 1 V | - | SIM_ERROR |
| VO | Voltage output swing from rail | VS = 5V, RL ≤ 10kΩm connected to ( | 5 mV / 20 mV / 20 mV | - | SIM_ERROR |
| IO | Output current | VS = 15V, VO = V–, VID = 1V, TA =  | -20 mA / -30 mA / - | - | SIM_ERROR |
| IO | Output current | VS = 15V, VO = V+, VID = –1V, TA = | -10 mA / - / 20 mA | - | SIM_ERROR |
| IO | Output current | VID = –1V, VO = (V–) + 200mV | 5 mA / - / 20 mA | - | SIM_ERROR |
| ISC | Short-circuit current | VS = 20V, (V+) = 10V, (V–) = –10V, | -40 mA / - / 60 mA | - | SIM_ERROR |
| CLOAD | Capacitive load drive | Not specified | - / - / - | - | UNSUPPORTED_KIND |
| RO | Open-loop output impedance | f = 1MHz, IO = 0A | - / - / - | - | UNSUPPORTED_KIND |
| IQ | Quiescent current per amplifier | VS = 5V, IO = 0A, TA = –40°C to +1 | 240 uA / - / 300 uA | - | SIM_ERROR |
| IQ | Quiescent current per amplifier | VS = 36V, IO = 0A, TA = –40°C to + | 750 uA / - / - | - | SIM_ERROR |
| VIO | Input offset voltage | VCC = 5V to MAX, VIC = VICRmin, VO | 5 mV / 3 mV / 7 mV | - | SIM_ERROR |
| VIO | Input offset voltage | VCC = 5V to MAX, VIC = VICRmin, VO | 7 mV / 9 mV / - | - | SIM_ERROR |
| IIO | Input offset current | VO = 1.4V, TA = 25°C, Full range,  | 2 nA / 30 nA / 50 nA | - | SIM_ERROR |
| IIO | Input offset current | VO = 1.4V, TA = 25°C, Full range,  | 2 nA / 30 nA / 50 nA | - | SIM_ERROR |
| IIB | Input bias current | VO = 1.4V, TA = 25°C, Full range,  | -20 nA / -150 nA / -250 nA | - | SIM_ERROR |
| IIB | Input bias current | VO = 1.4V, TA = 25°C, Full range,  | -20 nA / -250 nA / -500 nA | - | SIM_ERROR |
| VICR | Common-mode input voltage range | VCC = 5V to MAX, TA = 25°C, Full r | - / - / - | - | NOT_TESTABLE_CONDITION |
| VOH | High-level output voltage | RL = 2kΩ, TA = 25°C, LM124, LM224, | - / - / - | - | SIM_ERROR |
| VOH | High-level output voltage | RL = 2kΩ, TA = 25°C, LM324, LM324K | - / - / - | - | SIM_ERROR |
| VOH | High-level output voltage | VCC = MAX, RL = 2kΩ, Full range, L | 26 V / 26 V / - | - | SIM_ERROR |
| VOH | High-level output voltage | VCC = MAX, RL = 2kΩ, Full range, L | 26 V / 26 V / - | - | SIM_ERROR |
| VOH | High-level output voltage | RL ≥ 10kΩ, Full range, LM124, LM22 | 27 V / 27 V / - | - | SIM_ERROR |
| VOH | High-level output voltage | RL ≥ 10kΩ, Full range, LM324, LM32 | 27 V / 27 V / - | - | SIM_ERROR |
| VOL | Low-level output voltage | RL ≤ 10kΩ, Full range, LM124, LM22 | 5 mV / 20 mV / - | - | SIM_ERROR |
| VOL | Low-level output voltage | RL ≤ 10kΩ, Full range, LM324, LM32 | 5 mV / 20 mV / - | - | SIM_ERROR |
| AVD | Large-signal differential voltage ampl | VCC+ = 15V, VO = 1V to 11V, RL ≥ 2 | 93.98 dB / 100 dB / - | - | SIM_ERROR |
| AVD | Large-signal differential voltage ampl | VCC+ = 15V, VO = 1V to 11V, RL ≥ 2 | 87.96 dB / 100 dB / - | - | SIM_ERROR |
| CMRR | Common-mode rejection ratio | VIC = VICRmin, TA = 25°C, LM124, L | 70 dB / 80 dB / - | - | SIM_ERROR |
| CMRR | Common-mode rejection ratio | VIC = VICRmin, TA = 25°C, LM324, L | 65 dB / 80 dB / - | - | SIM_ERROR |
| kSVR | Supply-voltage rejection ratio (ΔVCC / | TA = 25°C, LM124, LM224, LM224K | 65 dB / 100 dB / - | - | SIM_ERROR |
| kSVR | Supply-voltage rejection ratio (ΔVCC / | TA = 25°C, LM324, LM324K | 65 dB / 100 dB / - | - | SIM_ERROR |
| VO1/ VO2 | Crosstalk attenuation | f = 1kHz to 20kHz, TA = 25°C, LM12 | - / - / - | - | UNSUPPORTED_KIND |
| VO1/ VO2 | Crosstalk attenuation | f = 1kHz to 20kHz, TA = 25°C, LM32 | - / - / - | - | UNSUPPORTED_KIND |
| IO | Output current | Source, VCC = 15V, VID = 1V, VO =  | -20 mA / -30 mA / -60 mA | - | SIM_ERROR |
| IO | Output current | VCC = 15V, VID = –1V, VO = 15V, TA | -10 mA / -10 mA / - | - | SIM_ERROR |
| IO | Output current | VCC = 15V, VID = –1V, VO = 15V, TA | 10 mA / 20 mA / - | - | SIM_ERROR |
| IO | Output current | VID = –1V, VO = 200mV, TA = 25°C,  | 5 uA / 5 uA / - | - | SIM_ERROR |
| VIO | Input offset voltage | VCC = 5V to MAX, VIC = VICRmin, VO | 3 mV / 7 mV / 3 mV | - | SIM_ERROR |
| VIO | Input offset voltage | VCC = 5V to MAX, VIC = VICRmin, VO | 10 mV / 10 mV / - | - | SIM_ERROR |
| ΔVIO/ΔT | Input offset voltage temperature drift | RS = 0Ω, Full range, LM2902, LM290 | - / - / - | - | UNSUPPORTED_KIND |
| ΔVIO/ΔT | Input offset voltage temperature drift | RS = 0Ω, Full range, LM2902KV, LM2 | - / - / - | - | UNSUPPORTED_KIND |
| IIO | Input offset current | VO = 1.4V, Full range, LM2902, LM2 | 2 nA / 50 nA / 2 nA | - | SIM_ERROR |
| IIO | Input offset current | VO = 1.4V, Full range, LM2902KV, L | 2 nA / 50 nA / - | - | SIM_ERROR |
| ΔIIO/ΔT | Input offset voltage temperature drift | Full range, LM2902, LM2902K, TA =  | - / - / - | - | UNSUPPORTED_KIND |
| ΔIIO/ΔT | Input offset voltage temperature drift | Full range, LM2902KV, LM2902KAV, T | - / - / - | - | UNSUPPORTED_KIND |
| IIB | Input bias current | VO = 1.4V, Full range, LM2902, LM2 | -20 nA / -250 nA / -20 nA | - | SIM_ERROR |
| IIB | Input bias current | VO = 1.4V, Full range, LM2902KV, L | -20 nA / -250 nA / - | - | SIM_ERROR |
| VICR | Common-mode input voltage range | VCC = 5V to MAX, Full range, LM290 | - / - / - | - | NOT_TESTABLE_CONDITION |
| VICR | Common-mode input voltage range | VCC = 5V to MAX, Full range, LM290 | - / - / - | - | NOT_TESTABLE_CONDITION |
| VOH | High-level output voltage | RL = 10kΩ, Full range, LM2902, LM2 | - / - / - | - | SIM_ERROR |
| VOH | High-level output voltage | RL = 2kΩ, Full range, LM2902KV, LM | - / - / - | - | SIM_ERROR |
| VOH | High-level output voltage | RL ≥ 10kΩ, Full range, LM2902, LM2 | 22 V / 26 V / - | - | SIM_ERROR |
| VOH | High-level output voltage | RL ≥ 10kΩ, Full range, LM2902KV, L | 23 V / 24 V / 27 V | - | SIM_ERROR |
| VOL | Low-level output voltage | RL ≤ 10kΩ, Full range, LM2902, LM2 | 5 mV / 20 mV / 5 mV | - | SIM_ERROR |
| VOL | Low-level output voltage | RL ≤ 10kΩ, Full range, LM2902KV, L | 5 mV / 20 mV / - | - | SIM_ERROR |
| AVD | Large-signal differential voltage ampl | VCC = 15V, VO = 1V to 11V, RL ≥ 2k | 87.96 dB / 100 dB / 87.96 dB | - | SIM_ERROR |
| AVD | Large-signal differential voltage ampl | VCC = 15V, VO = 1V to 11V, RL ≥ 2k | 87.96 dB / 100 dB / - | - | SIM_ERROR |
| AVD | Large-signal differential voltage ampl | VCC = 15V, VO = 1V to 11V, RL ≥ 2k | 83.52 dB / 83.52 dB / - | - | SIM_ERROR |
| CMRR | Common-mode rejection ratio | VIC = VICRmin, Full range, LM2902, | 50 dB / 80 dB / 60 dB | - | SIM_ERROR |
| CMRR | Common-mode rejection ratio | VIC = VICRmin, Full range, LM2902K | 60 dB / 80 dB / - | - | SIM_ERROR |
| kSVR | Supply-voltage rejection ratio (ΔVCC / | Full range, LM2902, LM2902K, TA =  | 50 dB / 100 dB / 60 dB | - | SIM_ERROR |
| kSVR | Supply-voltage rejection ratio (ΔVCC / | Full range, LM2902KV, LM2902KAV, T | 60 dB / 100 dB / - | - | SIM_ERROR |
| VO1/ VO2 | Crosstalk attenuation | f = 1kHz to 20kHz, Full range, LM2 | - / - / - | - | UNSUPPORTED_KIND |
| VO1/ VO2 | Crosstalk attenuation | f = 1kHz to 20kHz, Full range, LM2 | - / - / - | - | UNSUPPORTED_KIND |
| IO | Output current | Source, VCC = 15V, VID = 1V, VO =  | -20 mA / -30 mA / -60 mA | - | SIM_ERROR |
| VIO | Input offset voltage | VCC = 5V to 30V, VIC = VICRmin, VO | 2 mV / 2 mV / 3 mV | - | SIM_ERROR |
| IIO | Input offset current | VO = 1.4V, 25°C | 10 nA / 2 nA / 15 nA | - | SIM_ERROR |
| IIB | Input bias current | VO = 1.4V, 25°C | -50 nA / -15 nA / -80 nA | - | SIM_ERROR |
| VICR | Common-mode input voltage range | VCC = 30V, 25°C | - / - / - | - | NOT_TESTABLE_CONDITION |
| VOH | High-level output voltage | RL = 2kΩ, 25°C, VCC = 30V | 26 V / 26 V / 26 V | - | SIM_ERROR |
| VOL | Low-level output voltage | RL ≤ 10kΩ, Full range | 20 mV / 5 mV / 20 mV | - | SIM_ERROR |
| AVD | Large-signal differential voltage ampl | VCC = 15V, VO = 1V to 11V, RL ≥ 2k | 87.96 dB / 87.96 dB / 83.52 dB | - | SIM_ERROR |
| CMRR | Common-mode rejection ratio | VIC = VICRmin, 25°C | 70 dB / 70 dB / 80 dB | - | SIM_ERROR |
| kSVR | Supply-voltage rejection ratio | 25°C | 65 dB / 65 dB / 100 dB | - | SIM_ERROR |
| VO1/ VO2 | Crosstalk attenuation | f = 1kHz to 20kHz, 25°C | - / - / - | - | UNSUPPORTED_KIND |
| IO | Output current | Source, VCC = 15V, VID = 1V, VO =  | -20 mA / -20 mA / -30 mA | - | SIM_ERROR |
| IO | Output current | Sink, VCC = 15V, VID = -1V, VO = 1 | 10 mA / 10 mA / 20 mA | - | SIM_ERROR |
| IOS | Short-circuit output current | VCC at 5V, VCC- at -5V, VO = 0V, 2 | 40 mA / 60 mA / 40 mA | - | SIM_ERROR |
| ICC | Supply current (four amplifiers) | VO = 2.5V, no load, Full range | 700 uA / 1.2 mA / 1.2 mA | - | SIM_ERROR |
| ICC | Supply current (four amplifiers) | VCC = 30V, VO = 15V, no load, Full | 1.4 mA / 3 mA / 3 mA | - | SIM_ERROR |