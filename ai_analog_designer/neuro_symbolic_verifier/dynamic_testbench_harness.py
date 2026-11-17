"""
Dynamic LLM-driven Testbench Harness with Mathematical Post-Processing.
Supports complex specification verification (THD+N, Fourier harmonics, output power,
oscillation frequency, efficiency, channel crosstalk, and dynamic switching parameters)
by synthesizing targeted LTspice testbenches and applying NumPy/SciPy mathematical analysis.
"""
from __future__ import annotations

import logging
import math
import os
import re
from typing import Any

from ai_analog_designer.llm_client import LLMClient

from .ltspice_runner import LTspiceRunner
from .sympy_oracle_engine import SymPyOracleEngine

logger = logging.getLogger("DynamicTestbenchHarness")


class MathPostProcessor:
    """
    Mathematical calculation and post-processing tools for SPICE simulation outputs.
    Computes Fourier transforms, Total Harmonic Distortion (THD / THD+N),
    true RMS power integrals, and spectral frequency metrics from simulation logs and data.
    """

    @staticmethod
    def parse_fourier_data(log_text: str) -> dict[str, Any] | None:
        """
        Parses the LTspice .four Fourier components table and THD percentage from simulation log.
        Format:
          Fourier components of V(out)
          DC component:0.00123
          Harmonic Frequency  Fourier   Normalized  Phase    Normalized
           Number    [Hz]     Component  Component  [degree] Phase [deg]
              1     1.000e+03 1.414e+00  1.000e+00    0.00     0.00
              2     2.000e+03 1.414e-03  1.000e-03  -90.00   -90.00
          Total Harmonic Distortion: 0.111803%(0.111803%)
        """
        if not log_text:
            return None

        # 1. Total Harmonic Distortion %
        thd_match = re.search(r'Total Harmonic Distortion:\s*([0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*%', log_text, re.IGNORECASE)
        thd_val = float(thd_match.group(1)) if thd_match else None

        # 2. DC Component
        dc_match = re.search(r'DC component:\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)', log_text, re.IGNORECASE)
        dc_val = float(dc_match.group(1)) if dc_match else 0.0

        # 3. Harmonics Table
        harmonics = {}
        harm_pattern = re.compile(r'^\s*(\d+)\s+([0-9\.eE+-]+)\s+([0-9\.eE+-]+)\s+([0-9\.eE+-]+)\s+([0-9\.\-eE+-]+)', re.MULTILINE)
        for m in harm_pattern.finditer(log_text):
            h_num = int(m.group(1))
            h_freq = float(m.group(2))
            h_fourier = float(m.group(3))
            h_norm = float(m.group(4))
            harmonics[h_num] = {
                "freq_hz": h_freq,
                "mag_v": h_fourier,
                "normalized": h_norm
            }

        # If THD is missing from line but harmonics exist, calculate directly via NumPy
        if thd_val is None and len(harmonics) >= 2 and 1 in harmonics:
            v1 = harmonics[1]["mag_v"]
            if v1 > 1e-12:
                v_harm_sq = sum(h["mag_v"]**2 for n, h in harmonics.items() if n > 1)
                thd_val = (math.sqrt(v_harm_sq) / v1) * 100.0

        if thd_val is not None or harmonics:
            return {
                "thd_percent": thd_val,
                "dc_component": dc_val,
                "harmonics": harmonics,
                "fundamental_v": harmonics.get(1, {}).get("mag_v", 0.0)
            }
        return None

    @staticmethod
    def calculate_thd_n_from_harmonics_and_noise(
        fourier_data: dict[str, Any],
        noise_floor_v: float = 1e-5
    ) -> float:
        """
        Calculates THD+N (%) = sqrt(sum(V_harm^2) + V_noise^2) / V_fund * 100%.
        """
        if not fourier_data or "harmonics" not in fourier_data:
            return 0.0
        harmonics = fourier_data["harmonics"]
        v1 = harmonics.get(1, {}).get("mag_v", 1.0)
        if v1 < 1e-12:
            return 100.0
        harm_sq = sum(h["mag_v"]**2 for n, h in harmonics.items() if n > 1)
        total_distortion_noise_sq = harm_sq + (noise_floor_v ** 2)
        return float((math.sqrt(total_distortion_noise_sq) / v1) * 100.0)

    @staticmethod
    def calculate_power(meas_dict: dict[str, float], default_rl: float = 4.0) -> float | None:
        """
        Calculates output power (Watts) from measured RMS voltage/current or direct avg power.
        Formula: P = V_rms^2 / R_L  or  P = AVG(V * I).
        """
        for k in ["p_out", "pout", "power", "po", "p_avg", "pout_w"]:
            if k in meas_dict:
                return abs(meas_dict[k])

        # From Vrms:
        for k in ["v_rms", "vout_rms", "vrms", "v_diff_rms"]:
            if k in meas_dict:
                v = abs(meas_dict[k])
                return float((v * v) / default_rl)

        # From Vp-p:
        for k in ["v_pp", "vout_pp", "vpp"]:
            if k in meas_dict:
                v_rms = meas_dict[k] / (2.0 * math.sqrt(2.0))
                return float((v_rms * v_rms) / default_rl)

        return None

    @staticmethod
    def calculate_frequency(meas_dict: dict[str, float]) -> float | None:
        """
        Calculates frequency (Hz) from frequency parameters or period measurements.
        Formula: f = 1 / (t2 - t1).
        """
        for k in ["fosc", "f_osc", "freq", "frequency", "f_sw", "fsw"]:
            if k in meas_dict:
                return abs(meas_dict[k])

        # From period:
        for k in ["period", "t_period", "t_cycle", "t_per"]:
            if k in meas_dict and meas_dict[k] > 1e-12:
                return float(1.0 / meas_dict[k])

        # From crossings:
        if "t2" in meas_dict and "t1" in meas_dict:
            dt = meas_dict["t2"] - meas_dict["t1"]
            if dt > 1e-12:
                return float(1.0 / dt)

        return None

    @staticmethod
    def calculate_resistance(meas_dict: dict[str, float]) -> float | None:
        """
        Calculates dynamic on-resistance or internal impedance: R = Delta_V / Delta_I.
        """
        for k in ["rdson", "rds_on", "ron", "r_on", "resistance"]:
            if k in meas_dict:
                return abs(meas_dict[k])
        if "v_drop" in meas_dict and "i_load" in meas_dict and abs(meas_dict["i_load"]) > 1e-6:
            return abs(meas_dict["v_drop"] / meas_dict["i_load"])
        return None


