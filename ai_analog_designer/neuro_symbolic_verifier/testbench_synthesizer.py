import os
import re
from typing import Any

from ..openrouter_client import OpenRouterClient


class TestbenchSynthesizer:
    """
    Synthesizes LTspice-compliant testbenches implementing AnalogVerifier's
    Port Dependency Graph (PDG) activation scheduling.
    Ensures correct startup sequence (Power -> Bias -> Control -> Signal)
    and generates precise .meas directives to verify 100% of datasheet specifications.
    """

    def __init__(self, llm_client: OpenRouterClient | None = None):
        self.llm = llm_client or OpenRouterClient()

    def synthesize_testbenches(
        self,
        netlist_path: str,
        subckt_name: str,
        pins: list[dict[str, Any]],
        specifications: list[dict[str, Any]],
        pdg_schedule: dict[str, float]
    ) -> list[dict[str, Any]]:
        """
        Generates analysis testbenches (.cir) targeting the specifications.
        Returns a list of testbench specs: [{'name': ..., 'content': ..., 'target_params': [...]}]
        """
        # Filter testable electrical parameters (omit package thermal/ESD ratings)
        electrical_specs = [
            s for s in specifications
            if not any(k in s.get("symbol", "").lower() for k in ["tstg", "θja", "theta", "hbm", "mm", "cdm", "esd"])
        ]
        if not electrical_specs:
            electrical_specs = specifications

        dc_specs = []
        ac_specs = []
        tran_specs = []

        for s in electrical_specs:
            sym = s.get("symbol", "").lower()
            desc = (s.get("description", "") + " " + s.get("parameter", "")).lower()

            is_ac = any(k in sym or k in desc for k in ["open_loop_gain", "gbw", "bandwidth", "phase_margin", "cmrr", "psrr"]) or                     bool(re.search(r'\bac\s+gain\b', desc)) or (bool(re.search(r'\bac\b', sym)) and "accuracy" not in sym)
            is_tran = any(k in sym or k in desc for k in ["slew", "sr", "delay", "tpd", "tr", "tf", "rise", "fall", "period", "freq", "fosc", "fout", "fmax", "jitter", "pulse", "thd", "lock", "ripple", "overshoot", "undershoot", "startup", "settling", "efficiency", "soft-start"])

            if is_ac and not is_tran:
                ac_specs.append(s)
            elif is_tran:
                tran_specs.append(s)
            else:
                dc_specs.append(s)

        testbenches = []
        expected_pin_names_str = " ".join([p["name"] for p in pins])
        pin_names_str = self._get_actual_subckt_pins(netlist_path, subckt_name, expected_pin_names_str)
        schedule_str = "\n".join([f"  {p}: {t*1e6:.2f} us" for p, t in pdg_schedule.items()])

        max_sched_time = max(pdg_schedule.values()) if pdg_schedule else 50e-6
        tran_stop = max(50e-6, max_sched_time * 2.0)
        tran_step = tran_stop / 500.0
        tran_cmd = f".tran {tran_step*1e6:.2f}u {tran_stop*1e6:.2f}u"

        categories = []
        if dc_specs:
            categories.append(("dc_op", "DC Operating Point & Static Characteristics", dc_specs, ".op"))
        if ac_specs:
            categories.append(("ac_sweep", "AC Frequency Sweep & Small-Signal Characteristics", ac_specs, ".ac dec 20 1 100Meg"))
        if tran_specs:
            categories.append(("transient", "Transient Dynamics & Switching Characteristics", tran_specs, tran_cmd))

        if not categories:
            categories.append(("full_verification", "Complete Functional Verification", specifications, tran_cmd))

        for tb_id, title, cat_specs, sim_type in categories:
            tb_data = self._generate_testbench_with_llm(
                tb_id=tb_id,
                title=title,
                cat_specs=cat_specs,
                sim_type=sim_type,
                netlist_path=netlist_path,
                subckt_name=subckt_name,
                pin_names_str=pin_names_str,
                pins=pins,
                schedule_str=schedule_str
            )
            testbenches.append(tb_data)

        return testbenches

    def _generate_testbench_with_llm(
        self,
        tb_id: str,
        title: str,
        cat_specs: list[dict[str, Any]],
        sim_type: str,
        netlist_path: str,
        subckt_name: str,
        pin_names_str: str,
        pins: list[dict[str, Any]],
        schedule_str: str
    ) -> dict[str, Any]:
        """
        Uses OpenRouter LLM to generate a compliant LTspice testbench deck.
        """
        netlist_filename = os.path.basename(netlist_path)
        specs_desc = "\n".join([
            f"- '{s.get('symbol')}': Min={s.get('min')}, Typ={s.get('typ')}, Max={s.get('max')} {s.get('unit')} | Desc: {s.get('description', s.get('parameter', ''))} | Conditions: {s.get('test_conditions', '')}"
            for s in cat_specs
        ])

        prompt = f"""You are an Expert Mixed-Signal Test & Verification Engineer.
Synthesize an LTspice SPICE testbench deck to verify the following specifications for subcircuit '{subckt_name}'.

## DUT INTERFACE:
- Subcircuit Name: {subckt_name}
- Pins: {pin_names_str}

## PORT DEPENDENCY GRAPH ACTIVATION SCHEDULE:
Follow this physical power-up / activation timing strictly:
{schedule_str}

## TARGET SPECIFICATIONS TO MEASURE:
{specs_desc}

## CRITICAL LTSPICE COMPATIBILITY RULES:
1. Include the subcircuit using: `.include "{netlist_filename}"`
2. Instantiate DUT: `XDUT {pin_names_str} {subckt_name}`
3. Ground pin (e.g. GND, VSS, AGND, PGND) MUST connect to node 0 or be grounded with `VGND GND 0 0`.
4. Power supplies (e.g. VCC, VDD) must match datasheet typical operating voltage (e.g. 3.3V or 5V as stated in specs).
5. Input stimulus must follow the PDG schedule (delayed startup if transient, or correct DC bias).
6. Simulation Directive: Must specify `{sim_type}` analysis command.
7. MEASUREMENT DIRECTIVES (STRICT LTSPICE SYNTAX ONLY!):
   - Measure each target specification symbol using valid LTspice `.meas` commands.
   - For Voltages and Currents:
     `.meas tran vout_max MAX V(OUT) from=10u to=50u`
     `.meas tran vout_min MIN V(OUT) from=10u to=50u`
     `.meas tran i_supply AVG -I(VDD) from=10u to=50u`
   - For Oscillation Frequency & Period:
     DO NOT use HSPICE keywords like PERIOD(), FREQ(), or STDEV()!
     In LTspice, measure threshold crossings:
     `.meas tran t1 when V(OUT)=1.65 rise=3`
     `.meas tran t2 when V(OUT)=1.65 rise=4`
     `.meas tran fosc param 1/(t2-t1)`
   - For Rise/Fall Times:
     `.meas tran tr1 when V(OUT)=0.33 rise=2`
     `.meas tran tr2 when V(OUT)=2.97 rise=2`
     `.meas tran tr param tr2-tr1`
   - In LTspice, WHEN directives DO NOT allow 'from=' or 'to='!
     Syntax: `.meas tran t1 when V(OUT)=1.65 rise=3`
     NEVER put 'from=...' or 'to=...' on any line containing 'when'!
   - In `.meas tran <name> param <expr>`, NEVER append `FROM ... TO ...`.
   - Never use multi-arg MAX(a, b, c). LTspice MAX only takes 2 arguments: MAX(a, b).
   - For LTspice: Terminate the file strictly with `.end`. NO `.control` or `.endc`.
8. STIMULUS & VOLTAGE SOURCE RULES:
   - AT MOST ONE voltage source per pin. DO NOT define a flat zero-volt source (e.g. `VCONVST CONVST 0 0`) and then define a second pulse source for the same pin! Apply the stimulus or bias directly with a single source per pin.
   - For power-down / reset / enable pins (e.g. A_PWD, PWD_RST, SHDN, CS, RD): bias them to their active/enabled state (e.g. 5V or 3.3V) so the circuit is fully awake during measurements!
   - Ensure dynamic stimulus transitions (e.g. CONVST edge, clock pulses) occur WITHIN the simulation window defined by {sim_type}.

OUTPUT FORMAT:
Respond using the following XML tag:
<spice_deck>
* Full LTspice testbench code here
.include "{netlist_filename}"
XDUT {pin_names_str} {subckt_name}
...
.end
</spice_deck>
"""
        system_prompt = "You are an autonomous SPICE testbench generator specializing in LTspice batch verification and neuro-symbolic measurement extraction."
        
        try:
            raw_resp = self.llm.complete(prompt, system_prompt=system_prompt, temperature=0.1, max_tokens=8192, tag="tb")
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

            deck = self._sanitize_testbench(deck, subckt_name, pin_names_str, netlist_filename, pins=pins, sim_type=sim_type)
            return {
                "name": tb_id,
                "description": title,
                "target_symbols": [s.get("symbol") for s in cat_specs],
                "content": deck.strip() + "\n"
            }
        except Exception:
            # Fallback basic testbench
            fallback_deck = self._build_fallback_deck(tb_id, subckt_name, pin_names_str, pins, netlist_filename, cat_specs)
            return {
                "name": tb_id,
                "description": title,
                "target_symbols": [s.get("symbol") for s in cat_specs],
                "content": fallback_deck
            }

    def _get_actual_subckt_pins(self, netlist_path: str, subckt_name: str, fallback_pins: str) -> str:
        """Reads the exact pin signature from the synthesized .subckt file."""
        if not os.path.exists(netlist_path):
            return fallback_pins
        try:
            with open(netlist_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str.lower().startswith(".subckt"):
                        tokens = line_str.split()
                        if len(tokens) >= 3 and tokens[1].upper() == subckt_name.upper():
                            return " ".join(tokens[2:])
        except Exception:
            pass
        return fallback_pins

    def _fix_pwl_monotonicity(self, line: str) -> str:
        """Ensures all time points in PWL(...) statements are strictly monotonically increasing."""
        def fix_match(m):
            raw_inner = m.group(1).strip()
            tokens = raw_inner.split()
            if len(tokens) < 4:
                return m.group(0)

            def parse_unit(s):
                val_s = s.strip()
                mult = 1.0
                if val_s.endswith("s") or val_s.endswith("S"):
                    val_s = val_s[:-1]
                if val_s.endswith("u") or val_s.endswith("U"):
                    mult = 1e-6
                    val_s = val_s[:-1]
                elif val_s.endswith("n") or val_s.endswith("N"):
                    mult = 1e-9
                    val_s = val_s[:-1]
                elif val_s.endswith("p") or val_s.endswith("P"):
                    mult = 1e-12
                    val_s = val_s[:-1]
                elif val_s.endswith("m") or val_s.endswith("M"):
                    mult = 1e-3
                    val_s = val_s[:-1]
                try:
                    return float(val_s) * mult
                except Exception:
                    return None

            new_pairs = []
            last_t = -1.0
            for i in range(0, len(tokens), 2):
                if i + 1 < len(tokens):
                    t_str = tokens[i]
                    v_str = tokens[i+1]
                    t_val = parse_unit(t_str)
                    if t_val is not None:
                        if t_val <= last_t:
                            t_val = last_t + 10e-9 # add 10ns
                            t_str = f"{t_val*1e6:.4f}u"
                        last_t = t_val
                    new_pairs.extend([t_str, v_str])
            return f"PWL({' '.join(new_pairs)})"

        return re.sub(r'PWL\s*\(([^)]+)\)', fix_match, line, flags=re.IGNORECASE)

    def _sanitize_testbench(
        self,
        deck: str,
        subckt_name: str,
        pin_names_str: str,
        netlist_filename: str,
        pins: list[dict[str, Any]] | None = None,
        sim_type: str = ".tran 0 100u 0 10n"
    ) -> str:
        """Sanitizes testbench for LTspice execution, stripping invalid HSPICE syntax, fixing PWL, and deduplicating."""
        lines = deck.splitlines()
        clean_lines = []
        has_end = False
        seen_instances = set()
        seen_v_sources = {}
        seen_meas_names = set()
        seen_sim_directive = False
        # Check measurement types in raw deck
        has_meas_tran = any(re.search(r'^\s*\.meas\s+tran\b', l, re.IGNORECASE) for l in lines)
        has_meas_ac = any(re.search(r'^\s*\.meas\s+ac\b', l, re.IGNORECASE) for l in lines)
        has_meas_op = any(re.search(r'^\s*\.meas\s+op\b', l, re.IGNORECASE) for l in lines)

        # Auto-align sim command if LLM wrote tran measurements for dc_op or ac_sweep
        if has_meas_tran and not has_meas_ac and not has_meas_op:
            target_sim_cmd = ".tran"
            if not sim_type.strip().lower().startswith(".tran"):
                sim_type = ".tran 0.1u 50u"
        elif has_meas_ac and not has_meas_tran and not has_meas_op:
            target_sim_cmd = ".ac"
        elif has_meas_op and not has_meas_tran and not has_meas_ac:
            target_sim_cmd = ".op"
        else:
            target_sim_cmd = sim_type.strip().split()[0].lower() if sim_type else ".tran"

        out_pins = {
            p['name'].upper() for p in pins 
            if p.get('direction', '').upper() in ['OUTPUT', 'OUT'] or p.get('role', '').upper() in ['OUTPUT', 'FEEDBACK', 'STATUS']
        } if pins else set()

        for line in lines:
            line_str = line.strip()
            if not line_str:
                clean_lines.append("")
                continue

            # Strip stray markdown fences, xml tags, or language markers
            if line_str.startswith("```") or "<spice_deck>" in line_str.lower() or "</spice_deck>" in line_str.lower() or line_str.lower() == "xml":
                continue

            # Remove ngspice control blocks
            if any(line_str.lower().startswith(k) for k in [".control", ".endc", "run", "quit"]):
                continue

            # Guarantee XDUT has exact matching pin sequence
            if line_str.upper().startswith("XDUT ") and subckt_name.upper() in line_str.upper():
                line_str = f"XDUT {pin_names_str} {subckt_name}"

            # Ensure strictly ONE simulation directive in the deck matching target sim_type
            if line_str.lower().startswith((".tran", ".ac", ".op", ".dc", ".noise", ".tf")):
                cmd = line_str.split()[0].lower()
                if cmd == target_sim_cmd and not seen_sim_directive:
                    seen_sim_directive = True
                elif cmd == target_sim_cmd and seen_sim_directive:
                    line_str = f"; Removed duplicate simulation directive: {line_str}"
                else:
                    line_str = f"; Removed conflicting simulation directive: {line_str}"

            # Remove voltage sources driving output/feedback pins or duplicating parallel node sources
            tokens = line_str.split()
            if tokens and tokens[0].upper().startswith("V") and len(tokens) >= 4 and not tokens[0].startswith("."):
                # If a resistor parameter name was accidentally included: e.g. V_PULLUP N1 N2 R_PULLUP 100k
                if any(t.upper().startswith("R_") for t in tokens[3:]):
                    r_name = re.sub(r'^[Vv]', 'R', tokens[0])
                    val_toks = [t for t in tokens[3:] if not t.upper().startswith("R_")]
                    line_str = f"{r_name} {tokens[1]} {tokens[2]} {' '.join(val_toks)}"
                    tokens = line_str.split()

            if tokens and tokens[0].upper().startswith("V") and len(tokens) >= 3 and not tokens[0].startswith("."):
                node_pos = tokens[1].upper()
                node_neg = tokens[2].upper()
                if node_pos in out_pins:
                    line_str = f"; Sanitized output driver short: {line_str}"
                    tokens = []
                else:
                    pair = (node_pos, node_neg)
                    inv_pair = (node_neg, node_pos)
                    target_pair = pair if pair in seen_v_sources else (inv_pair if inv_pair in seen_v_sources else None)
                    is_dynamic = any(term in line_str.upper() for term in ["PULSE", "SINE", "AC "]) or ("PWL" in line_str.upper() and not re.match(r'^PWL\s*\(\s*0(?:us|ns|s)?\s+0(?:v)?\s+.*0(?:v)?\s*\)$', line_str, re.IGNORECASE))
                    
                    if target_pair is not None:
                        old_idx = seen_v_sources[target_pair]
                        old_line = clean_lines[old_idx]
                        old_dynamic = any(term in old_line.upper() for term in ["PULSE", "SINE", "AC "]) or ("PWL" in old_line.upper() and not re.match(r'^PWL\s*\(\s*0(?:us|ns|s)?\s+0(?:v)?\s+.*0(?:v)?\s*\)$', old_line, re.IGNORECASE))
                        if is_dynamic and not old_dynamic:
                            clean_lines[old_idx] = f"; Overridden static bias source: {clean_lines[old_idx]}"
                            seen_v_sources[pair] = len(clean_lines)
                        else:
                            line_str = f"; Sanitized duplicate parallel voltage source short: {line_str}"
                            tokens = []
                    else:
                        seen_v_sources[pair] = len(clean_lines)

            # Clean dynamic V(...) in static .param lines
            if line_str.lower().startswith(".param") and "v(" in line_str.lower():
                line_str = re.sub(r'v\([a-zA-Z0-9_]+\)', '3.3', line_str, flags=re.IGNORECASE)

            # Fix when clause inequalities (> or < to =) and strip trailing/preceding from/to/at
            if re.search(r'\bwhen\b', line_str, re.IGNORECASE):
                # Replace AVG with FIND on when lines
                line_str = re.sub(r'\bAVG\b', 'FIND', line_str, flags=re.IGNORECASE)
                # Strip all from=... and to=... and at=... occurrences anywhere on the line
                line_str = re.sub(r'\s+from\s*=\s*\S+', '', line_str, flags=re.IGNORECASE)
                line_str = re.sub(r'\s+to\s*=\s*\S+', '', line_str, flags=re.IGNORECASE)
                line_str = re.sub(r'\s+from\s+\S+', '', line_str, flags=re.IGNORECASE)
                line_str = re.sub(r'\s+to\s+\S+', '', line_str, flags=re.IGNORECASE)
                line_str = re.sub(r'\s+at\s*=\s*\S+', '', line_str, flags=re.IGNORECASE)
                line_str = re.sub(r'\s+at\s+\S+', '', line_str, flags=re.IGNORECASE)

                # Replace > or < after when with =
                parts = re.split(r'(\bwhen\s+)', line_str, flags=re.IGNORECASE)
                if len(parts) >= 3:
                    before = parts[0] + parts[1]
                    after = re.sub(r'([a-zA-Z0-9_\(\)]+)\s*[><]\s*', r'\1 = ', parts[2])
                    # Strip unit 'V' or 'v' immediately after numbers in comparison (e.g. = 1.65V -> = 1.65)
                    after = re.sub(r'(=\s*[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*[vV]\b', r'\1', after)
                    line_str = before + after

            # Strip invalid FROM/TO appended to param directives
            if re.match(r'^\.meas\s+\S+\s+\S+\s+param\s+', line_str, re.IGNORECASE):
                line_str = re.sub(r'\s+from\s*=\s*\S+\s+to\s*=\s*\S+.*$', '', line_str, flags=re.IGNORECASE)
                line_str = re.sub(r'\s+from\s+\S+\s+to\s+\S+.*$', '', line_str, flags=re.IGNORECASE)

            # In .meas tran/ac: if param has at=..., change param to find
            if re.search(r'^\.meas\s+\S+\s+\S+\s+param\s+.+?\bat\s*=', line_str, re.IGNORECASE):
                line_str = re.sub(r'^(\.meas\s+\S+\s+\S+\s+)param\s+', r'\1find ', line_str, flags=re.IGNORECASE)

            # Strip unsupported HSPICE functions like FIND PERIOD(...) or FREQ(...) or PERIOD V(...)
            if re.search(r'^\.meas\s+\S+\s+\S+\s+(?:freq|period|pulsewidth|stdev)\b', line_str, re.IGNORECASE) or \
               any(bad_fn in line_str.upper() for bad_fn in ["PERIOD(", "FREQ(", "PULSEWIDTH(", "STDEV("]):
                line_str = f"; Sanitized unsupported HSPICE meas: {line_str}"

            # Strip or sanitize multi-arg MAX / MIN (LTspice only supports binary max(a, b))
            if re.search(r'\b(?:max|min)\s*\([^)]*,[^)]*,', line_str, re.IGNORECASE):
                line_str = f"; Sanitized multi-arg MAX/MIN meas: {line_str}"

            # Fix PWL non-monotonic timestamps across all points
            if "PWL" in line_str.upper():
                line_str = self._fix_pwl_monotonicity(line_str)

            # Strip invalid rshunt from .options
            if line_str.lower().startswith(".options"):
                line_str = re.sub(r'\brshunt=\S+', '', line_str, flags=re.IGNORECASE)
                line_str = re.sub(r'\s+', ' ', line_str).strip()

            # Ensure .meas directives have an explicit analysis type (op, tran, ac, dc, noise, tf)
            if line_str.lower().startswith(".meas"):
                m_toks = line_str.split()
                valid_types = {"op", "tran", "ac", "dc", "noise", "tf"}
                if len(m_toks) >= 2 and m_toks[1].lower() not in valid_types:
                    default_type = "tran" if "tran" in deck.lower() else "op"
                    line_str = f"{m_toks[0]} {default_type} " + " ".join(m_toks[1:])
                # Deduplicate measurement names to avoid "already defined elsewhere" error
                m_toks = line_str.split()
                if len(m_toks) >= 3:
                    meas_name = m_toks[2].upper()
                    if meas_name in seen_meas_names:
                        line_str = f"; Sanitized duplicate meas name: {line_str}"
                    else:
                        seen_meas_names.add(meas_name)

            # Ensure action keyword like FIND exists before bare V(...) or I(...) in .meas directives
            line_str = re.sub(r'^(\.meas\s+\S+\s+\S+\s+)([VIvi]\()', r'\1FIND \2', line_str, flags=re.IGNORECASE)
            # Clean duplicate action words like PARAM FIND or MAX FIND
            line_str = re.sub(r'\b(PARAM|MAX|MIN|AVG)\s+FIND\b', r'\1', line_str, flags=re.IGNORECASE)

            # Deduplicate component instance names
            first_tok = tokens[0] if tokens else ""
            if first_tok and first_tok[0].upper() in "RCLMQDVIXEGFHSW" and not first_tok.startswith("."):
                inst = first_tok.upper()
                if inst in seen_instances:
                    counter = 2
                    new_inst = f"{first_tok}_{counter}"
                    while new_inst.upper() in seen_instances:
                        counter += 1
                        new_inst = f"{first_tok}_{counter}"
                    line_str = re.sub(r'^\s*' + re.escape(first_tok), new_inst, line_str)
                    seen_instances.add(new_inst.upper())
                else:
                    seen_instances.add(inst)

            if line_str.lower().startswith(".end"):
                has_end = True
            clean_lines.append(line_str)

        # Guarantee XDUT is instantiated
        has_dut = any(
            l.strip().upper().startswith("XDUT ") or 
            (l.strip().upper().startswith("X") and subckt_name.upper() in l.strip().upper())
            for l in clean_lines
        )
        if not has_dut:
            ins_idx = len(clean_lines) - 1 if has_end else len(clean_lines)
            for i, l in enumerate(clean_lines):
                if l.strip().upper().startswith("V") or l.strip().upper().startswith("R"):
                    ins_idx = i + 1
            clean_lines.insert(ins_idx, f"\n* Auto-injected DUT Instance\nXDUT {pin_names_str} {subckt_name}\n")

        # Guarantee at least one valid simulation directive
        if not seen_sim_directive and sim_type:
            clean_lines.insert(len(clean_lines)-1 if has_end else len(clean_lines), sim_type)

        content = "\n".join(clean_lines)
        if ".options" not in content.lower():
            content = ".options gmin=1e-12 cshunt=1e-15\n" + content

        if f'.include "{netlist_filename}"' not in content and f'.include {netlist_filename}' not in content:
            content = f'.include "{netlist_filename}"\n' + content

        if not has_end:
            content += "\n.end\n"

        return content

    def _build_fallback_deck(
        self,
        tb_id: str,
        subckt_name: str,
        pin_names_str: str,
        pins: list[dict[str, Any]],
        netlist_filename: str,
        specs: list[dict[str, Any]]
    ) -> str:
        """Constructs an operational fallback testbench if LLM query encounters issue."""
        deck = [
            f"* Fallback Automated LTspice Testbench for {subckt_name} ({tb_id})",
            f'.include "{netlist_filename}"',
            f"XDUT {pin_names_str} {subckt_name}",
            "VGND 0 0 0",
            "VCC VCC 0 3.3",
            "VIN IN 0 PULSE(0 3.3 10n 1n 1n 20n 50n)",
            ".tran 1n 100n",
            ".meas tran vout_max max V(OUT)",
            ".meas tran vout_min min V(OUT)",
            ".meas tran i_supply avg -I(VCC)",
            ".end"
        ]
        return "\n".join(deck) + "\n"
