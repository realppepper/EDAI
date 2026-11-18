# Specification coverage — TL071

- Verification target rows (all): **34**
- Electrical (testable) rows: **0**
- Mapped to a deterministic fixture: **0**
- Actually measured: **0** → coverage **0.0 %**
- PDG Causal Gate Status: **PDG_STAGE0_TOPOLOGY**
- Pass among measured rows: **0.0 %** (0/0)
- Pass among unique parameter kinds: **0.0 %** (0/0)
- Sim errors 0 | not observed 0 | no fixture 0 | unsupported kind 0 | not testable 34

| Symbol | Name | Conditions | Limits (canonical) | Measured | Result |
|---|---|---|---|---|---|
| VS | Supply voltage, VS = (V+) – (V–) | All NS and PS packages; All TL07xM | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VS | Supply voltage, VS = (V+) – (V–) | All other devices | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VICM | Common-mode voltage | All NS and PS packages; All TL07xM | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VICM | Common-mode voltage | All other devices | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VID | Differential voltage | All NS and PS packages; All TL07xM | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| VID | Differential voltage | All other devices | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| IIN | Current | All NS and PS packages; All TL07xM | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| IIN | Current | All other devices | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| ISC | Output short-circuit | Continuous | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| TA | Operating ambient temperature, TA |  | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| TJ | Junction temperature, TJ |  | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| TC | Case temperature for 60 seconds - FK p | FK package | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| TL | Lead temperature 1.8 mm (1/16 inch) fr | 1.8 mm (1/16 inch) from case for 1 | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| Tstg | Storage temperature, Tstg |  | - / - / - | - | NOT_TESTABLE_ABS_MAX |
| V(ESD) | Electrostatic discharge | Human-body model (HBM), per ANSI/E | - / - / - | - | NOT_TESTABLE_ESD |
| V(ESD) | Electrostatic discharge | Charged-device model (CDM), per JE | - / - / - | - | NOT_TESTABLE_ESD |
| RθJA | Junction-to-ambient thermal resistance | TL074xx, D (SOIC) | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJA | Junction-to-ambient thermal resistance | TL074xx, DYY (SOT-23) | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJA | Junction-to-ambient thermal resistance | TL074xx, N (TSSOP) | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJA | Junction-to-ambient thermal resistance | TL074xx, NS (TSSOP) | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJA | Junction-to-ambient thermal resistance | TL074xx, W (TSSOP) | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJC(top) | Junction-to-case (top) thermal resista | TL074xx, D (SOIC) | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJC(top) | Junction-to-case (top) thermal resista | TL074xx, DYY (SOT-23) | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJC(top) | Junction-to-case (top) thermal resista | TL074xx, FK (TSSOP) | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJC(top) | Junction-to-case (top) thermal resista | TL074xx, J (TSSOP) | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJC(top) | Junction-to-case (top) thermal resista | TL074xx, PW (TSSOP) | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJC(top) | Junction-to-case (top) thermal resista | TL074xx, W (TSSOP) | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJB | Junction-to-board thermal resistance | TL074xx, D (SOIC) | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJB | Junction-to-board thermal resistance | TL074xx, DYY (SOT-23) | - / - / - | - | NOT_TESTABLE_THERMAL |
| RθJB | Junction-to-board thermal resistance | TL074xx, W (TSSOP) | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJT | Junction-to-top characterization param | TL074xx, D (SOIC) | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJT | Junction-to-top characterization param | TL074xx, DYY (SOT-23) | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJT | Junction-to-top characterization param | TL074xx, W (TSSOP) | - / - / - | - | NOT_TESTABLE_THERMAL |
| ψJB | Junction-to-board characterization par | TL074xx, D (SOIC) | - / - / - | - | NOT_TESTABLE_THERMAL |