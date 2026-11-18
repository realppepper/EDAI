# Autonomous AI Analog Circuit Synthesis & Verification Report
**Target IC:** `TL431, TL432` | **Subcircuit:** `TL431__TL432`
**Overall Datasheet Specification Pass Rate:** `0.0%`

## 1. Executive Summary
- **IC Category:** The TL431 and TL432 devices are three-terminal adjustable shunt regulators, with specified thermal stability over applicable automotive, commercial, and military temperature ranges. The output voltage can be set to any value between Vref (approximately 2.5V) and 36V, with two external resistors. These devices have a typical output impedance of 0.2Ω. Active output circuitry provides a very sharp turn-on characteristic, making these devices excellent replacements for Zener diodes in many applications, such as on-board regulation, adjustable power supplies, and switching power supplies. The TL432 device has exactly the same functionality and electrical specifications as the TL431 device, but has different pinouts for the DBV, DBZ, and PK packages. Both the TL431 and TL432 devices are offered in three grades, with initial tolerances (at 25°C) of 0.5%, 1%, and 2%, for the B, A, and standard grade, respectively. In addition, low output drift versus temperature verifies good stability over the entire temperature range. The TL43xxC devices are characterized for operation from 0°C to 70°C, the TL43xxI devices are characterized for operation from –40°C to 85°C, and the TL43xxQ devices are characterized for operation from –40°C to 125°C.
- **Total Datasheet Specifications Extracted:** 49
- **Design Iterations Required:** 2
- **Synthesized Netlist Location:** `C:\Users\Sera\.gemini\antigravity\worktrees\Project2\implement_circuit_test_methodology\benchmark_results\TL431\TL431__TL432_iter2.cir`

## 2. Port Dependency Graph (PDG) Scheduling
Topological activation sequence derived from physical pin roles:
| Pin Name | Physical Role | Direction | Activation Time (us) |
| :--- | :--- | :--- | :--- |

### 2.1 Port Dependency Graph Topology
```mermaid
graph TD
```

## 3. Specification Verification & SymPy Oracle Audit
Detailed verification results evaluated against SymPy interval constraints:
| Parameter | Min Target | Typ Target | Max Target | Measured Value | Unit | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `Vref` | - | - | 0.5 | **N/A** | % | ❌ FAIL |
| `Vref` | - | - | 1 | **N/A** | % | ❌ FAIL |
| `Vref` | - | - | 2 | **N/A** | % | ❌ FAIL |
| `Vout` | 2.5 | - | 36 | **N/A** | V | ❌ FAIL |
| `TA` | -40 | - | 125 | **N/A** | °C | ❌ FAIL |
| `ΔVref` | 0.0048 | 0.006 | 0.0072 | **N/A** | mV | ❌ FAIL |
| `ΔVref` | 0.0112 | 0.014 | 0.0168 | **N/A** | mV | ❌ FAIL |
| `Zout` | 0.16 | 0.2 | 0.24 | **N/A** | Ω | ❌ FAIL |
| `Isink` | 0.001 | - | 0.1 | **N/A** | mA | ❌ FAIL |
| `VKA` | - | - | 37 | **N/A** | V | ❌ FAIL |
| `IKA` | -0.1 | - | 0.15 | **N/A** | mA | ❌ FAIL |
| `II(ref)` | -5e-05 | - | 0.01 | **N/A** | mA | ❌ FAIL |
| `TJ` | - | - | 150 | **N/A** | °C | ❌ FAIL |
| `RθJC(top)` | 45.6 | 57 | 68.4 | **N/A** | °C/W | ❌ FAIL |
| `RθJC(top)` | 52 | 65 | 78 | **N/A** | °C/W | ❌ FAIL |
| `RθJC(top)` | 31.2 | 39 | 46.8 | **N/A** | °C/W | ❌ FAIL |
| `RθJC(top)` | 36.8 | 46 | 55.2 | **N/A** | °C/W | ❌ FAIL |
| `RθJC(top)` | 69.6 | 87 | 104.4 | **N/A** | °C/W | ❌ FAIL |
| `RθJC(top)` | 104.8 | 131 | 157.2 | **N/A** | °C/W | ❌ FAIL |
| `RθJC(top)` | 60.8 | 76 | 91.2 | **N/A** | °C/W | ❌ FAIL |
| `RθJC(top)` | 44 | 55 | 66 | **N/A** | °C/W | ❌ FAIL |
| `RθJC(top)` | 7.2 | 9 | 10.8 | **N/A** | °C/W | ❌ FAIL |
| `VKA` | 2.5 | - | 36 | **N/A** | V | ❌ FAIL |
| `IKA` | 0.001 | - | 0.1 | **N/A** | mA | ❌ FAIL |
| `TA` | 0 | - | 70 | **N/A** | °C | ❌ FAIL |
| `TA` | -40 | - | 85 | **N/A** | °C | ❌ FAIL |
| `TA` | -40 | - | 125 | **N/A** | °C | ❌ FAIL |
| `Vref` | 2.44 | 2.495 | 2.55 | **N/A** | mV | ❌ FAIL |
| `VI(dev)` | - | 0.006 | 0.016 | **N/A** | mV | ❌ FAIL |
| `VI(dev)` | - | 0.004 | 0.025 | **N/A** | mV | ❌ FAIL |
| `ΔVref / ΔVKA` | - | -0.0014 | -0.0027 | **N/A** | mV/V | ❌ FAIL |
| `ΔVref / ΔVKA` | - | -0.001 | -0.002 | **N/A** | mV/V | ❌ FAIL |
| `Iref` | - | 2e-06 | 4e-06 | **N/A** | µA | ❌ FAIL |
| `II(dev)` | - | 4e-07 | 1.2e-06 | **N/A** | µA | ❌ FAIL |
| `Imin` | 0.0004 | - | 0.001 | **N/A** | mA | ❌ FAIL |
| `Ioff` | - | 1e-07 | 1e-06 | **N/A** | µA | ❌ FAIL |
| `|ZKA|` | - | 0.2 | 0.5 | **N/A** | Ω | ❌ FAIL |

