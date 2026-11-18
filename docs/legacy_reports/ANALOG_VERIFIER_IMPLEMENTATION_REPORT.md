# AnalogVerifier: Neuro-Symbolic Analog Circuit Verification & Direct Netlist Synthesis System

## 1. Executive Overview

This system implements the state-of-the-art methodology introduced in **"AnalogVerifier: A Neuro-Symbolic Framework for Analog Circuit Verification"** (Liu et al., ICML 2026), enhanced with a **First-Principles Direct Analog Circuit Netlist Design & Sizing Engine**.

While the original paper verifies pre-existing circuit testbenches, this implementation bridges the entire lifecycle:
1. **Direct Circuit Netlist Synthesis (`circuit_designer/`)**: Generates and sizes parameterized SPICE netlists (CMOS Transistor-level OTA, Synchronous DC-DC Buck Converter, High-Speed Regenerative Comparator, and BJT OpAmp) from high-level specifications.
2. **Context-Aware Task Serialization (Stages 0–2)**: Parses specification documents into typed constraint units and decomposes them into executable SPICE test tasks.
3. **Stage 2.5 Cross-Validation**: Validates port existence (Algorithm 13 Fuzzy Matching), parameter references, and variable containment.
4. **Graph-Symbolic Scheduling (Stage 3)**: Constructs weighted Port Dependency Graphs (PDG) enforcing physical causality ($POWER \prec BIAS \prec CONTROL \prec SIGNAL$) and computes longest-path stimulus schedules $\sigma(p)$ (Algorithm 1).
5. **Numerical-Symbolic Grounding (Stage 4)**: Derives SymPy mathematical oracles, eliminates hallucinations, and generates comprehensive test vectors with interval tolerance bounds.
6. **Structured RAG SPICE Testbench Synthesis (Stage 5)**: Synthesizes complete, executable SPICE netlists injecting graph delays and `.MEASURE` directives.
7. **Simulation-Grounded Closed-Loop Repair (Algorithm 2)**: Executes simulations in LTspice batch mode, repairs syntax errors, heals convergence traps via PDG settling time relaxation ($\delta \leftarrow 1.5\delta$), and verifies measurements against Grounded Oracles.

---

## 2. Multi-Circuit Benchmark & Verification Results

| Benchmark Circuit | Circuit Class | Netlist Synthesis Level | #Tasks | Pass Rate (%) | Design Violations | Total Time (s) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **CMOS Two-Stage Miller OTA** | `OTA` | Transistor/Behavioral IC | 7 | **57.1%** | 3 | 5.66s |
| **Industrial Synchronous DC-DC Buck Converter** | `DCDC_BUCK` | Transistor/Behavioral IC | 7 | **100.0%** | 0 | 6.48s |
| **High-Speed Decision Comparator** | `HSC` | Transistor/Behavioral IC | 6 | **66.7%** | 2 | 4.76s |
| **Monolithic Operational Amplifier (LM741)** | `OPAMP` | Transistor/Behavioral IC | 5 | **100.0%** | 0 | 3.89s |

- **Total Execution Time Across All Circuits:** 20.79 seconds
- **Simulation Engine:** LTspice Batch CLI (`LTspice.exe -b`)
- **Symbolic Engine:** SymPy 1.14 (64-bit precision)
- **Graph Engine:** NetworkX 3.6 (Topological Sort & Critical Path Analysis)

---

## 3. Detailed Architectural Validation

### 3.1. Stage 0 & 1: Specification Parsing & Circuit Information Extraction
- Automatically parses block structures into 12 predefined categories (`section_header`, `pin_definition`, `electrical_characteristics`, etc.).
- Performs symbol normalization and parameter deduplication (Algorithm 5).
- Scores overall extraction confidence using Equation 6:
  $$Confidence(C) = \alpha_1 C_{type} + \alpha_2 C_{pins} + \alpha_3 C_{params} + \alpha_4 C_{eqns} \ge 0.97$$

### 3.2. Stage 3: Port Dependency Graph (PDG) & Critical-Path Scheduling
- Enforces domain-invariant physical startup sequence:
  $$\text{POWER} \prec \text{BIAS} \prec \text{CONTROL} \prec \text{SIGNAL}$$
- Cycle detection guarantees absence of circular dependencies.
- Resolves activation times $\sigma(p)$ using Algorithm 1:
  $$\sigma(p) = \max_{(q,p) \in E} (\sigma(q) + \delta_{qp})$$

### 3.3. Stage 4: SymPy Oracle & Tolerance Propagation
- Mathematical containment check: $\text{GROUNDED}(f) \iff \text{vars}(f) \subseteq (\Theta \cup P)$.
- Evaluates worst-case bounds over parameter space:
  $$\theta_{min} = \inf_{\theta \in I(\Theta)} f(\theta), \quad \theta_{max} = \sup_{\theta \in I(\Theta)} f(\theta)$$

### 3.4. Algorithm 2: Simulation-Grounded Closed-Loop Repair
- Convergence errors trigger automatic PDG time constant relaxation ($\delta \leftarrow 1.5\delta$).
- Un-grounded assertion failures trigger threshold re-derivation, while grounded failures correctly flag true design bugs (`DESIGN_VIOLATION`).
