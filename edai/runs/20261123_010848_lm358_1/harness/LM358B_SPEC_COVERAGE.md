# Specification coverage — LM358B

- Verification target rows (all): **155**
- Electrical (testable) rows: **154**
- Mapped to a deterministic fixture: **119**
- Actually measured: **0** → coverage **0.0 %**
- PDG Causal Gate Status: **PDG_STAGE0_TOPOLOGY**
- Pass among measured rows: **0.0 %** (0/3)
- Pass among unique parameter kinds: **0.0 %** (0/0)
- Sim errors 119 | not observed 0 | no fixture 0 | unsupported kind 27 | not testable 9

| Symbol | Name | Conditions | Limits (canonical) | Measured | Result |
|---|---|---|---|---|---|
| TA | Operating ambient temperature | LM358B, LM358BA | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| VOS | Input offset voltage | LM358B, TA = -40C to 85C | 300 uV / - / 3 mV | - | SIM_ERROR |
| VOS | Input offset voltage | LM358BA, TA = -40C to 85C | 300 uV / - / 3 mV | - | SIM_ERROR |
| VOS | Input offset voltage | LM358B, TA = -40C to 85C | 400 uV / - / - | - | SIM_ERROR |
| VOS | Input offset voltage | LM358BA, TA = -40C to 85C | 400 uV / - / - | - | SIM_ERROR |
| dVOS/dT | Input offset voltage drift | TA = -40C to 85C(1) | - / - / - | - | UNSUPPORTED_KIND |
| PSRR | Power supply rejection ratio | VS = 3 V to 36 V | - / 96.48 dB / - | - | SIM_ERROR |
| CMRR | Common-mode rejection ratio | (V-) ≤ VCM ≤ (V+) - 1.5 V, VS = 3  | - / 80 dB / - | - | SIM_ERROR |
| CMRR | Common-mode rejection ratio | (V-) ≤ VCM ≤ (V+) - 2.0 V, VS = 5  | - / 70.01 dB / - | - | SIM_ERROR |
| IB | Input bias current | TA = -40C to 85C(1) | -10 nA / -35 nA / - | - | SIM_ERROR |
| IOS | Input offset current | TA = -40C to 85C(1) | 500 pA / 4 nA / - | - | SIM_ERROR |
| dIOS/dT | Input offset current drift | TA = -40C to 85C | - / - / - | - | UNSUPPORTED_KIND |
| En | Input voltage noise | f = 0.1 to 10 Hz | - / - / - | - | UNSUPPORTED_KIND |
| en | Input voltage noise density | f = 1 kHz | - / - / - | - | SIM_ERROR |
| ZID | Differential input impedance |  | - / - / - | - | UNSUPPORTED_KIND |
| ZIC | Common-mode input impedance |  | - / - / - | - | UNSUPPORTED_KIND |
| AOL | Open-loop voltage gain | VS = 15 V; VO = 1 V to 11 V; RL ≥  | - / - / - | - | SIM_ERROR |
| GBW | Gain bandwidth product |  | 1.2 MHz / - / - | - | SIM_ERROR |
| SR | Slew rate | G = + 1 | 0.5 V/us / - / - | - | SIM_ERROR |
| Θm | Phase margin | G = + 1, RL = 10kΩ, CL = 20 pF | 56 deg / - / - | - | SIM_ERROR |
| tOR | Overload recovery time | VIN × gain > VS | - / - / - | - | UNSUPPORTED_KIND |
| ts | Settling time | VS = 5 V, 2-V step , G = +1, CL =  | - / - / - | - | UNSUPPORTED_KIND |
| THD+N | Total harmonic distortion + noise | G = + 1, f = 1 kHz, VO = 3.53 VRMS | - / - / - | - | UNSUPPORTED_KIND |
| VO | Voltage output swing from rail | IOUT = 50 µA | 1.35 V / 1.42 V / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | IOUT = 1 mA | 1.4 V / 1.48 V / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | IOUT = 5 mA(1) | 1.5 V / 1.61 V / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | IOUT = 50 µA | 100 mV / 150 mV / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | VS = 5 V, RL ≤ 10 kΩ connected to  | 750 mV / 1 V / - | - | SIM_ERROR |
| IO | Output current | VS = 15 V; VO = V–; VID = 1 V | -20 mA / -30 mA / - | - | SIM_ERROR |
| IO | Output current | VS = 15 V; VO = V+; VID = -1 V | -10 mA / -20 mA / - | - | SIM_ERROR |
| IO | Output current | VID = -1 V; VO = (V–) + 200 mV | 60 uA / 100 uA / - | - | SIM_ERROR |
| ISC | Short-circuit current | VS = 20 V, (V+) = 10 V, (V–) = -10 | -40 mA / -60 mA / - | - | SIM_ERROR |
| CLOAD | Capacitive load drive |  | - / - / - | - | UNSUPPORTED_KIND |
| RO | Open-loop output resistance | f = 1 MHz, IO = 0 A | - / - / - | - | UNSUPPORTED_KIND |
| IQ | Quiescent current per amplifier | VS = 5 V; IO = 0 A, TA = –40°C to  | 300 uA / 460 uA / - | - | SIM_ERROR |
| IQ | Quiescent current per amplifier | VS = 36 V; IO = 0 A, LM358, LM358A | 800 uA / - / - | - | SIM_ERROR |
| VOS | Input offset voltage | LM2904B, TA = –40°C to +125°C | 300 uV / - / 3 mV | - | SIM_ERROR |
| VOS | Input offset voltage | LM2904BA, TA = –40°C to +125°C | 2 mV / - / - | - | SIM_ERROR |
| dVOS/dT | Input offset voltage drift | TA = –40°C to +125°C(1) | - / - / - | - | UNSUPPORTED_KIND |
| PSRR | Power Supply Rejection Ratio | VS = (V+) – (V–) = 5 V - 36 V, VCM | - / 96.48 dB / - | - | SIM_ERROR |
| CMRR | Common-mode rejection ratio | (V–) ≤ VCM ≤ (V+) – 1.5 V, VS = 3  | - / 80 dB / - | - | SIM_ERROR |
| CMRR | Common-mode rejection ratio | (V–) ≤ VCM ≤ (V+) – 2.0 V, VS = 5  | - / 70.01 dB / - | - | SIM_ERROR |
| IB | Input bias current | TA = –40°C to +125°C(1) | -10 nA / -35 nA / - | - | SIM_ERROR |
| IOS | Input offset current | TA = –40°C to +125°C(1) | 500 pA / 4 nA / - | - | SIM_ERROR |
| dIOS/dT | Input offset current drift | TA = –40°C to +125°C | - / - / - | - | UNSUPPORTED_KIND |
| ts | Settling time | VS = 5 V, 2-V Step , G = +1, CL =  | - / - / - | - | UNSUPPORTED_KIND |
| VO | Voltage output swing from rail | Positive Rail (V+), IOUT = 50 µA | 1.35 V / 1.42 V / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | Positive Rail (V+), IOUT = 1 mA | 1.4 V / 1.48 V / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | Positive Rail (V+), IOUT = 5 mA(1) | 1.5 V / 1.61 V / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | Negative Rail (V-), IOUT = 50 µA | 100 mV / 150 mV / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | Negative Rail (V-), IOUT = 1 mA | 750 mV / 1 V / - | - | SIM_ERROR |
| IO | Output current | VS = 15 V; VO = V-; VID = 1 V, Sou | -20 mA / -30 mA / - | - | SIM_ERROR |
| IO | Output current | VS = 15 V; VO = V+; VID = -1 V, Si | -10 mA / -20 mA / - | - | SIM_ERROR |
| ISC | Short-circuit current | VID = -1 V; VO = (V-) + 200 mV | 60 uA / 100 uA / - | - | SIM_ERROR |
| IQ | Quiescent current per amplifier | VS = 36 V; IO = 0 A, TA = –40°C to | 800 uA / - / - | - | SIM_ERROR |
| VOS | Offset Voltage | VS = 5 V to 30 V; VC M = 0 V; VO = | 3 mV / 7 mV / 11 mV | - | SIM_ERROR |
| dVOS/dT | Input offset voltage drift | LM358, TA = 0°C to 70°C | - / - / - | - | UNSUPPORTED_KIND |
| dVOS/dT | Input offset voltage drift | LM358A, TA = 0°C to 70°C | - / - / - | - | UNSUPPORTED_KIND |
| PSRR | Input offset voltage vs power supply ( | VS = 5 V to 30 V | - / - / - | - | SIM_ERROR |
| VO1/ VO2 | Channel separation | f = 1 kHz to 20 kHz | - / - / - | - | UNSUPPORTED_KIND |
| VCM | Common-mode voltage range | VS = 5 V to 30 V; LM358, TA = 0°C  | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | VS = 30 V; LM358, TA = 0°C to 70°C | - / - / - | - | NOT_TESTABLE_CONDITION |
| CMRR | Common-mode rejection ratio | VS = 5 V to 30 V; VCM = 0 V | 65 dB / 80 dB / - | - | SIM_ERROR |
| IB | Input bias current | VO = 1.4 V; TA = 0°C to 70°C | -20 nA / -250 nA / -500 nA | - | SIM_ERROR |
| IB | Input bias current | VO = 1.4 V; TA = 0°C to 70°C | -15 nA / -100 nA / -200 nA | - | SIM_ERROR |
| IOS | Input offset current | VO = 1.4 V; TA = 0°C to 70°C | 2 nA / 50 nA / 150 nA | - | SIM_ERROR |
| IOS | Input offset current | VO = 1.4 V; TA = 0°C to 70°C | 2 nA / 30 nA / 75 nA | - | SIM_ERROR |
| dIOS/dT | Input offset current drift | LM358A, TA = 0°C to 70°C | - / - / - | - | UNSUPPORTED_KIND |
| AOL | Open-loop voltage gain | VS = 15 V; VO = 1 V to 11 V; RL ≥  | 87.96 dB / 100 dB / - | - | SIM_ERROR |
| GBW | Gain bandwidth product | TA = 0°C to 70°C | 700 kHz / - / - | - | SIM_ERROR |
| SR | Slew rate | G = +1 | 0.3 V/us / - / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | Positive rail; VS = 30 V; RL = 2 k | 4 V / - / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | VS = 30 V; RL ≥ 10 kΩ | 2 V / 3 V / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | VS = 5 V; RL ≥ 2 kΩ | 1.5 V / - / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | Negative rail; VS = 5 V; RL ≤ 10 k | 5 mV / 20 mV / - | - | SIM_ERROR |
| IO | Output current | VS = 15 V; VO = 0 V; VID = 1 V; TA | -20 mA / - / -30 mA | - | SIM_ERROR |
| IO | Output current | LM358A, TA = 0°C to 70°C | -60 mA / - / -10 mA | - | SIM_ERROR |
| IO | Output current | VID = –1 V; VO = 200 mV; TA = 0°C  | 5 uA / 12 uA / 30 uA | - | SIM_ERROR |
| ISC | Short-circuit current | VS = 10 V; VO = VS / 2 | 40 mA / - / 60 mA | - | SIM_ERROR |
| IQ | Quiescent current per amplifier | VO = 2.5 V; IO = 0 A; TA = 0°C to  | 350 uA / 600 uA / - | - | SIM_ERROR |
| IQ | Quiescent current per amplifier | VS = 30 V; VO = 15 V; IO = 0 A | 500 uA / 1 mA / - | - | SIM_ERROR |
| VOS | Input offset voltage | VS = 5 V to maximum; VC M = 0 V; V | 3 mV / 7 mV / - | - | SIM_ERROR |
| VOS | Input offset voltage | TA = -40C to 125C; A-suffix device | 1 mV / 2 mV / - | - | SIM_ERROR |
| VOS | Input offset voltage | TA = -40C to 125C | 4 mV / - / - | - | SIM_ERROR |
| dVOS/dT | Input offset voltage drift | TA = -40C to 125C | - / - / - | - | UNSUPPORTED_KIND |
| VCM | Common-mode voltage range | VS = 5 V to maximum | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | TA = -40C to 125C | - / - / - | - | NOT_TESTABLE_CONDITION |
| CMRR | Common-mode rejection ratio | VS = 5 V to maximum; VCM = 0 V | 65 dB / 80 dB / - | - | SIM_ERROR |
| IB | Input bias current | VO = 1.4 V; TA = -40C to 125C | -20 nA / -250 nA / - | - | SIM_ERROR |
| IOS | Input offset current | VO = 1.4 V; Non-V suffix device; T | 2 nA / 50 nA / - | - | SIM_ERROR |
| IOS | Input offset current | VO = 1.4 V; V-suffix device; TA =  | 2 nA / 50 nA / - | - | SIM_ERROR |
| dIOS/dT | Input offset current drift | TA = -40C to 125C | - / - / - | - | UNSUPPORTED_KIND |
| AOL | Open-loop voltage gain | TA = -40C to 125C | - / - / - | - | SIM_ERROR |
| GBW | Gain bandwidth product |  | 700 kHz / - / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | RL ≥ 10 kΩ; Non-V suffix device; V | - / - / - | - | SIM_ERROR |
| VO | Voltage output swing from rail | RL ≥ 10 kΩ; V-suffix device; VS =  | - / - / 2 V | - | SIM_ERROR |
| VO | Voltage output swing from rail | RL = 2 kΩ; V-suffix device; VS = m | - / - / 6 V | - | SIM_ERROR |
| VO | Voltage output swing from rail | RL ≥ 10 kΩ; V-suffix device; VS =  | - / - / 4 V | - | SIM_ERROR |
| VO | Voltage output swing from rail | VS = 5 V; RL ≤ 10 kΩ; TA = -40C to | 5 mV / 20 mV / - | - | SIM_ERROR |
| IO | Output current | VS = 15 V; VO = 0 V; VID = 1 V; TA | -20 mA / -30 mA / - | - | SIM_ERROR |
| IO | Output current | VS = 15 V; VO = 15 V; VID = -1 V;  | -10 mA / - / - | - | SIM_ERROR |
| IO | Output current | VID = -1 V; VO = 200 mV; Non-V suf | 30 uA / - / - | - | SIM_ERROR |
| IO | Output current | VID = -1 V; VO = 200 mV; V-suffix  | 12 uA / - / - | - | SIM_ERROR |
| ISC | Short-circuit current |  | - / - / - | - | SIM_ERROR |
| VOS | Input offset voltage | LM158, VS = 5 V to 30 V; VC M = 0  | 3 mV / 5 mV / - | - | SIM_ERROR |
| VOS | Input offset voltage | LM158A, VS = 5 V to 30 V; VC M = 0 | 7 mV / - / - | - | SIM_ERROR |
| dVOS/dT | Input offset voltage drift | LM158A, TA = –55°C to 125°C | - / - / - | - | UNSUPPORTED_KIND |
| dVOS/dT | Input offset voltage drift | LM158, TA = –55°C to 125°C | - / - / - | - | UNSUPPORTED_KIND |
| VCM | Common-mode voltage range | LM158, VS = 5 V to 30 V, TA = –55° | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | LM158A, VS = 5 V to 30 V, TA = –55 | - / - / - | - | NOT_TESTABLE_CONDITION |
| CMRR | Common-mode rejection ratio | VS = 5 V to 30 V; VCM = 0 V | 70 dB / 80 dB / - | - | SIM_ERROR |
| IB | Input bias current | LM158, VO = 1.4 V, TA = –55°C to 1 | -20 nA / -150 nA / - | - | SIM_ERROR |
| IB | Input bias current | LM158A, VO = 1.4 V, TA = –55°C to  | -300 nA / - / - | - | SIM_ERROR |
| IOS | Input offset current | LM158, VO = 1.4 V, TA = –55°C to 1 | 2 nA / 30 nA / - | - | SIM_ERROR |
| IOS | Input offset current | LM158A, VO = 1.4 V, TA = –55°C to  | 2 nA / 10 nA / - | - | SIM_ERROR |
| dIOS/dT | Input offset current drift | LM158A, TA = –55°C to 125°C | - / - / - | - | UNSUPPORTED_KIND |
| AOL | Open-loop voltage gain | VS = 15 V; VO = 1 V to 11 V; RL ≥  | 93.98 dB / 100 dB / - | - | SIM_ERROR |
| GBW | Gain bandwidth product | N/A | 700 kHz / - / - | - | SIM_ERROR |
| VO | Voltage output swing from rail (Positi | VS = 30 V; RL = 2 kΩ, TA = –55°C t | 4 V / - / - | - | SIM_ERROR |
| VO | Voltage output swing from rail (Negati | VS = 5 V; RL ≤ 10 kΩ, TA = –55°C t | 5 mV / - / 20 mV | - | SIM_ERROR |
| IO | Output current (Source) | VS = 15 V; VO = 0 V; VID = 1 V | -20 mA / -30 mA / - | - | SIM_ERROR |
| IO | Output current (Source) | LM158A, TA = –55°C to 125°C | -60 mA / - / - | - | SIM_ERROR |
| IO | Output current (Sink) | VS = 15 V; VO = 15 V; VID = –1 V,  | 10 mA / 20 mA / - | - | SIM_ERROR |
| IO | Output current (Sink) | VID = –1 V; VO = 200 mV | 5 uA / - / - | - | SIM_ERROR |
| ISC | Short-circuit current | VS = 10 V; VO = VS / 2, LM158, LM1 | -40 mA / -60 mA / - | - | SIM_ERROR |
| IQ | Quiescent current per amplifier | VS = 5 V, TA = 25°C (unless otherw | 350 uA / 600 uA / - | - | SIM_ERROR |
| IQ | Quiescent current per amplifier | VS = 30 V; VO = 15 V; IO = 0 A, LM | 500 uA / - / 1 mA | - | SIM_ERROR |
| VOS | Input offset voltage | LM258, VS = 5 V to 30 V; VC M = 0  | 3 mV / 5 mV / - | - | SIM_ERROR |
| VOS | Input offset voltage | LM258A, VS = 5 V to 30 V; VC M = 0 | 2 mV / 3 mV / - | - | SIM_ERROR |
| dVOS/dT | Input offset voltage drift | LM258, TA = –25°C to 85°C | - / - / - | - | UNSUPPORTED_KIND |
| dVOS/dT | Input offset voltage drift | LM258A, TA = –25°C to 85°C | - / - / - | - | UNSUPPORTED_KIND |
| PSRR | Input offset voltage vs power supply ( | VS = 5 V to 30 V, TA = 25°C | - / - / - | - | SIM_ERROR |
| VO1/ VO2 | Channel separation | f = 1 kHz to 20 kHz, TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| VCM | Common-mode voltage range | LM258, VS = 5 V to 30 V, TA = –25° | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | LM258A, VS = 5 V to 30 V, TA = –25 | - / - / - | - | NOT_TESTABLE_CONDITION |
| CMRR | Common-mode rejection ratio | VS = 5 V to 30 V; VCM = 0 V, TA =  | 70 dB / 80 dB / - | - | SIM_ERROR |
| IB | Input bias current | LM258, VO = 1.4 V, TA = –25°C to 8 | -20 nA / -150 nA / - | - | SIM_ERROR |
| IB | Input bias current | LM258A, VO = 1.4 V, TA = –25°C to  | -300 nA / - / - | - | SIM_ERROR |
| IOS | Input offset current | LM258, VO = 1.4 V, TA = –25°C to 8 | 2 nA / 30 nA / - | - | SIM_ERROR |
| IOS | Input offset current | LM258A, VO = 1.4 V, TA = –25°C to  | 2 nA / 15 nA / - | - | SIM_ERROR |
| dIOS/dT | Input offset current drift | LM258, TA = –25°C to 85°C | - / - / - | - | UNSUPPORTED_KIND |
| dIOS/dT | Input offset current drift | LM258A, TA = –25°C to 85°C | - / - / - | - | UNSUPPORTED_KIND |
| en | Input voltage noise density | f = 1 kHz, TA = 25°C | - / - / - | - | SIM_ERROR |
| GBW | Gain bandwidth product | TA = 25°C | - / 700 kHz / - | - | SIM_ERROR |
| SR | Slew rate | G = +1, TA = 25°C | - / 0.3 V/us / - | - | SIM_ERROR |
| VO | Voltage output swing from rail (Positi | VS = 30 V; RL = 2 kΩ, TA = –25°C t | 4 V / - / - | - | SIM_ERROR |
| VO | Voltage output swing from rail (Positi | VS = 30 V; RL ≥ 10 kΩ, TA = –25°C  | 2 V / 3 V / - | - | SIM_ERROR |
| VO | Voltage output swing from rail (Negati | VS = 5 V; RL ≥ 2 kΩ, TA = –25°C to | 1.5 V / - / - | - | SIM_ERROR |
| VO | Voltage output swing from rail (Negati | VS = 5 V; RL ≤ 10 kΩ, TA = –25°C t | 5 mV / 20 mV / - | - | SIM_ERROR |
| IO | Output current (Source) | VS = 15 V; VO = 0 V; VID = 1 V, TA | -20 mA / -30 mA / - | - | SIM_ERROR |
| IO | Output current (Source) | LM258A, VS = 15 V; VO = 0 V; VID = | -60 mA / - / - | - | SIM_ERROR |
| IO | Output current (Sink) | VID = –1 V; VO = 200 mV, TA = –25° | 5 uA / - / - | - | SIM_ERROR |
| ISC | Short-circuit current | VS = 10 V; VO = VS / 2, TA = 25°C | -40 mA / - / -60 mA | - | SIM_ERROR |
| IQ | Quiescent current per amplifier | VO = 2.5 V; IO = 0 A, TA = –25°C t | 350 uA / - / 600 uA | - | SIM_ERROR |
| IQ | Quiescent current per amplifier | VS = 30 V; VO = 15 V; IO = 0 A, TA | 500 uA / - / 1 mA | - | SIM_ERROR |