## 4. Closed-Loop Iteration History & Root Cause Analysis
| Iteration | Pass Rate | Passed Specs | Failed Specs | Architecture Notes |
| :--- | :--- | :--- | :--- | :--- |
| Iteration 1 | 0.0% | 0 | 0 | The TL431/TL432 is a precision adjustable shunt regulator. The core of its opera... |
| Iteration 2 | 0.0% | 0 | 0 | The TL431/TL432 is a precision adjustable shunt regulator. The core of its opera... |

### 4.1 Loop 1 Detailed Audit
- **Pass Rate**: `0.0%` (0/0 specs passed)

**Shortfall Audit (미달 원인 분석):**
- Compiler/Simulation Error: C:\Users\Sera\.gemini\antigravity\worktrees\Project2\implement_circuit_test_methodology\benchmark_results\TL431\tb_dc_op.cir(28): syntax error
- Compiler/Simulation Error:   --> .meas Vref_op_val V(REF)
- Compiler/Simulation Error:   --> ^^^^^^^
- Compiler/Simulation Error: C:\Users\Sera\.gemini\antigravity\worktrees\Project2\implement_circuit_test_methodology\benchmark_results\TL431\tb_dc_op.cir(38): syntax error
- Param 'Vref' violated: Parameter 'Vref' was not observed in simulation measurements. (Measured: Unobserved)
- Param 'Vref' violated: Parameter 'Vref' was not observed in simulation measurements. (Measured: Unobserved)
- Param 'Vref' violated: Parameter 'Vref' was not observed in simulation measurements. (Measured: Unobserved)
- Param 'Vout' violated: Parameter 'Vout' was not observed in simulation measurements. (Measured: Unobserved)
- Param 'TA' violated: Parameter 'TA' was not observed in simulation measurements. (Measured: Unobserved)
- Param 'ΔVref' violated: Parameter 'ΔVref' was not observed in simulation measurements. (Measured: Unobserved)

**Improvement Actions (개선 및 수정 사항):**
- Initial first-principles topology and Level-1 parameter sizing synthesized from scratch.

### 4.2 Loop 2 Detailed Audit
- **Pass Rate**: `0.0%` (0/0 specs passed)