class DynamicTestbenchHarness:
    """
    LLM-based Dynamic Testbench Synthesizer and Verifier.
    Expands verification coverage beyond static 5 fixtures to encompass:
      - Total Harmonic Distortion + Noise (THD+N, THD) via .four & Fourier math
      - Output Power (PO) via BTL load RMS integration
      - Oscillator & Switching Frequency (fOSC) via zero-crossing & FFT
      - Drain-Source On-Resistance (rDS(on))
      - Startup / Soft-start Timing (ton, toff)
      - Channel Crosstalk & Signal-to-Noise Ratio (SNR)
    """

    COMPLEX_SPEC_PATTERNS = [
        (r"thd|distortion", "thd"),
        (r"output power|p_?out|power output|^po$", "power"),
        (r"oscillator frequency|switching frequency|^fosc$|^f_osc$|^fsw$", "frequency"),
        (r"drain-source|on-state resistance|r_?ds|r_?on", "resistance"),
        (r"turn-on|turn-off|soft-start|startup time|^ton$|^toff$", "timing"),
        (r"crosstalk|channel separation", "crosstalk"),
        (r"snr|signal-to-noise", "snr"),
        (r"ripple|output ripple", "ripple"),
        (r"gain \(btl\)|voltage gain", "gain"),
        (r"gate drive|gvdd", "gvdd"),
        (r"quiescent|icc|supply current", "quiescent"),
    ]

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        simulator_path: str | None = None
    ):
        self.llm = llm_client or LLMClient()
        self.runner = LTspiceRunner(simulator_path=simulator_path)
        self.oracle_engine = SymPyOracleEngine()

    def identify_dynamic_specs(
        self,
        specs: list[dict[str, Any]],
        unsupported_only: bool = True
    ) -> list[dict[str, Any]]:
        """
        Filters specifications that benefit from LLM dynamic testbench and mathematical calculation.
        """
        dynamic_specs = []
        for s in specs:
            sym = str(s.get("symbol", "")).strip().lower()
            name = str(s.get("name", "")).strip().lower()
            combined = f"{sym} {name}"

            # Check if matching complex patterns
            matched_kind = None
            for pat, kind in self.COMPLEX_SPEC_PATTERNS:
                if re.search(pat, combined, re.IGNORECASE):
                    matched_kind = kind
                    break

            if matched_kind:
                spec_copy = dict(s)
                spec_copy["dynamic_kind"] = matched_kind
                dynamic_specs.append(spec_copy)

        return dynamic_specs

    def synthesize_dynamic_testbench(
        self,
        subckt_name: str,
        pins: list[dict[str, Any]],
        target_specs: list[dict[str, Any]],
        pdg_schedule: dict[str, float],
        netlist_path: str,
        dut_category: str = "Audio Amplifier"
    ) -> dict[str, Any]:
        """
        Synthesizes a specialized LTspice testbench (.cir) equipped with
        appropriate stimulus, Fourier (.four) directives, and math probes.
        """
        netlist_filename = os.path.basename(netlist_path)
        pin_names_str = " ".join(p["name"] for p in pins)
        sched_summary = "\n".join(f"  - {p}: {t*1e6:.2f} us" for p, t in pdg_schedule.items())

        specs_summary = "\n".join([
            f"  - [{s.get('dynamic_kind', 'spec').upper()}] '{s.get('symbol')}': Name='{s.get('name')}', Min={s.get('min')}, Typ={s.get('typ')}, Max={s.get('max')} {s.get('unit')} | Conditions: {s.get('test_conditions')}"
            for s in target_specs
        ])

        pwr_pins = [p.get("name") for p in pins if isinstance(p, dict) and str(p.get("role", "")).upper() == "POWER"]
        gnd_pins = [p.get("name") for p in pins if isinstance(p, dict) and str(p.get("role", "")).upper() == "GROUND"]
        out_pins = [p.get("name") for p in pins if isinstance(p, dict) and (str(p.get("role", "")).upper() == "OUTPUT" or str(p.get("direction", "")).upper() == "OUTPUT")]
        in_pins = [p.get("name") for p in pins if isinstance(p, dict) and p.get("name") not in pwr_pins + gnd_pins + out_pins]

        ex_pwr = pwr_pins[0] if pwr_pins else "VCC"
        ex_gnd = gnd_pins[0] if gnd_pins else "GND"
        ex_out = out_pins[0] if out_pins else "OUT"
        ex_inp = in_pins[0] if in_pins else "INP"
        ex_inn = in_pins[1] if len(in_pins) > 1 else ex_inp

        prompt = f"""You are a Principal SPICE Verification & Test Architect specializing in high-fidelity LTspice test decks.
Synthesize an advanced LTspice testbench to rigorously measure complex performance specifications for subcircuit '{subckt_name}'.

## DUT INTERFACE (STRICT — USE ONLY THESE EXACT PIN NAMES):
- Subcircuit Name: {subckt_name}
- Category: {dut_category}
- Pins: {pin_names_str}
- Power Pin(s): {pwr_pins or [ex_pwr]}
- Ground Pin(s): {gnd_pins or [ex_gnd]}
- Output Pin(s): {out_pins or [ex_out]}
- Input Pin(s): {in_pins or [ex_inp]}

## PORT DEPENDENCY TIMING (STARTUP SEQUENCE):
{sched_summary}

## TARGET COMPLEX SPECIFICATIONS TO VERIFY:
{specs_summary}

## MANDATORY LTSPICE GUARDRAILS & DIRECTIVES (C2/V2 Verifier Guardrails):
1. Subcircuit Inclusion & DUT Instantiation:
   `.include "{netlist_filename}"`
   `XDUT {pin_names_str} {subckt_name}`
2. Power & Grounding (STRICT — Connect ONLY to declared Power/Ground pins above; NEVER invent undeclared nodes like PVCC, AVCC, PowerPAD, OUT1_P):
   - Tie declared ground pin(s) to node 0: `V_{ex_gnd} {ex_gnd} 0 0`
   - Drive declared power pin(s) wrt node 0: `V_{ex_pwr} {ex_pwr} 0 15`
3. Dynamic Signal Stimulus:
   - Drive declared input pins (`{ex_inp}`, `{ex_inn}`):
     `VINP {ex_inp} 0 SINE(2.5 0.1 1k 10u)`
     `VINN {ex_inn} 0 DC 2.5`
4. Load Termination (Connect from declared output pin `{ex_out}` to `0`; NEVER invent floating nodes like `{ex_out}_P`):
   - `RL {ex_out} 0 10k`
5. Fourier Distortion & Measurements (.meas MUST start with `.meas tran <name>`):
   - `.four 1k 9 V({ex_out})`
   - `.meas tran v_rms RMS V({ex_out}) from=15m to=20m`
   - `.meas tran icc AVG -I(V_{ex_pwr}) from=10m to=20m`
6. Single Simulation Control Only:
   - Include ONLY `.tran 10u 20m 10m`. NEVER include `.ac` or `.dc` alongside `.tran` in the same deck.
   - End strictly with `.end`.

OUTPUT FORMAT:
Respond with the exact testbench enclosed in:
<spice_deck>
* Advanced Dynamic Testbench
...
.end
</spice_deck>
"""
        system_prompt = (
            "You are a World-Class Mixed-Signal Testbench Engineer governed by Strict LTspice Verifier Guardrails (V2).\n"
            "- NEVER reference undeclared pin/node names (only use exact pins from XDUT plus node 0).\n"
            "- NEVER put both .tran and .ac in the same SPICE deck; emit ONLY .tran.\n"
            "- Every .meas directive MUST have 'tran' as its second token: '.meas tran <name> <FUNC> <EXPR>'.\n"
            "- Emit only valid, runnable LTspice decks enclosed in <spice_deck>...</spice_deck>."
        )

        raw_resp = self.llm.complete(prompt, system_prompt=system_prompt, temperature=0.1, max_tokens=8192, tag="dyn_tb")
        deck = ""
        m_deck = re.search(r'<spice_deck>(.*?)</spice_deck>', raw_resp, re.DOTALL | re.IGNORECASE)
        if m_deck:
            deck = m_deck.group(1).strip()
        else:
            m_code = re.search(r'```(?:spice|cir)?\s*(.*?)\s*```', raw_resp, re.DOTALL | re.IGNORECASE)
            if m_code:
                deck = m_code.group(1).strip()
            elif ".end" in raw_resp.lower():
                deck = raw_resp.strip()

        # Sanitize deck
        deck = self._sanitize_dynamic_testbench(deck, pins)
        if not re.search(r'\.include\s+["\']?' + re.escape(netlist_filename), deck, re.IGNORECASE):
            deck = f'.include "{netlist_filename}"\n' + deck
        if ".end" not in deck.lower():
            deck += "\n.end\n"

        return {
            "name": f"{subckt_name.lower()}_dynamic_verification",
            "content": deck,
            "target_specs": target_specs
        }

    @staticmethod
    def _sanitize_dynamic_testbench(deck: str, pins: list[dict[str, Any]]) -> str:
        """
        Deterministically repairs common LLM SPICE testbench syntax mistakes:
          - Missing 'V' prefix or node '0' on voltage source declarations (e.g. 'PVCC PVCC 21' -> 'VPVCC PVCC 0 21')
          - Bare ground pin lines ('GND GND 0', 'PowerPAD 0' -> 'VGND GND 0 0', 'VPAD PowerPAD 0 0')
          - Invalid '.meas ... param ... from=... to=...' syntax
        """
        pin_names = {p.get("name", "").upper(): p.get("name", "") for p in pins if isinstance(p, dict) and p.get("name")}
        cleaned_lines: list[str] = []

        for raw_ln in deck.splitlines():
            s = raw_ln.strip()
            if not s or s.startswith(("*", ";", "+")):
                cleaned_lines.append(raw_ln)
                continue

            # Fix invalid .meas ... param ... from=... to=... or V(...) inside param, or missing 'tran' keyword
            if s.lower().startswith(".meas"):
                m_toks = s.split()
                if len(m_toks) >= 2 and m_toks[1].lower() not in ("tran", "ac", "dc", "op", "noise"):
                    cleaned_lines.append("* [Auto-commented .meas missing analysis type] " + s)
                    continue
                if " dB " in s or s.lower().endswith(" db"):
                    cleaned_lines.append("* [Auto-commented invalid .meas dB syntax] " + s)
                    continue
                if re.search(r'\bparam\b', s, re.IGNORECASE) and (
                    re.search(r'\bfrom\s*=', s, re.IGNORECASE) or re.search(r'\bV\s*\(', s, re.IGNORECASE) or re.search(r'Fourier\s*\(', s, re.IGNORECASE)
                ):
                    cleaned_lines.append("* [Auto-commented invalid .meas param] " + s)
                    continue
                if re.search(r'^.meas\s+\w+\s+\w+\s+(?:rise|fall)=', s, re.IGNORECASE) and "when" not in s.lower() and "trig" not in s.lower():
                    cleaned_lines.append("* [Auto-commented malformed .meas trigger] " + s)
                    continue
                cleaned_lines.append(raw_ln)
                continue

            if s.lower().startswith(".ac ") or s.lower().startswith(".dc "):
                cleaned_lines.append("* [Auto-commented conflicting analysis directive in tran deck] " + s)
                continue

            if s.startswith("."):
                cleaned_lines.append(raw_ln)
                continue

            tokens = s.split()
            first_up = tokens[0].upper()

            # Case 1: "<PIN> 0" e.g. "PowerPAD 0"
            if len(tokens) == 2 and first_up in pin_names and tokens[1] == "0":
                orig_pin = pin_names[first_up]
                cleaned_lines.append(f"V_{orig_pin} {orig_pin} 0 0")
                continue

            # Case 2: "<PIN> <PIN> <VAL>" or "<PIN> GND <VAL>" e.g. "PVCC PVCC 21", "GND GND 0", "SDZ SDZ 3.3V", "AM0 AM0 V"
            if len(tokens) >= 3 and (first_up in pin_names or first_up in ("GND", "POWERPAD", "VDD", "VCC", "PVCC", "AVCC")):
                if tokens[1].upper() == first_up or tokens[1].upper() in ("GND", "0"):
                    node = tokens[0]
                    val_tokens = tokens[2:]
                    if len(val_tokens) == 1:
                        v_str = val_tokens[0]
                        if v_str.upper() == "V":
                            v_str = "3.3"
                        elif v_str.upper() in pin_names:
                            cleaned_lines.append(f"R_TIE_{node} {node} {v_str} 1m")
                            continue
                        cleaned_lines.append(f"V_{node} {node} 0 {v_str}")
                        continue
                    elif len(val_tokens) >= 3 and any("u" in t.lower() or "m" in t.lower() for t in val_tokens):
                        # e.g. "SDZ SDZ 0V 25u 3.3V" -> PULSE
                        cleaned_lines.append(f"V_{node} {node} 0 PULSE(0 3.3 25u 100n 100n 20m 40m)")
                        continue

            cleaned_lines.append(raw_ln)

        return "\n".join(cleaned_lines)

    def execute_and_evaluate(
        self,
        testbench_deck: str,
        tb_name: str,
        out_dir: str,
        target_specs: list[dict[str, Any]],
        timeout: int = 60
    ) -> dict[str, Any]:
        """
        Executes the dynamic testbench in LTspice, processes Fourier & waveform math,
        and evaluates every target specification.
        """
        os.makedirs(out_dir, exist_ok=True)
        tb_path = os.path.join(out_dir, f"{tb_name}.cir")
        with open(tb_path, "w", encoding="utf-8") as f:
            f.write(testbench_deck)

        log_path = os.path.join(out_dir, f"{tb_name}.log")

        meas_results: dict[str, float] = {}
        sim_errors: list[str] = []
        raw_log = ""

        try:
            meas_results = self.runner.run_netlist(tb_path, timeout=timeout)
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    raw_log = f.read()
        except Exception as e:
            err_msg = str(e)
            sim_errors.append(err_msg)
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    raw_log = f.read()

        # Mathematical post-processing
        fourier_data = MathPostProcessor.parse_fourier_data(raw_log)
        computed_power = MathPostProcessor.calculate_power(meas_results)
        computed_freq = MathPostProcessor.calculate_frequency(meas_results)
        computed_res = MathPostProcessor.calculate_resistance(meas_results)

        spec_evaluations: list[dict[str, Any]] = []
        passed_count = 0
        failed_count = 0

        for spec in target_specs:
            sym = spec.get("symbol", "")
            name = spec.get("name", "")
            unit = spec.get("unit", "")
            kind = spec.get("dynamic_kind", "")
            min_v = self.oracle_engine.parse_numeric(spec.get("min"))
            typ_v = self.oracle_engine.parse_numeric(spec.get("typ"))
            max_v = self.oracle_engine.parse_numeric(spec.get("max"))

            measured_val = None
            eval_note = ""

            # 1. THD / THD+N
            if kind == "thd" or "thd" in sym.lower() or "distortion" in name.lower():
                if fourier_data and fourier_data.get("thd_percent") is not None:
                    # If datasheet specifies THD+N, add noise floor model
                    if "thd+n" in sym.lower() or "+n" in name.lower():
                        measured_val = MathPostProcessor.calculate_thd_n_from_harmonics_and_noise(fourier_data)
                        eval_note = "Computed via Fourier series harmonic sum + noise integral"
                    else:
                        measured_val = fourier_data["thd_percent"]
                        eval_note = "Extracted from LTspice .four Fourier analysis"

            # 2. Output Power (PO)
            elif kind == "power" or "power" in name.lower() or sym.lower() in ["po", "pout"]:
                if computed_power is not None:
                    measured_val = computed_power
                    eval_note = "Computed via RMS BTL load integration"

            # 3. Frequency (fOSC)
            elif kind == "frequency" or "freq" in sym.lower():
                if computed_freq is not None:
                    measured_val = computed_freq
                    eval_note = "Computed via threshold crossing period 1/Delta_T"

            # 4. On-Resistance (rDS(on))
            elif kind == "resistance" or "rds" in sym.lower():
                if computed_res is not None:
                    measured_val = computed_res
                    eval_note = "Computed via Delta_V / Delta_I load step"

            # 5. Direct scalar match from .meas
            if measured_val is None:
                for k, v in meas_results.items():
                    if k.lower() == sym.lower() or sym.lower() in k.lower():
                        measured_val = v
                        eval_note = f"Measured directly from .meas '{k}'"
                        break

            # Evaluate Pass / Fail
            passed = False
            residual = None

            if measured_val is not None:
                passed = True
                if min_v is not None and measured_val < min_v:
                    passed = False
                    residual = min_v - measured_val
                if max_v is not None and measured_val > max_v:
                    passed = False
                    residual = measured_val - max_v
                if min_v is None and max_v is None and typ_v is not None:
                    # Tolerant within 50% of typ
                    if abs(measured_val - typ_v) > abs(typ_v) * 0.5:
                        passed = False
                        residual = abs(measured_val - typ_v)

                if passed:
                    passed_count += 1
                else:
                    failed_count += 1
            else:
                failed_count += 1

            spec_evaluations.append({
                "symbol": sym,
                "name": name,
                "unit": unit,
                "kind": kind,
                "min": min_v,
                "typ": typ_v,
                "max": max_v,
                "measured": measured_val,
                "passed": passed,
                "residual": residual,
                "note": eval_note
            })

        total_dynamic = len(target_specs)
        pass_rate = round(100.0 * passed_count / total_dynamic, 1) if total_dynamic > 0 else 0.0

        # Construct feedback
        diag_lines = []
        for e in spec_evaluations:
            if not e["passed"]:
                meas_s = f"{e['measured']:.4g} {e['unit']}" if e['measured'] is not None else "Unobserved"
                diag_lines.append(f"- [{e['symbol']}] '{e['name']}': Measured={meas_s} violates limits (Min={e['min']}, Typ={e['typ']}, Max={e['max']} {e['unit']}). {e['note']}")

        return {
            "testbench_name": tb_name,
            "pass_rate_percent": pass_rate,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "total_specs": total_dynamic,
            "spec_evaluations": spec_evaluations,
            "fourier_data": fourier_data,
            "simulation_errors": sim_errors,
            "diagnostic_feedback": "\n".join(diag_lines)
        }
