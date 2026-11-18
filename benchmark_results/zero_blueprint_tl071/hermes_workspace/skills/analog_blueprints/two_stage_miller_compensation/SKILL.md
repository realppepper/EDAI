---
name: two_stage_miller_compensation
category: Operational Amplifier
description: Domain Subcircuit Blueprint for two_stage_miller_compensation
---

# Blueprint Skill: two_stage_miller_compensation

## Description
Domain Subcircuit Blueprint for two_stage_miller_compensation

## SPICE Topology & Netlist
```spice
BLUEPRINT: Two-Stage Opamp with Miller Compensation
1. DIFF PAIR: M1/M2 (PMOS), tail current Itail=20u, W/L=50u/1u
2. ACTIVE LOAD: M3/M4 (NMOS mirror), W/L=20u/1u
3. STAGE1 OUT: drain of M2/M4 (high-Z node)
4. OUTPUT STAGE: M5 (PMOS common-source), bias Ibias=100u, W/L=200u/1u
5. COMPENSATION: Cc=15p from stage1_out to OUT
6. NULLING RESISTOR: Rz=2k in series with Cc (Rz = 1/gm5)
7. BIAS CIRCUIT: Current mirror from Iref to generate Itail, Ibias
8. PIN ORDER: IN+ IN- VDD VSS OUT
SYNTAX: Cc stage1_out OUT 15p ; Rz stage1_out n_int 2k ; Cc n_int OUT 15p
```