**Shortfall Audit (미달 원인 분석):**
- Compiler/Simulation Error: C:\Users\Sera\.gemini\antigravity\worktrees\Project2\implement_circuit_test_methodology\benchmark_results\TL431\tb_dc_op.cir(28): syntax error
- Compiler/Simulation Error:   --> .meas Vref_0_5_pct_tol PARAM FIND V(REF)
- Compiler/Simulation Error:   --> ^^^^^^^
- Compiler/Simulation Error: C:\Users\Sera\.gemini\antigravity\worktrees\Project2\implement_circuit_test_methodology\benchmark_results\TL431\tb_dc_op.cir(29): syntax error
- Param 'Vref' violated: Parameter 'Vref' was not observed in simulation measurements. (Measured: Unobserved)
- Param 'Vref' violated: Parameter 'Vref' was not observed in simulation measurements. (Measured: Unobserved)
- Param 'Vref' violated: Parameter 'Vref' was not observed in simulation measurements. (Measured: Unobserved)
- Param 'Vout' violated: Parameter 'Vout' was not observed in simulation measurements. (Measured: Unobserved)
- Param 'TA' violated: Parameter 'TA' was not observed in simulation measurements. (Measured: Unobserved)
- Param 'ΔVref' violated: Parameter 'ΔVref' was not observed in simulation measurements. (Measured: Unobserved)

**Improvement Actions (개선 및 수정 사항):**
- Topology refinement: The TL431/TL432 is a precision adjustable shunt regulator. The core of its operation is a voltage reference and an error amplifier that comp...

