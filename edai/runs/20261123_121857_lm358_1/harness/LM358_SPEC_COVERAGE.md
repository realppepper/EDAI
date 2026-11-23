# Specification coverage — LM358

- Verification target rows (all): **203**
- Electrical (testable) rows: **175**
- Mapped to a deterministic fixture: **134**
- Actually measured: **0** → coverage **0.0 %**
- PDG Causal Gate Status: **PDG_STAGE0_TOPOLOGY**
- Pass among measured rows: **0.0 %** (0/0)
- Pass among unique parameter kinds: **0.0 %** (0/0)
- Sim errors 134 | not observed 0 | no fixture 0 | unsupported kind 28 | not testable 41

| Symbol | Name | Conditions | Limits (canonical) | Measured | Result |
|---|---|---|---|---|---|
| Vs Supply voltage, Vs= ([V+] - [V-]) | Vs Supply voltage | LM358B, LM358BA, LM2904B, LM2904BA | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| Vs Supply voltage, Vs= ([V+] - [V-]) | Vs Supply voltage | LM158, LM258, LM358, LM158A, LM258 | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| Vs Supply voltage, Vs= ([V+] - [V-]) | Vs Supply voltage | LM2904 | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| VCM Common-mode voltage | VCM Common-mode voltage | All variants | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA Operating ambient temperature | Operating ambient temperature | LM358B, LM358BA | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA Operating ambient temperature | Operating ambient temperature | LM2904B, LM2904BA, LM2904, LM2904V | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA Operating ambient temperature | Operating ambient temperature | LM358, LM358A | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA Operating ambient temperature | Operating ambient temperature | LM258, LM258A | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA Operating ambient temperature | Operating ambient temperature | LM158, LM158A | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| R_BJA | Junction-to-ambient thermal resistance | LM258, LM258A, LM358, LM358A, LM35 | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJA | Junction-to-ambient thermal resistance | LM258, LM258A, LM358, LM358A, LM35 | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJA | Junction-to-ambient thermal resistance | LM258, LM258A, LM358, LM358A, LM35 | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJA | Junction-to-ambient thermal resistance | LM258, LM258A, LM358, LM358A, LM35 | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJA | Junction-to-ambient thermal resistance | LM258, LM258A, LM358, LM358A, LM35 | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJA | Junction-to-ambient thermal resistance | LM158, LM158A, Package FK (LCCC) | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJC(top) | Junction-to-case (top) thermal resista | LM258, LM258A, LM358, LM358A, LM35 | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJC(top) | Junction-to-case (top) thermal resista | LM258, LM258A, LM358, LM358A, LM35 | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJC(top) | Junction-to-case (top) thermal resista | LM258, LM258A, LM358, LM358A, LM35 | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJC(top) | Junction-to-case (top) thermal resista | LM258, LM258A, LM358, LM358A, LM35 | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJC(top) | Junction-to-case (top) thermal resista | LM258, LM258A, LM358, LM358A, LM35 | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJC(top) | Junction-to-case (top) thermal resista | LM158, LM158A, Package FK (LCCC) | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJB | Junction-to-board thermal resistance | LM258, LM258A, LM358, LM358A, LM35 | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJB | Junction-to-board thermal resistance | LM258, LM258A, LM358, LM358A, LM35 | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJB | Junction-to-board thermal resistance | LM258, LM258A, LM358, LM358A, LM35 | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJB | Junction-to-board thermal resistance | LM258, LM258A, LM358, LM358A, LM35 | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJB | Junction-to-board thermal resistance | LM258, LM258A, LM358, LM358A, LM35 | - / - / - | - | NOT_TESTABLE_THERMAL |
| R_BJB | Junction-to-board thermal resistance | LM258, LM258A, LM358, LM358A, LM35 | - / - / - | - | NOT_TESTABLE_THERMAL |
| Psi_JT | Junction-to-top characterization param | LM258, LM258A, LM358, LM358A, LM35 | - / - / - | - | NOT_TESTABLE_THERMAL |
| VOS | Input offset voltage | LM358B, VS = (V+) – (V–) = 5 V – 3 | - / 300 uV / 3 mV | - | SIM_ERROR |
| VOS | Input offset voltage | LM358B, TA = -40°C to +85°C, VS =  | - / - / 4 mV | - | SIM_ERROR |
| VOS | Input offset voltage | LM358BA, VS = (V+) – (V–) = 5 V –  | - / - / 2 mV | - | SIM_ERROR |
| VOS | Input offset voltage | LM358BA, TA = -40°C to +85°C, VS = | - / - / 2.5 mV | - | SIM_ERROR |
| dVOS/dT | Input offset voltage drift | LM358B, TA = -40°C to +85°C(1), VS | - / - / - | - | UNSUPPORTED_KIND |
| PSRR | Power supply rejection ratio | LM358B, VS = (V+) – (V–) = 5 V – 3 | 96.48 dB / 114 dB / - | - | SIM_ERROR |
| PSRR | Channel separation, dc | LM358B, f = 1 kHz to 20 kHz, VS =  | - / - / - | - | UNSUPPORTED_KIND |
| VCM | Common-mode voltage range | LM358B, Vs = 3 V to 36 V, VS = (V+ | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | LM358B, Vs = 5 V to 36 V, TA = -40 | - / - / - | - | NOT_TESTABLE_CONDITION |
| CMRR | Common-mode rejection ratio | LM358B, (V-) ≤ VCM ≤ (V+) - 1.5 V, | 80 dB / 93.98 dB / - | - | SIM_ERROR |
| CMRR | Common-mode rejection ratio | LM358B, (V-) ≤ VCM ≤ (V+) - 2.0 V, | 70.01 dB / 92.04 dB / - | - | SIM_ERROR |
| IB | Input bias current | LM358B, VS = (V+) – (V–) = 5 V – 3 | -10 nA / -35 nA / - | - | SIM_ERROR |
| IB | Input bias current | LM358B, TA = -40°C to +85°C(1), VS | -50 nA / - / - | - | SIM_ERROR |
| IOS | Input offset current | LM358B, VS = (V+) – (V–) = 5 V – 3 | - / 500 pA / 4 nA | - | SIM_ERROR |
| IOS | Input offset current | LM358B, TA = -40°C to +85°C(1), VS | 5 nA / - / - | - | SIM_ERROR |
| dlOS/dT | Input offset current drift | LM358B, TA = -40°C to +85°C, VS =  | - / - / - | - | UNSUPPORTED_KIND |
| En | Input voltage noise | LM358B, f = 0.1 to 10 Hz, VS = (V+ | - / - / - | - | UNSUPPORTED_KIND |
| en | Input voltage noise density | LM358B, f = 1 kHz, VS = (V+) – (V– | - / - / - | - | SIM_ERROR |
| ZID | Differential | LM358B, VS = (V+) – (V–) = 5 V – 3 | - / - / - | - | UNSUPPORTED_KIND |
| ZIC | Common-mode | LM358B, VS = (V+) – (V–) = 5 V – 3 | - / - / - | - | UNSUPPORTED_KIND |
| AOL | Open-loop voltage gain | LM358B, Vs = 15 V; VO = 1 V to 11  | 96.9 dB / 102.9 dB / - | - | SIM_ERROR |
| AOL | Open-loop voltage gain | LM358B, TA = -40°C to +85°C, VS =  | 90.88 dB / - / - | - | SIM_ERROR |
| GBW | Gain bandwidth product | LM358B, VS = (V+) – (V–) = 5 V – 3 | 1.2 MHz / - / - | - | SIM_ERROR |
| SR | Slew rate | LM358B, G = + 1, VS = (V+) – (V–)  | 0.5 V/us / - / - | - | SIM_ERROR |
| Θm | Phase margin | LM358B, G = + 1, RL = 10kΩ, CL = 2 | 56 deg / - / - | - | SIM_ERROR |
| I_Q | Quiescent current per amplifier | LM358B, TA = −40°C to +85°C, Vs =  | - / 300 uA / 460 uA | - | SIM_ERROR |
| I_Q | Quiescent current per amplifier | LM358B, TA = −40°C to +85°C, Vs =  | - / - / 800 uA | - | SIM_ERROR |
| VOS | Input offset voltage | LM2904B, VS = (V+) – (V–) = 5 V -  | -300 uV / 3 mV / - | - | SIM_ERROR |
| VOS | Input offset voltage | LM2904BA, TA = −40°C to +125°C, VS | - / 4 mV / 2 mV | - | SIM_ERROR |
| VOS | Input offset voltage | LM2904BA, TA = −40°C to +125°C, VS | - / 3 mV / - | - | SIM_ERROR |
| dVOS/dT | Input offset voltage drift | LM2904B, TA = −40°C to +125°C, VS  | - / - / - | - | UNSUPPORTED_KIND |
| PSRR | Power Supply Rejection Ratio | LM2904B, VS = (V+) – (V–) = 5 V -  | - / 96.48 dB / - | - | SIM_ERROR |
| PSRR | Channel separation, dc | LM2904B, f = 1 kHz to 20 kHz, VS = | - / - / - | - | UNSUPPORTED_KIND |
| VCM | Common-mode voltage range | LM2904B, Vs = 3 V to 36 V, VS = (V | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | LM2904B, Vs = 5 V to 36 V, TA = −4 | - / - / - | - | NOT_TESTABLE_CONDITION |
| CMRR | Common-mode rejection ratio | LM2904B, (V-) ≤ VCM ≤ (V+) – 1.5 V | - / 80 dB / - | - | SIM_ERROR |
| CMRR | Common-mode rejection ratio | LM2904B, (V-) ≤ VCM ≤ (V+) – 2.0 V | - / - / - | - | SIM_ERROR |
| IB | Input bias current | LM2904B, VS = (V+) – (V–) = 5 V -  | -10 nA / -35 nA / - | - | SIM_ERROR |
| IOS | Input offset current | LM2904B, TA = −40°C to +125°C, VS  | - / -50 nA / - | - | SIM_ERROR |
| diOS/dT | Input offset current drift | LM2904B, TA = −40°C to +125°C, VS  | - / - / - | - | UNSUPPORTED_KIND |
| En | Input voltage noise | LM2904B, f = 0.1 to 10 Hz, VS = (V | - / - / - | - | UNSUPPORTED_KIND |
| en | Input voltage noise density | LM2904B, f = 1 kHz, VS = (V+) – (V | - / - / - | - | SIM_ERROR |
| ZID | Differential | LM2904B, VS = (V+) – (V–) = 5 V -  | - / - / - | - | UNSUPPORTED_KIND |
| ZIC | Common-mode | LM2904B, VS = (V+) – (V–) = 5 V -  | - / - / - | - | UNSUPPORTED_KIND |
| AOL | Open-loop voltage gain | LM2904B, Vs = 15 V; VO = 1 V to 11 | 96.9 dB / 102.9 dB / - | - | SIM_ERROR |
| AOL | Open-loop voltage gain | LM2904B, TA = −40°C to +125°C, VS  | 90.88 dB / - / - | - | SIM_ERROR |
| GBW | Gain bandwidth product | LM2904B, VS = (V+) – (V–) = 5 V -  | 1.2 MHz / - / - | - | SIM_ERROR |
| SR | Slew rate | LM2904B, G = + 1, VS = (V+) – (V–) | 0.5 V/us / - / - | - | SIM_ERROR |
| Θm | Phase margin | LM2904B, G = + 1, RL = 10kΩ, CL =  | 56 deg / - / - | - | SIM_ERROR |
| tOR | Overload recovery time | LM2904B, Vin × gain > Vs, VS = (V+ | - / - / - | - | UNSUPPORTED_KIND |
| ts | Settling time | LM2904B, To 0.1%, Vs = 5 V, 2-V St | - / - / - | - | UNSUPPORTED_KIND |
| THD+N | Total harmonic distortion + noise | LM2904B, G = + 1, f = 1 kHz, VO =  | - / - / - | - | UNSUPPORTED_KIND |
| I_Q | Quiescent current per amplifier | Vs = 5 V; I_O = 0 A, TA = −40°C to | - / 300 uA / 460 uA | - | SIM_ERROR |
| I_Q | Quiescent current per amplifier | Vs = 36 V; I_O = 0 A, TA = −40°C t | 800 uA / - / - | - | SIM_ERROR |
| VOS | Input offset voltage | LM358, Vs = 5 V to 30 V; VC M = 0  | - / 3 mV / 7 mV | - | SIM_ERROR |
| VOS | Input offset voltage | LM358A, Vs = 5 V to 30 V; VC M = 0 | - / 2 mV / 3 mV | - | SIM_ERROR |
| dVOS/dT | Input offset voltage drift | LM358, TA = 0°C to 70°C | - / - / - | - | UNSUPPORTED_KIND |
| dVOS/dT | Input offset voltage drift | LM358A, TA = 0°C to 70°C | - / - / - | - | UNSUPPORTED_KIND |
| PSRR | Input offset voltage vs power supply ( | Vs = 5 V to 30 V | - / - / - | - | SIM_ERROR |
| VOI/VO2 | Channel separation | f = 1 kHz to 20 kHz | - / - / - | - | UNSUPPORTED_KIND |
| VCM | Common-mode voltage range | LM358, Vs = 5 V to 30 V | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | LM358A, Vs = 30 V | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | LM358, Vs = 5 V to 30 V, TA = 0°C  | - / - / - | - | NOT_TESTABLE_CONDITION |
| CMRR | Common-mode rejection ratio | Vs = 5 V to 30 V; VM = 0 V | 65 dB / 80 dB / - | - | SIM_ERROR |
| IB | Input bias current | LM358, VO = 1.4 V, VO = 1.4 V | -20 nA / -250 nA / - | - | SIM_ERROR |
| IB | Input bias current | LM358, VO = 1.4 V, TA = 0°C to 70° | - / -500 nA / - | - | SIM_ERROR |
| IB | Input bias current | LM358A, VO = 1.4 V | -15 nA / -100 nA / - | - | SIM_ERROR |
| IB | Input bias current | LM358A, VO = 1.4 V, TA = 0°C to 70 | - / -200 nA / - | - | SIM_ERROR |
| IOS | Input offset current | LM358, VO = 1.4 V | - / 2 nA / 50 nA | - | SIM_ERROR |
| IOS | Input offset current | LM358, VO = 1.4 V, TA = 0°C to 70° | - / 150 nA / - | - | SIM_ERROR |
| IOS | Input offset current | LM358A, VO = 1.4 V | - / 2 nA / 30 nA | - | SIM_ERROR |
| IOS | Input offset current | LM358A, VO = 1.4 V, TA = 0°C to 70 | - / 75 nA / - | - | SIM_ERROR |
| dlOS/dT | Input offset current drift | VO = 1.4 V | - / - / - | - | UNSUPPORTED_KIND |
| eη | Input voltage noise density | f = 1 kHz | - / - / - | - | SIM_ERROR |
| AOL | Open-loop voltage gain | Vs = 15 V; VO = 1 V to 11 V; RL ≥  | 87.96 dB / 100 dB / - | - | SIM_ERROR |
| AOL | Open-loop voltage gain | TA = 0°C to 70°C | 83.52 dB / - / - | - | SIM_ERROR |
| GBW | Gain bandwidth product | N/A | 700 kHz / - / - | - | SIM_ERROR |
| SR | Slew rate | G = +1 | 0.3 V/us / - / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | Vs = 30 V; RL = 2 kΩ, TA = 0°C to  | - / 4 V / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | Vs = 30 V; RL ≥ 10 kΩ | 2 V / 3 V / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | Vs = 5 V; RL ≥ 2 kΩ | - / - / 1.5 V | - | SIM_ERROR |
| VO | Voltage output swing from rail | Vs = 5 V; RL ≤ 10 kΩ, TA = 0°C to  | 5 mV / 20 mV / - | - | SIM_ERROR |
| IO | Output current | Vs = 15 V; VO = 0 V; VD = 1 V, Sou | -20 mA / -30 mA / - | - | SIM_ERROR |
| IO | Output current | LM358A, Vs = 15 V; VO = 0 V; VD =  | - / -60 mA / - | - | SIM_ERROR |
| IO | Output current | LM358A, Vs = 15 V; VO = 0 V; VD =  | -10 mA / - / - | - | SIM_ERROR |
| IO | Output current | Vs = 15 V; VO = 15 V; VID = −1 V,  | 10 mA / 20 mA / - | - | SIM_ERROR |
| IO | Output current | Vs = 15 V; VO = 15 V; VID = −1 V,  | 5 mA / - / - | - | SIM_ERROR |
| IO | Output current | VID = −1 V; VO = 200 mV | 12 uA / 30 uA / - | - | SIM_ERROR |
| ISC | Short-circuit current | Vs = 10 V; VO = VS / 2 | -40 mA / -60 mA / 40 mA | - | SIM_ERROR |
| PARAM_117 | None |  | - / - / - | - | NOT_TESTABLE_CONDITION |
| VOS | Input offset voltage | Vs = 5 V to maximum; VC M = 0 V; V | - / 3 mV / 7 mV | - | SIM_ERROR |
| VOS | Input offset voltage | Vs = 5 V to maximum; VC M = 0 V; V | - / 10 mV / - | - | SIM_ERROR |
| VOS | Input offset voltage | Vs = 5 V to maximum; VC M = 0 V; V | - / 1 mV / 2 mV | - | SIM_ERROR |
| dVOS/dT | Input offset voltage drift | dVOS/dT, TA = -40°C to 125°C | - / - / - | - | UNSUPPORTED_KIND |
| VO1/VO2 | Channel separation | f = 1 kHz to 20 kHz | - / - / - | - | UNSUPPORTED_KIND |
| VCM | Common-mode voltage range | Vs = 5 V to maximum, TA = 25°C | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | Vs = 5 V to maximum, TA = -40°C to | - / - / - | - | NOT_TESTABLE_CONDITION |
| CMRR | Common-mode rejection ratio | Vs = 5 V to maximum; VCM = 0 V | 65 dB / 80 dB / - | - | SIM_ERROR |
| IB | Input bias current | Vo = 1.4 V | -20 nA / - / -250 nA | - | SIM_ERROR |
| IOS | Input offset current | Vo = 1.4 V, Non-V suffix device | - / 2 nA / 50 nA | - | SIM_ERROR |
| IOS | Input offset current | Vo = 1.4 V, V-suffix device | - / 2 nA / 50 nA | - | SIM_ERROR |
| IOS | Input offset current | Vo = 1.4 V, TA = -40°C to 125°C | - / - / 150 nA | - | SIM_ERROR |
| dlOS/dT | Input offset current drift | TA = -40°C to 125°C | - / - / - | - | UNSUPPORTED_KIND |
| en | Input voltage noise density | f = 1 kHz | - / - / - | - | SIM_ERROR |
| AOL | Open-loop voltage gain | Vs = 15 V; VO = 1 V to 11 V; RL ≥  | 87.96 dB / 100 dB / - | - | SIM_ERROR |
| AOL | Open-loop voltage gain | TA = -40°C to 125°C | 83.52 dB / - / - | - | SIM_ERROR |
| GBW | Gain bandwidth product | TA = 25°C | 700 kHz / - / - | - | SIM_ERROR |
| SR | Slew rate | G = +1, TA = 25°C | 0.3 V/us / - / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | Positive rail, RL ≥ 10 kΩ | - / - / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | Positive rail, Non-V suffix device | - / - / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | Positive rail, Non-V suffix device | 2 V / 3 V / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | Positive rail, V-suffix device, Vs | 6 V / 4 V / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | Positive rail, V-suffix device, Vs | 4 V / 5 V / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | Negative rail, Vs = 5 V; RL ≤ 10 k | - / 5 mV / 20 mV | - | SIM_ERROR |
| IO | Output current | Vs = 15 V; VO = 0 V; VID = 1 V, So | -20 mA / -30 mA / - | - | SIM_ERROR |
| IO | Output current | Vs = 15 V; VO = 0 V; VID = 1 V, TA | -10 mA / - / - | - | SIM_ERROR |
| IO | Output current | Vs = 15 V; VO = 15 V; VID = -1 V,  | 10 mA / 20 mA / - | - | SIM_ERROR |
| IO | Output current | Vs = 15 V; VO = 15 V; VID = -1 V,  | 5 mA / - / - | - | SIM_ERROR |
| IO | Output current | VID = -1 V; VO = 200 mV, Non-V suf | 30 uA / - / - | - | SIM_ERROR |
| Isc | Short-circuit current | Vs = 10 V; VO = Vs / 2 | - / - / - | - | SIM_ERROR |
| IQ | Quiescent current per amplifier | VO = 2.5 V; IO = 0 A, TA = -40°C t | - / 350 uA / 600 uA | - | SIM_ERROR |
| VOS | Input offset voltage | LM158, Vs = 5 V to 30 V; VC M = 0  | 3 mV / 5 mV / 7 mV | - | SIM_ERROR |
| VOS | Input offset voltage | LM158A, Vs = 5 V to 30 V; VC M = 0 | - / - / 2 mV | - | SIM_ERROR |
| dVOS/dT | Input offset voltage drift | LM158, TA = -55°C to 125°C | - / - / - | - | UNSUPPORTED_KIND |
| VOI/ VO2 | Channel separation | f = 1 kHz to 20 kHz | - / - / - | - | UNSUPPORTED_KIND |
| VCM | Common-mode voltage range | LM158, Vs = 5 V to 30 V | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | LM158, Vs = 5 V to 30 V, TA = -55° | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | LM158A, Vs = 30 V | - / - / - | - | NOT_TESTABLE_CONDITION |
| CMRR | Common-mode rejection ratio | Vs = 5 V to 30 V; VM = 0 V | 70 dB / 80 dB / - | - | SIM_ERROR |
| IB | Input bias current | LM158, VO = 1.4 V | -20 nA / -150 nA / - | - | SIM_ERROR |
| IB | Input bias current | LM158, TA = -55°C to 125°C | - / -300 nA / - | - | SIM_ERROR |
| IB | Input bias current | LM158A, VO = 1.4 V | -15 nA / -50 nA / - | - | SIM_ERROR |
| IB | Input bias current | LM158A, TA = -55°C to 125°C | - / -100 nA / - | - | SIM_ERROR |
| IOS | Input offset current | LM158, VO = 1.4 V | - / 2 nA / 30 nA | - | SIM_ERROR |
| IOS | Input offset current | LM158, TA = -55°C to 125°C | - / 100 nA / - | - | SIM_ERROR |
| IOS | Input offset current | LM158A, VO = 1.4 V | - / 2 nA / 10 nA | - | SIM_ERROR |
| IOS | Input offset current | LM158A, TA = -55°C to 125°C | - / 30 nA / - | - | SIM_ERROR |
| dlOS/dT | Input offset current drift | LM158 | - / - / - | - | UNSUPPORTED_KIND |
| AOL | Open-loop voltage gain | Vs = 15 V; VO = 1 V to 11 V; RL ≥  | 93.98 dB / 100 dB / - | - | SIM_ERROR |
| AOL | Open-loop voltage gain | TA = -55°C to 125°C | 87.96 dB / - / - | - | SIM_ERROR |
| GBW | Gain bandwidth product | LM158 | 700 kHz / - / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | Vs = 30 V; RL = 2 kΩ, TA = -55°C t | - / - / 4 V | - | SIM_ERROR |
| VO | Voltage output swing from rail | Vs = 5 V; RL ≤ 10 kΩ, TA = -55°C t | 5 mV / 20 mV / - | - | SIM_ERROR |
| IO | Output current | Vs = 15 V; VO = 0 V; VD = 1 V, TA  | -20 mA / -30 mA / - | - | SIM_ERROR |
| IO | Output current | Vs = 15 V; VO = 0 V; VD = 1 V, TA  | -60 mA / - / - | - | SIM_ERROR |
| IO | Output current | Vs = 15 V; VO = 15 V; VD = -1 V, T | 10 mA / 20 mA / - | - | SIM_ERROR |
| IO | Output current | Vid = -1 V; VO = 200 mV | 12 uA / 30 uA / - | - | SIM_ERROR |
| I_O | Quiescent current per amplifier | LM158, LM158A, TA = -55°C to 125°C | 350 uA / 600 uA / 350 uA | - | SIM_ERROR |
| I_O | Quiescent current per amplifier | LM158, LM158A, Vs = 30 V; Vo = 15  | - / - / - | - | SIM_ERROR |
| VOS Input offset voltage | VOS Input offset voltage | Vs = 5 V to 30 V; VC M = 0 V; VO = | - / 3 mV / 5 mV | - | SIM_ERROR |
| VOS Input offset voltage | VOS Input offset voltage | Vs = 5 V to 30 V; VC M = 0 V; VO = | 7 mV / - / - | - | SIM_ERROR |
| VOS Input offset voltage | VOS Input offset voltage | Vs = 5 V to 30 V; VC M = 0 V; VO = | - / 2 mV / 3 mV | - | SIM_ERROR |
| VOS Input offset voltage | VOS Input offset voltage | Vs = 5 V to 30 V; VC M = 0 V; VO = | 4 mV / - / - | - | SIM_ERROR |
| dVOS/dT | Input offset voltage drift | TA = -25C to 85C | - / - / - | - | UNSUPPORTED_KIND |
| dVOS/dT | Input offset voltage drift | TA = -25C to 85C | - / - / - | - | UNSUPPORTED_KIND |
| IB | Input bias current | VO = 1.4 V | -20 nA / -150 nA / - | - | SIM_ERROR |
| IB | Input bias current | VO = 1.4 V; TA = -25C to 85C | -300 nA / - / - | - | SIM_ERROR |
| IB | Input bias current | VO = 1.4 V | -15 nA / -80 nA / - | - | SIM_ERROR |
| IB | Input bias current | VO = 1.4 V; TA = -25C to 85C | -100 nA / - / - | - | SIM_ERROR |
| IOS | Input offset current | VO = 1.4 V | - / 2 nA / 30 nA | - | SIM_ERROR |
| IOS | Input offset current | VO = 1.4 V; TA = -25C to 85C | 100 nA / - / - | - | SIM_ERROR |
| IOS | Input offset current | VO = 1.4 V | - / 2 nA / 15 nA | - | SIM_ERROR |
| dlOS/dT | Input offset current drift |  | - / - / - | - | UNSUPPORTED_KIND |
| AOL | Open-loop voltage gain | TA = -25C to 85C | 87.96 dB / - / - | - | SIM_ERROR |
| GBW | Gain bandwidth product |  | 700 kHz / - / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | Vs = 30 V; RL = 2 kΩ; TA = -25C to | - / - / 4 V | - | SIM_ERROR |
| VO | Voltage output swing from rail | Vs = 30 V; RL ≥ 10 kΩ | - / - / 2 V | - | SIM_ERROR |
| VO | Voltage output swing from rail | Vs = 5 V; RL ≤ 10 kΩ; TA = -25C to | 5 mV / 20 mV / - | - | SIM_ERROR |
| IO | Output current Source | Vs = 15 V; VO = 0 V; VD = 1 V | -20 mA / -30 mA / - | - | SIM_ERROR |
| IO | Output current Source | Vs = 15 V; VO = 0 V; VD = 1 V; TA  | -60 mA / - / - | - | SIM_ERROR |
| IO | Output current Sink | Vs = 15 V; VO = 15 V; VD = -1 V | 10 mA / 20 mA / - | - | SIM_ERROR |
| IO | Output current Sink | Vs = 15 V; VO = 15 V; VD = -1 V; T | 5 mA / - / - | - | SIM_ERROR |
| I_SC Short-circuit current | I_SC Short-circuit current | Vs = 10 V; VO = Vs / 2 | -40 mA / -60 mA / - | - | SIM_ERROR |
| IQ | Quiescent current per amplifier | Vo = 2.5 V; IO = 0 A; TA = -25C to | - / 350 uA / 600 uA | - | SIM_ERROR |
| IQ | Quiescent current per amplifier | Vs = 30 V; VO = 15 V; IO = 0 A | - / 500 uA / 1 mA | - | SIM_ERROR |