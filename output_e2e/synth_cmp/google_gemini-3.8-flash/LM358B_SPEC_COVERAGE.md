# Specification coverage — LM358B

- Verification target rows (all): **260**
- Electrical (testable) rows: **195**
- Mapped to a deterministic fixture: **152**
- Actually measured: **90** → coverage **59.2 %**
- Pass among measured: **33.3 %** (30/90)
- Sim errors 43 | not observed 14 | no fixture 0 | unsupported kind 30 | not testable 78

| Symbol | Name | Conditions | Limits (canonical) | Measured | Result |
|---|---|---|---|---|---|
| VS | Supply voltage | LM358B, LM358BA, LM2904B, LM2904BA | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VS | Supply voltage | LM158, LM258, LM358, LM158A, LM258 | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VS | Supply voltage | LM2904 | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VID | Differential input voltage | LM358B, LM358BA, LM2904B, LM2904BA | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VID | Differential input voltage | LM2904 | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VI | Input voltage | LM358B, LM358BA, LM2904B, LM2904BA | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VI | Input voltage | LM158, LM258, LM358, LM158A, LM258 | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VI | Input voltage | LM2904, Either input | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| tSC | Duration of output short circuit | One amplifier to ground at (or bel | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| TA | Operating ambient temperature | LM158, LM158A | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| TA | Operating ambient temperature | LM258, LM258A | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| TA | Operating ambient temperature | LM358B, LM358BA | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| TA | Operating ambient temperature | LM358, LM358A | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| TA | Operating ambient temperature | LM2904B, LM2904BA, LM2904, LM2904V | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| TJ | Operating virtual-junction temperature | All variants | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| Tstg | Storage temperature | All variants | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| V(ESD) | Human-body model (HBM) electrostatic d | LM358B, LM358BA, LM2904B, LM2904BA | - / - / - | - | NOT_TESTABLE_ESD |
| V(ESD) | Charged-device model (CDM) electrostat | LM358B, LM358BA, LM2904B, LM2904BA | - / - / - | - | NOT_TESTABLE_ESD |
| V(ESD) | Human-body model (HBM) electrostatic d | LM158, LM258, LM358, LM158A, LM258 | - / - / - | - | NOT_TESTABLE_ESD |
| V(ESD) | Charged-device model (CDM) electrostat | LM158, LM258, LM358, LM158A, LM258 | - / - / - | - | NOT_TESTABLE_ESD |
| VS | Supply voltage, VS= ([V+] – [V–]) | LM358B, LM358BA, LM2904B, LM2904BA | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| VS | Supply voltage, VS= ([V+] – [V–]) | LM158, LM258, LM358, LM158A, LM258 | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| VS | Supply voltage, VS= ([V+] – [V–]) | LM2904 | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| VCM | Common-mode voltage | V– to V+ – 2 | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating ambient temperature | LM358B, LM358BA | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating ambient temperature | LM2904B, LM2904BA, LM2904, LM2904V | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating ambient temperature | LM358, LM358A | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating ambient temperature | LM258, LM258A | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| TA | Operating ambient temperature | LM158, LM158A | - / - / - | - | NOT_TESTABLE_RECOMMENDED |
| RθJA | Junction-to-ambient thermal resistance | D (SOIC) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJA | Junction-to-ambient thermal resistance | DGK (VSSOP) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJA | Junction-to-ambient thermal resistance | P (PDIP) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJA | Junction-to-ambient thermal resistance | PS (SO) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJA | Junction-to-ambient thermal resistance | PW (TSSOP) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJA | Junction-to-ambient thermal resistance | DDF (SOT-23) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJA | Junction-to-ambient thermal resistance | FK (LCCC) 20 PINS / JG (CDIP) 8 PI | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJC(top) | Junction-to-case (top) thermal resista | D (SOIC) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJC(top) | Junction-to-case (top) thermal resista | DGK (VSSOP) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJC(top) | Junction-to-case (top) thermal resista | P (PDIP) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJC(top) | Junction-to-case (top) thermal resista | PS (SO) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJC(top) | Junction-to-case (top) thermal resista | PW (TSSOP) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJC(top) | Junction-to-case (top) thermal resista | DDF (SOT-23) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJC(top) | Junction-to-case (top) thermal resista | FK (LCCC) 20 PINS / JG (CDIP) 8 PI | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJB | Junction-to-board thermal resistance | D (SOIC) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJB | Junction-to-board thermal resistance | DGK (VSSOP) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJB | Junction-to-board thermal resistance | P (PDIP) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJB | Junction-to-board thermal resistance | PS (SO) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJB | Junction-to-board thermal resistance | PW (TSSOP) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJB | Junction-to-board thermal resistance | DDF (SOT-23) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJB | Junction-to-board thermal resistance | FK (LCCC) 20 PINS / JG (CDIP) 8 PI | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJT | Junction-to-top characterization param | D (SOIC) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJT | Junction-to-top characterization param | DGK (VSSOP) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJT | Junction-to-top characterization param | P (PDIP) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJT | Junction-to-top characterization param | PS (SO) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJT | Junction-to-top characterization param | PW (TSSOP) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJT | Junction-to-top characterization param | DDF (SOT-23) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJT | Junction-to-top characterization param | FK (LCCC) 20 PINS / JG (CDIP) 8 PI | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJB | Junction-to-board characterization par | D (SOIC) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJB | Junction-to-board characterization par | DGK (VSSOP) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJB | Junction-to-board characterization par | P (PDIP) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJB | Junction-to-board characterization par | PS (SO) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJB | Junction-to-board characterization par | PW (TSSOP) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJB | Junction-to-board characterization par | DDF (SOT-23) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJB | Junction-to-board characterization par | FK (LCCC) 20 PINS / JG (CDIP) 8 PI | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJC(bot) | Junction-to-case (bottom) thermal resi | D (SOIC) 8 PINS | - / - / - | - | NOT_TESTABLE_THERMAL |
| VOS | Input offset voltage | LM358B, VS = 5 V to 36 V, TA = 25C | - / 300 uV / 3 mV | 2.498 V | FAIL |
| VOS | Input offset voltage | LM358B, TA = -40C to +85C | - / - / 4 mV | 2.498 V | FAIL |
| VOS | Input offset voltage | LM358BA, VS = 5 V to 36 V, TA = 25 | - / - / 2 mV | 2.498 V | FAIL |
| VOS | Input offset voltage | LM358BA, TA = -40C to +85C | - / - / 2.5 mV | 2.498 V | FAIL |
| dVOS/dT | Input offset voltage drift | TA = -40C to +85C | - / - / - | - | UNSUPPORTED_KIND |
| PSRR | Power supply rejection ratio | VS = 5 V to 36 V, TA = 25C | 96.48 dB / 114 dB / - | - | NOT_OBSERVED |
| Channel separation, dc | Channel separation, dc | f = 1 kHz to 20 kHz | - / - / - | - | UNSUPPORTED_KIND |
| VCM | Common-mode voltage range | VS = 3 V to 36 V, (V-) to (V+) - 1 | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | VS = 5 V to 36 V, TA = -40C to +85 | - / - / - | - | NOT_TESTABLE_CONDITION |
| CMRR | Common-mode rejection ratio | (V-) <= VCM <= (V+) - 1.5 V, VS =  | 80 dB / 93.98 dB / - | -316 dB | FAIL |
| CMRR | Common-mode rejection ratio | (V-) <= VCM <= (V+) - 2.0 V, VS =  | 70.01 dB / 92.04 dB / - | -316 dB | FAIL |
| IB | Input bias current | VS = 5 V to 36 V, TA = 25C | - / -10 nA / -35 nA | 9.437 nA | PASS |
| IB | Input bias current | TA = -40C to +85C | - / - / -50 nA | 9.437 nA | PASS |
| IOS | Input offset current | VS = 5 V to 36 V, TA = 25C | - / 500 pA / 4 nA | 499.6 nA | FAIL |
| IOS | Input offset current | TA = -40C to +85C | - / - / 5 nA | 499.6 nA | FAIL |
| dIOS/dT | Input offset current drift | TA = -40C to +85C | - / - / - | - | UNSUPPORTED_KIND |
| En | Input voltage noise | f = 0.1 to 10 Hz | - / - / - | - | UNSUPPORTED_KIND |
| en | Input voltage noise density | f = 1 kHz | - / 40 nV/rtHz / - | 1.34e+04 nV/rtHz | FAIL_TYP |
| ZID | Differential input impedance | VS = 5 V to 36 V, TA = 25C | - / - / - | - | UNSUPPORTED_KIND |
| ZIC | Common-mode input impedance | VS = 5 V to 36 V, TA = 25C | - / - / - | - | UNSUPPORTED_KIND |
| AOL | Open-loop voltage gain | VS = 15 V; VO = 1 V to 11 V; RL >= | 96.9 dB / 102.9 dB / - | -471.9 dB | FAIL |
| AOL | Open-loop voltage gain | VS = 15 V; VO = 1 V to 11 V; RL >= | 90.88 dB / - / - | -471.9 dB | FAIL |
| GBW | Gain bandwidth product | VS = 5 V to 36 V, TA = 25C | - / 1.2 MHz / - | - | NOT_OBSERVED |
| SR | Slew rate | G = +1 | - / 0.5 V/us / - | - | NOT_OBSERVED |
| Theta_m | Phase margin | G = +1, RL = 10 kOhm, CL = 20 pF | - / 56 deg / - | - | NOT_OBSERVED |
| tOR | Overload recovery time | VIN x gain > VS | - / - / - | - | UNSUPPORTED_KIND |
| ts | Settling time | To 0.1%, VS = 5 V, 2-V step, G = + | - / - / - | - | UNSUPPORTED_KIND |
| THD+N | Total harmonic distortion + noise | G = +1, f = 1 kHz, VO = 3.53 VRMS, | - / - / - | - | UNSUPPORTED_KIND |
| VO | Voltage output swing from rail (Positi | IOUT = 50 uA | - / 1.35 V / 1.42 V | 5 V | FAIL |
| VO | Voltage output swing from rail (Positi | IOUT = 1 mA | - / 1.4 V / 1.48 V | 4.99 V | FAIL |
| VO | Voltage output swing from rail (Positi | IOUT = 5 mA | - / 1.5 V / 1.61 V | 4.951 V | FAIL |
| VO | Voltage output swing from rail (Negati | IOUT = 50 uA | - / 100 mV / 150 mV | 5 V | FAIL |
| VO | Voltage output swing from rail (Negati | IOUT = 1 mA | - / 750 mV / 1 V | 4.99 V | FAIL |
| VO | Voltage output swing from rail | VS = 5 V, RL <= 10 kOhm connected  | - / 5 mV / 20 mV | 2.497 mV | PASS |
| IO | Output current (Source) | VS = 15 V; VO = V-; VID = 1 V | -20 mA / -30 mA / - | 0 A | FAIL |
| IO | Output current (Source) | VS = 15 V; VO = V-; VID = 1 V, TA  | -10 mA / - / - | 0 A | FAIL |
| IO | Output current (Sink) | VS = 15 V; VO = V+; VID = -1 V | 10 mA / 20 mA / - | 30.15 mA | PASS |
| IO | Output current (Sink) | VS = 15 V; VO = V+; VID = -1 V, TA | 5 mA / - / - | 30.15 mA | PASS |
| IO | Output current (Sink) | VID = -1 V; VO = (V-) + 200 mV | 60 uA / 100 uA / - | 20 mA | PASS |
| ISC | Short-circuit current | VS = 20 V, (V+) = 10 V, (V-) = -10 | - / 40 mA / 60 mA | 30.1 mA | PASS |
| CLOAD | Capacitive load drive | VS = 5 V to 36 V, TA = 25C | - / - / - | - | UNSUPPORTED_KIND |
| RO | Open-loop output resistance | f = 1 MHz, IO = 0 A | - / - / - | - | UNSUPPORTED_KIND |
| IQ | Quiescent current per amplifier | LM358B, LM358BA, VS = 5 V, IO = 0  | - / 300 uA / 460 uA | 310 uA | PASS |
| IQ | Quiescent current per amplifier | LM358B, LM358BA, VS = 36 V, IO = 0 | - / - / 800 uA | 620 uA | PASS |
| VOS | Input offset voltage | LM2904B, VS = (V+) – (V–) = 5 V -  | - / 300 uV / 3 mV | 2.498 V | FAIL |
| VOS | Input offset voltage | LM2904B, TA = –40°C to +125°C | - / - / 4 mV | 2.498 V | FAIL |
| VOS | Input offset voltage | LM2904BA, VS = (V+) – (V–) = 5 V - | - / - / 2 mV | 2.498 V | FAIL |
| VOS | Input offset voltage | LM2904BA, TA = –40°C to +125°C | - / - / 3 mV | 2.498 V | FAIL |
| dVOS/dT | Input offset voltage drift | TA = –40°C to +125°C | - / - / - | - | UNSUPPORTED_KIND |
| PSRR | Power Supply Rejection Ratio | VS = (V+) – (V–) = 5 V - 36 V (±2. | 96.48 dB / 114 dB / - | - | NOT_OBSERVED |
| VCM | Common-mode voltage range | VS = 3 V to 36 V, (V–) to (V+) – 1 | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | VS = 5 V to 36 V, TA = –40°C to +1 | - / - / - | - | NOT_TESTABLE_CONDITION |
| CMRR | Common-mode rejection ratio | (V–) ≤ VCM ≤ (V+) – 1.5 V, VS = 3  | 80 dB / 93.98 dB / - | -316 dB | FAIL |
| CMRR | Common-mode rejection ratio | (V–) ≤ VCM ≤ (V+) – 2.0 V, VS = 5  | 70.01 dB / 92.04 dB / - | -316 dB | FAIL |
| IB | Input bias current | VS = (V+) – (V–) = 5 V - 36 V (±2. | - / -10 nA / -35 nA | 9.437 nA | PASS |
| IB | Input bias current | TA = –40°C to +125°C | - / - / -50 nA | 9.437 nA | PASS |
| IOS | Input offset current | VS = (V+) – (V–) = 5 V - 36 V (±2. | - / 500 pA / 4 nA | 499.6 nA | FAIL |
| IOS | Input offset current | TA = –40°C to +125°C | - / - / 5 nA | 499.6 nA | FAIL |
| dIOS/dT | Input offset current drift | TA = –40°C to +125°C | - / - / - | - | UNSUPPORTED_KIND |
| ZID | Differential | VS = (V+) – (V–) = 5 V - 36 V (±2. | - / - / - | - | UNSUPPORTED_KIND |
| ZIC | Common-mode | VS = (V+) – (V–) = 5 V - 36 V (±2. | - / - / - | - | UNSUPPORTED_KIND |
| AOL | Open-loop voltage gain | VS = 15 V; VO = 1 V to 11 V; RL ≥  | 96.9 dB / 102.9 dB / - | -471.9 dB | FAIL |
| AOL | Open-loop voltage gain | TA = –40°C to +125°C | 90.88 dB / - / - | -471.9 dB | FAIL |
| GBW | Gain bandwidth product | VS = (V+) – (V–) = 5 V - 36 V (±2. | - / 1.2 MHz / - | - | NOT_OBSERVED |
| SR | Slew rate | G = + 1 | - / 0.5 V/us / - | - | NOT_OBSERVED |
| Θm | Phase margin | G = + 1, RL = 10kΩ, CL = 20 pF | - / 56 deg / - | - | NOT_OBSERVED |
| tOR | Overload recovery time | VIN × gain > VS | - / - / - | - | UNSUPPORTED_KIND |
| ts | Settling time | To 0.1%, VS = 5 V, 2-V Step , G =  | - / - / - | - | UNSUPPORTED_KIND |
| THD+N | Total harmonic distortion + noise | G = + 1, f = 1 kHz, VO = 3.53 VRMS | - / - / - | - | UNSUPPORTED_KIND |
| VO | Voltage output swing from rail | Positive Rail (V+), IOUT = 50 µA | - / 1.35 V / 1.42 V | 5 V | FAIL |
| VO | Voltage output swing from rail | Positive Rail (V+), IOUT = 1 mA | - / 1.4 V / 1.48 V | 4.99 V | FAIL |
| VO | Voltage output swing from rail | Positive Rail (V+), IOUT = 5 mA | - / 1.5 V / 1.61 V | 4.951 V | FAIL |
| VO | Voltage output swing from rail | Negative Rail (V-), IOUT = 50 µA | - / 100 mV / 150 mV | 499.9 uV | PASS |
| VO | Voltage output swing from rail | Negative Rail (V-), IOUT = 1 mA | - / 750 mV / 1 V | 9.959 mV | PASS |
| VO | Voltage output swing from rail | VS = 5 V, RL ≤ 10 kΩ connected to  | - / 5 mV / 20 mV | 2.497 mV | PASS |
| IO | Output current | Source, VS = 15 V; VO = V-; VID =  | -20 mA / -30 mA / - | 0 A | FAIL |
| IO | Output current | Source, TA = –40°C to +125°C | -10 mA / - / - | 30.02 mA | PASS |
| IO | Output current | Sink, VS = 15 V; VO = V+; VID = -1 | 10 mA / 20 mA / - | 30.15 mA | PASS |
| IO | Output current | Sink, TA = –40°C to +125°C | 5 mA / - / - | 30.02 mA | PASS |
| CLOAD | Capacitive load drive | VS = (V+) – (V–) = 5 V - 36 V (±2. | - / - / - | - | UNSUPPORTED_KIND |
| IQ | Quiescent current per amplifier | VS = 5 V; IO = 0 A, TA = –40°C to  | 300 uA / - / 460 uA | 310 uA | PASS |
| IQ | Quiescent current per amplifier | VS = 36 V; IO = 0 A, TA = 25°C, VC | - / 800 uA / - | 620 uA | PASS_TYP |
| VOS | Input offset voltage | VS = 5 V to 30 V; VC = 0 V; VO = 1 | - / 3 mV / 7 mV | 2.498 V | FAIL |
| VOS | Input offset voltage | VS = 5 V to 30 V; VC = 0 V; VO = 1 | - / - / 9 mV | 2.498 V | FAIL |
| VOS | Input offset voltage | VS = 5 V to 30 V; VC = 0 V; VO = 1 | - / 2 mV / 3 mV | 2.498 V | FAIL |
| VOS | Input offset voltage | VS = 5 V to 30 V; VC = 0 V; VO = 1 | - / - / 5 mV | 2.498 V | FAIL |
| VOS | Input offset voltage | TA = 0°C to 70°C, LM358 | - / 7 mV / - | 2.498 V | FAIL_TYP |
| dVOS/dT | Input offset voltage drift | TA = 0°C to 70°C, LM358A | - / - / - | - | UNSUPPORTED_KIND |
| PSRR | Input offset voltage vs power supply ( | VS = 5 V to 30 V | - / - / - | 2.498 V | NO_NUMERIC_LIMIT |
| VO1/VO2 | Channel separation | f = 1 kHz to 20 kHz | - / - / - | - | UNSUPPORTED_KIND |
| VCM | Common-mode voltage range | VS = 5 V to 30 V, LM358 | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | VS = 30 V, LM358A | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | VS = 5 V to 30 V, TA = 0°C to 70°C | - / - / - | - | NOT_TESTABLE_CONDITION |
| CMRR | Common-mode rejection ratio | VS = 5 V to 30 V; VCM = 0 V | 65 dB / 80 dB / - | -316 dB | FAIL |
| IB | Input bias current | VO = 1.4 V, LM358 | - / -20 nA / -250 nA | - | SIM_ERROR |
| IB | Input bias current | VO = 1.4 V, TA = 0°C to 70°C, LM35 | - / - / -500 nA | - | SIM_ERROR |
| IB | Input bias current | VO = 1.4 V, LM358A | - / -15 nA / -100 nA | - | SIM_ERROR |
| IB | Input bias current | VO = 1.4 V, TA = 0°C to 70°C, LM35 | - / - / -200 nA | - | SIM_ERROR |
| IOS | Input offset current | VO = 1.4 V, LM358 | - / 2 nA / 50 nA | - | SIM_ERROR |
| IOS | Input offset current | VO = 1.4 V, TA = 0°C to 70°C, LM35 | - / - / 150 nA | - | SIM_ERROR |
| IOS | Input offset current | VO = 1.4 V, LM358A | - / 2 nA / 30 nA | - | SIM_ERROR |
| IOS | Input offset current | VO = 1.4 V, TA = 0°C to 70°C, LM35 | - / - / 75 nA | - | SIM_ERROR |
| dIOS/dT | Input offset current drift | TA = 0°C to 70°C, LM358A | - / - / - | - | UNSUPPORTED_KIND |
| AOL | Open-loop voltage gain | VS = 15 V; VO = 1 V to 11 V; RL ≥  | 87.96 dB / 100 dB / - | -472 dB | FAIL |
| AOL | Open-loop voltage gain | VS = 15 V; VO = 1 V to 11 V; RL ≥  | 83.52 dB / - / - | -472 dB | FAIL |
| GBW | Gain bandwidth product |  | - / 700 kHz / - | - | NOT_OBSERVED |
| SR | Slew rate | G = +1 | - / 0.3 V/us / - | - | NOT_OBSERVED |
| VO | Voltage output swing from rail (Positi | VS = 30 V; RL = 2 kΩ, TA = 0°C to  | - / - / 4 V | - | SIM_ERROR |
| VO | Voltage output swing from rail (Positi | VS = 30 V; RL ≥ 10 kΩ | - / 2 V / 3 V | - | SIM_ERROR |
| VO | Voltage output swing from rail (Positi | VS = 5 V; RL ≥ 2 kΩ | - / - / 1.5 V | - | SIM_ERROR |
| VO | Voltage output swing from rail (Negati | VS = 5 V; RL ≤ 10 kΩ, TA = 0°C to  | - / 5 mV / 20 mV | - | SIM_ERROR |
| IO | Output current (Source) | VS = 15 V; VO = 0 V; VID = 1 V, LM | -20 mA / -30 mA / - | - | SIM_ERROR |
| IO | Output current (Source) | VS = 15 V; VO = 0 V; VID = 1 V, TA | -10 mA / - / - | - | SIM_ERROR |
| IO | Output current (Sink) | VS = 15 V; VO = 15 V; VID = –1 V | 10 mA / 20 mA / - | - | SIM_ERROR |
| IO | Output current (Sink) | VS = 15 V; VO = 15 V; VID = –1 V,  | 5 mA / - / - | - | SIM_ERROR |
| IO | Output current (Sink) | VID = –1 V; VO = 200 mV | 12 uA / 30 uA / - | 30.02 mA | PASS |
| ISC | Short-circuit current | VS = 10 V; VO = VS / 2 | -40 mA / - / 60 mA | 30.05 mA | FAIL |
| IQ | Quiescent current per amplifier | VO = 2.5 V; IO = 0 A | - / 350 uA / 600 uA | 310 uA | PASS |
| IQ | Quiescent current per amplifier | VO = 2.5 V; IO = 0 A, TA = 0°C to  | - / - / - | 310 uA | NO_NUMERIC_LIMIT |
| IQ | Quiescent current per amplifier | VS = 30 V; VO = 15 V; IO = 0 A | - / 500 uA / 1 mA | 560 uA | PASS |
| VOS | Input offset voltage | LM2904, LM2904V, VS = 5 V, TA = 25 | - / 3 mV / 7 mV | 2.498 V | FAIL |
| VOS | Input offset voltage | LM2904, LM2904V, VS = 5 V, TA = -4 | - / - / 10 mV | 2.498 V | FAIL |
| VOS | Input offset voltage | LM2904, LM2904V, VS = 5 V, TA = 25 | - / 1 mV / 2 mV | 2.498 V | FAIL |
| VOS | Input offset voltage | LM2904, LM2904V, VS = 5 V, TA = -4 | - / - / 4 mV | 2.498 V | FAIL |
| dVOS/dT | Input offset voltage drift | LM2904, LM2904V, VS = 5 V, TA = -4 | - / - / - | - | UNSUPPORTED_KIND |
| PSRR | Input offset voltage vs power supply ( | LM2904, LM2904V, VS = 5 V, TA = 25 | - / - / - | 2.498 V | NO_NUMERIC_LIMIT |
| VO1/VO2 | Channel separation | LM2904, LM2904V, VS = 5 V, TA = 25 | - / - / - | - | UNSUPPORTED_KIND |
| VCM | Common-mode voltage range | LM2904, LM2904V, VS = 5 V, TA = 25 | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | LM2904, LM2904V, VS = 5 V, TA = -4 | - / - / - | - | NOT_TESTABLE_CONDITION |
| CMRR | Common-mode rejection ratio | LM2904, LM2904V, VS = 5 V, TA = 25 | 65 dB / 80 dB / - | -316 dB | FAIL |
| IB | Input bias current | LM2904, LM2904V, VS = 5 V, TA = 25 | - / -20 nA / -250 nA | - | SIM_ERROR |
| IB | Input bias current | LM2904, LM2904V, VS = 5 V, TA = -4 | - / - / -500 nA | - | SIM_ERROR |
| IOS | Input offset current | LM2904, LM2904V, VS = 5 V, TA = 25 | - / 2 nA / 50 nA | - | SIM_ERROR |
| IOS | Input offset current | LM2904, LM2904V, VS = 5 V, TA = -4 | - / - / 300 nA | - | SIM_ERROR |
| IOS | Input offset current | LM2904, LM2904V, VS = 5 V, TA = -4 | - / - / 150 nA | - | SIM_ERROR |
| dIOS/dT | Input offset current drift | LM2904, LM2904V, VS = 5 V, TA = -4 | - / - / - | - | UNSUPPORTED_KIND |
| en | Input voltage noise density | LM2904, LM2904V, VS = 5 V, TA = 25 | - / 40 nV/rtHz / - | 1.34e+04 nV/rtHz | FAIL_TYP |
| AOL | Open-loop voltage gain | LM2904, LM2904V, VS = 5 V, TA = 25 | 87.96 dB / 100 dB / - | -472 dB | FAIL |
| AOL | Open-loop voltage gain | LM2904, LM2904V, VS = 5 V, TA = -4 | 83.52 dB / - / - | -472 dB | FAIL |
| GBW | Gain bandwidth product | LM2904, LM2904V, VS = 5 V, TA = 25 | - / 700 kHz / - | - | NOT_OBSERVED |
| SR | Slew rate | LM2904, LM2904V, VS = 5 V, TA = 25 | - / 0.3 V/us / - | - | NOT_OBSERVED |
| VO | Voltage output swing from rail (Positi | LM2904, LM2904V, VS = 5 V, TA = 25 | - / - / 1.5 V | - | SIM_ERROR |
| VO | Voltage output swing from rail (Positi | LM2904, LM2904V, VS = 5 V, TA = 25 | - / 2 V / 3 V | - | SIM_ERROR |
| VO | Voltage output swing from rail (Positi | LM2904, LM2904V, VS = 5 V, TA = 25 | - / - / 6 V | - | SIM_ERROR |
| VO | Voltage output swing from rail (Positi | LM2904, LM2904V, VS = 5 V, TA = 25 | - / 4 V / 5 V | - | SIM_ERROR |
| VO | Voltage output swing from rail (Negati | LM2904, LM2904V, VS = 5 V, TA = 25 | - / 5 mV / 20 mV | - | SIM_ERROR |
| VO | Voltage output swing from rail (Negati | LM2904, LM2904V, VS = 5 V, TA = -4 | - / - / - | - | SIM_ERROR |
| IO | Output current (Source) | LM2904, LM2904V, VS = 5 V, TA = 25 | -20 mA / -30 mA / - | - | SIM_ERROR |
| IO | Output current (Source) | LM2904, LM2904V, VS = 5 V, TA = -4 | -10 mA / - / - | - | SIM_ERROR |
| IO | Output current (Sink) | LM2904, LM2904V, VS = 5 V, TA = 25 | 10 mA / 20 mA / - | 30.02 mA | PASS |
| IO | Output current (Sink) | LM2904, LM2904V, VS = 5 V, TA = -4 | 5 mA / - / - | 30.02 mA | PASS |
| IO | Output current (Sink) | LM2904, LM2904V, VS = 5 V, TA = 25 | - / 30 uA / - | 30.02 mA | FAIL_TYP |
| IO | Output current (Sink) | LM2904, LM2904V, VS = 5 V, TA = 25 | 12 uA / 40 uA / - | 30.02 mA | PASS |
| ISC | Short-circuit current | LM2904, LM2904V, VS = 5 V, TA = 25 | - / 40 mA / 60 mA | - | SIM_ERROR |
| IQ | Quiescent current per amplifier | LM2904, LM2904V, VS = 5 V, TA = 25 | - / 350 uA / 600 uA | 310 uA | PASS |
| IQ | Quiescent current per amplifier | LM2904, LM2904V, VS = 5 V, TA = -4 | - / - / - | 310 uA | NO_NUMERIC_LIMIT |
| IQ | Quiescent current per amplifier | LM2904, LM2904V, VS = 5 V, TA = 25 | - / 500 uA / 1 mA | - | SIM_ERROR |
| VOS | Input offset voltage | LM158, VS = 5 V to 30 V; VCM = 0 V | - / 3 mV / 5 mV | 2.498 V | FAIL |
| VOS | Input offset voltage | LM158, TA = –55°C to 125°C | - / - / 7 mV | 2.498 V | FAIL |
| VOS | Input offset voltage | LM158A, VS = 5 V to 30 V; VCM = 0  | - / - / 2 mV | 2.498 V | FAIL |
| VOS | Input offset voltage | LM158A, TA = –55°C to 125°C | - / - / 4 mV | 2.498 V | FAIL |
| dVOS/dT | Input offset voltage drift | LM158, TA = –55°C to 125°C | - / - / - | - | UNSUPPORTED_KIND |
| dVOS/dT | Input offset voltage drift | LM158A, TA = –55°C to 125°C | - / - / - | - | UNSUPPORTED_KIND |
| PSRR | Input offset voltage vs power supply ( | VS = 5 V to 30 V, TA = 25°C | - / - / - | 2.498 V | NO_NUMERIC_LIMIT |
| VO1/VO2 | Channel separation | f = 1 kHz to 20 kHz, TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| VCM | Common-mode voltage range | LM158, VS = 5 V to 30 V, TA = 25°C | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | LM158A, VS = 30 V, TA = 25°C | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | LM158, VS = 5 V to 30 V, TA = –55° | - / - / - | - | NOT_TESTABLE_CONDITION |
| VCM | Common-mode voltage range | LM158A, VS = 30 V, TA = –55°C to 1 | - / - / - | - | NOT_TESTABLE_CONDITION |
| CMRR | Common-mode rejection ratio | VS = 5 V to 30 V; VCM = 0 V, TA =  | 70 dB / 80 dB / - | -316 dB | FAIL |
| IB | Input bias current | LM158, VO = 1.4 V, TA = 25°C | -20 nA / - / -150 nA | - | SIM_ERROR |
| IB | Input bias current | LM158, TA = –55°C to 125°C | - / - / -300 nA | 9.437 nA | PASS |
| IB | Input bias current | LM158A, VO = 1.4 V, TA = 25°C | -15 nA / - / -50 nA | - | SIM_ERROR |
| IB | Input bias current | LM158A, TA = –55°C to 125°C | - / - / -100 nA | 9.437 nA | PASS |
| IOS | Input offset current | LM158, VO = 1.4 V, TA = 25°C | 2 nA / - / 30 nA | - | SIM_ERROR |
| IOS | Input offset current | LM158, TA = –55°C to 125°C | - / - / 100 nA | 499.6 nA | FAIL |
| IOS | Input offset current | LM158A, VO = 1.4 V, TA = 25°C | 2 nA / - / 10 nA | - | SIM_ERROR |
| IOS | Input offset current | LM158A, TA = –55°C to 125°C | - / - / 30 nA | 499.6 nA | FAIL |
| dIOS/dT | Input offset current drift | TA = 25°C | - / - / - | - | UNSUPPORTED_KIND |
| dIOS/dT | Input offset current drift | LM158A, TA = –55°C to 125°C | - / - / - | - | UNSUPPORTED_KIND |
| en | Input voltage noise density | f = 1 kHz, TA = 25°C | - / 40 nV/rtHz / - | 1.34e+04 nV/rtHz | FAIL_TYP |
| AOL | Open-loop voltage gain | VS = 15 V; VO = 1 V to 11 V; RL ≥  | 93.98 dB / 100 dB / - | -472 dB | FAIL |
| AOL | Open-loop voltage gain | VS = 15 V; VO = 1 V to 11 V; RL ≥  | 87.96 dB / - / - | -472 dB | FAIL |
| GBW | Gain bandwidth product | TA = 25°C | - / 700 kHz / - | - | NOT_OBSERVED |
| SR | Slew rate | G = +1, TA = 25°C | - / 0.3 V/us / - | - | NOT_OBSERVED |
| VO | Voltage output swing from rail (Positi | VS = 30 V; RL = 2 kΩ, TA = –55°C t | - / - / 4 V | - | SIM_ERROR |
| VO | Voltage output swing from rail (Positi | VS = 30 V; RL ≥ 10 kΩ, TA = 25°C | - / 2 V / 3 V | - | SIM_ERROR |
| VO | Voltage output swing from rail (Positi | VS = 5 V; RL ≥ 2 kΩ, TA = 25°C | - / - / 1.5 V | - | SIM_ERROR |
| VO | Voltage output swing from rail (Negati | VS = 5 V; RL ≤ 10 kΩ, TA = –55°C t | - / 5 mV / 20 mV | - | SIM_ERROR |
| IO | Output current (Source) | VS = 15 V; VO = 0 V; VID = 1 V, TA | -20 mA / -30 mA / - | - | SIM_ERROR |
| IO | Output current (Source) | LM158A, VS = 15 V; VO = 0 V; VID = | - / - / -60 mA | - | SIM_ERROR |
| IO | Output current (Sink) | VS = 15 V; VO = 15 V; VID = –1 V,  | 10 mA / 20 mA / - | - | SIM_ERROR |
| IO | Output current (Sink) | VS = 15 V; VO = 15 V; VID = –1 V,  | 5 mA / - / - | - | SIM_ERROR |
| IO | Output current (Sink) | VID = –1 V; VO = 200 mV, TA = 25°C | 12 uA / 30 uA / - | 30.02 mA | PASS |
| ISC | Short-circuit current | VS = 10 V; VO = VS / 2, TA = 25°C | - / 40 mA / 60 mA | 30.05 mA | PASS |