## 5. Synthesized SPICE Netlist Architecture
Netlist file: `C:\Users\Sera\.gemini\antigravity\worktrees\Project2\implement_circuit_test_methodology\benchmark_results\TL431\TL431__TL432_iter2.cir`
```spice
* TL431/TL432 Three-Terminal Adjustable Shunt Regulator
* Pinout: K (Cathode), A (Anode), REF (Reference)
.subckt TL431__TL432 K REF A

* --- Model Definitions ---
.model NMOS NMOS (LEVEL=1 VTO=0.7 KP=100u LAMBDA=0.02 TOX=100n GAMMA=0.5 PHI=0.6)
.model PMOS PMOS (LEVEL=1 VTO=-0.7 KP=40u LAMBDA=0.03 TOX=100n GAMMA=0.6 PHI=0.6)
.model NPN NPN (BF=100 VAF=50 IS=1e-14 CJE=1p CJC=2p RC=1 RE=0.1 RB=10 IKF=0.1)
.model PNP PNP (BF=50 VAF=30 IS=1e-14 CJE=2p CJC=3p RC=2 RE=0.2 RB=20 IKF=0.05)

* --- Internal Voltage Reference (Bandgap-like) ---
* Simplified bandgap reference for ~2.5V output with temperature compensation
* Vref_bandgap is the core reference voltage
* Vref_trim allows for initial tolerance adjustment (0.5%, 1%, 2%)
B_Vref_bandgap Vref_bandgap 0 V = {2.495 + V(Vref_trim_val)} ; Typical Vref = 2.495V

* --- Error Amplifier ---
* Input Differential Pair (PMOS)
M1 REF V_bias_diff_gate V_bias_diff_source V_bias_diff_source PMOS W=10u L=1u
M2 Vref_bandgap V_bias_diff_gate V_bias_diff_source V_bias_diff_source PMOS W=10u L=1u

* Current Mirror Load (NMOS)
M3 V_diff_out V_cm_gate 0 0 NMOS W=5u L=1u
M4 V_bias_diff_source V_cm_gate 0 0 NMOS W=5u L=1u

* Second Stage (Common Source with Active Load)
M5 V_amp_out V_diff_out V_bias_amp_source V_bias_amp_source PMOS W=20u L=1u
M6 V_amp_out V_cm_gate 0 0 NMOS W=10u L=1u

* Compensation Capacitor
Ccomp V_diff_out V_amp_out 50p

* --- Bias Circuitry ---
* Constant current source for differential pair
Ibias_diff V_bias_diff_source 0 DC 10uA

* Constant current source for second stage
Ibias_amp V_bias_amp_source 0 DC 20uA

* Gate bias for current mirror loads (M3, M4, M6)
R_cm_bias VDD V_cm_gate 100k
I_cm_bias 0 V_cm_gate DC 10uA ; Sets the gate voltage for the current mirror

* Gate bias for differential pair (M1, M2)
R_diff_gate VDD V_bias_diff_gate 100k
I_diff_gate 0 V_bias_diff_gate DC 5uA

* --- Output Stage ---
* NPN output transistor
Q1 K V_amp_out A NPN

* --- ESD Protection (Simplified) ---
* Diodes to clamp REF pin to K and A
D_ref_k REF K D_ESD
D_ref_a A REF D_ESD
.model D_ESD D (IS=1e-15 BV=40 IBV=1e-5)

* --- Vref Trim for Initial Tolerance ---
* This source allows setting the Vref offset for different grades.
* For typical operation, set Vref_trim_val to 0.
* For 0.5% tolerance: Vref_trim_val = 2.5V * 0.005 = 12.5mV
* For 1% tolerance: Vref_trim_val = 2.5V * 0.01 = 25mV
* For 2% tolerance: Vref_trim_val = 2.5V * 0.02 = 50mV
V_Vref_trim Vref_trim_val 0 DC 0V ; Set to 0V for typical, adjust for tolerance

* --- Power Supply for Internal Circuitry (Derived from K and A) ---
* The internal circuitry needs a supply. We'll assume a virtual VDD for the internal blocks
* that is derived from K, and a virtual GND that is A.
* This is a simplification, as the actual TL431 uses the K-A voltage as its supply.
* For the internal bias and amplifier, we need a stable supply.
* Let's create a virtual VDD and GND for the internal blocks.
* VDD_internal is derived from K, GND_internal is A.
* The internal bias currents and amplifier stages operate between these.
* For simplicity, we'll assume the internal VDD is K and internal GND is A for the bias.
* The PMOS sources are connected to a node that is effectively VDD for the internal circuit.
* The NMOS drains are connected to a node that is effectively GND for the internal circuit.
* Let's define VDD_internal as K and GND_internal as A for the internal bias.
* The current sources and resistors are connected to these.
* Re-evaluate the bias connections to reflect K-A supply.

* Re-architecting bias for K-A supply
* The internal circuitry operates from VKA.
* The PMOS sources will be connected to K.
* The NMOS sources will be connected to A.

* --- Re-architected Error Amplifier for K-A supply ---
* Input Differential Pair (PMOS)
M1_2 REF V_bias_diff_gate K K PMOS W=10u L=1u
M2_2 Vref_bandgap V_bias_diff_gate K K PMOS W=10u L=1u

* Current Mirror Load (NMOS)
M3_2 V_diff_out V_cm_gate A A NMOS W=5u L=1u
M4_2 V_bias_diff_source V_cm_gate A A NMOS W=5u L=1u

* Second Stage (Common Source with Active Load)
M5_2 V_amp_out V_diff_out K K PMOS W=20u L=1u
M6_2 V_amp_out V_cm_gate A A NMOS W=10u L=1u

* Compensation Capacitor
Ccomp_2 V_diff_out V_amp_out 50p

* --- Re-architected Bias Circuitry for K-A supply ---
* Constant current source for differential pair
Ibias_diff_2 K V_bias_diff_source DC 10uA

* Constant current source for second stage
Ibias_amp_2 K V_bias_amp_source DC 20uA

* Gate bias for current mirror loads (M3, M4, M6)
R_cm_bias_2 K V_cm_gate 100k
I_cm_bias_2 A V_cm_gate DC 10uA ; Sets the gate voltage for the current mirror

* Gate bias for differential pair (M1, M2)
R_diff_gate_2 K V_bias_diff_gate 100k
I_diff_gate_2 A V_bias_diff_gate DC 5uA

* --- Output Stage ---
* NPN output transistor
Q1_2 K V_amp_out A NPN

* --- Vref Trim for Initial Tolerance ---
V_Vref_trim_2 Vref_trim_val 0 DC 0V ; Set to 0V for typical, adjust for tolerance

.ends TL431__TL432
```