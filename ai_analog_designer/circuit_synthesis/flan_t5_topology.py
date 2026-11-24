"""
Topology Candidate Explorer (FLAN-T5 + Modular Block Library).
Integrates jiyun's FLAN-T5 structure generator (when EDAI_MODEL_DIR & torch/transformers
are present) with jiyun's curated modular op-amp block assembler (`data/opamp_blocks/`),
producing rule-validated structure tables ready for `gm_id_sizer`.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .gm_id_sizer import (
    auto_size,
    circuit_to_table,
    parse_ngspice_subckt,
    parse_table_text,
    rule_problems,
    table_text,
)

BLOCKS_DIR = Path(__file__).resolve().parent / "data" / "opamp_blocks"
CARDS_FILE = BLOCKS_DIR / "cards.json"

ROLES = ("stage1", "stage2", "compensation")
BIAS_NETS = {"nb": "nb", "pb": "pb", "vbn": "vbn2", "vbp": "vbp2", "vbt": "vbt"}
FIXED_NETS = {
    "supply_p": "VDD",
    "supply_n": "VSS",
    "in_plus": "INP",
    "in_minus": "INN",
    "out": "OUT",
    "comp_b": "OUT",
}
NODE_COUNT = {"X": 4, "R": 2, "C": 2}

# Built-in canonical structure table templates (always available even without FLAN-T5 weights)
BUILTIN_STRUCTURE_TEMPLATES: list[dict[str, str]] = [
    {
        "name": "two_stage_miller_pmos_input",
        "description": "Two-stage Miller-compensated CMOS op-amp with PMOS differential input pair and Class-A output",
        "table": (
            "PM1 D=N1 G=IN1 S=N3 B=VDD; PM2 D=N2 G=IN2 S=N3 B=VDD; "
            "PM3 D=N3 G=N4 S=VDD B=VDD; PM4 D=N4 G=N4 S=VDD B=VDD; "
            "PM5 D=OUT G=N4 S=VDD B=VDD; "
            "NM1 D=N1 G=N1 S=VSS B=VSS; NM2 D=N2 G=N1 S=VSS B=VSS; "
            "NM3 D=N4 G=N4 S=VSS B=VSS; NM4 D=OUT G=N2 S=VSS B=VSS; "
            "R1 P=N2 N=N5; C1 P=N5 N=OUT"
        ),
    },
    {
        "name": "two_stage_miller_nmos_input",
        "description": "Two-stage Miller-compensated CMOS op-amp with NMOS differential input pair",
        "table": (
            "PM1 D=N1 G=N1 S=VDD B=VDD; PM2 D=N2 G=N1 S=VDD B=VDD; "
            "PM3 D=OUT G=N2 S=VDD B=VDD; "
            "NM1 D=N1 G=IN1 S=N3 B=VSS; NM2 D=N2 G=IN2 S=N3 B=VSS; "
            "NM3 D=N3 G=N4 S=VSS B=VSS; NM4 D=N4 G=N4 S=VSS B=VSS; "
            "NM5 D=OUT G=N4 S=VSS B=VSS; "
            "R1 P=N2 N=N5; C1 P=N5 N=OUT; R2 P=VDD N=N4"
        ),
    },
]


def load_block_library() -> dict[str, Any]:
    """Loads jiyun's modular op-amp block cards from data/opamp_blocks/cards.json."""
    if not CARDS_FILE.is_file():
        return {"relations": {}, "blocks": {}}
    data = json.loads(CARDS_FILE.read_text(encoding="utf-8"))
    return {"relations": data.get("relations", {}), "blocks": {c["name"]: c for c in data.get("blocks", [])}}


def _pins_with(card: dict[str, Any], prefix: str) -> dict[str, str]:
    return {job.split(":", 1)[1]: pin for pin, job in card.get("pins", {}).items() if job.startswith(prefix + ":")}


def assemble_block_topology(
    stage1_name: str,
    stage2_name: str | None = None,
    comp_name: str | None = None,
    library: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assembles a complete op-amp structure table from modular SPICE blocks."""
    lib = library or load_block_library()
    blocks = lib["blocks"]
    s1 = blocks.get(stage1_name)
    s2 = blocks.get(stage2_name) if stage2_name else None
    comp = blocks.get(comp_name) if comp_name else None
    if s1 is None:
        return {"ok": False, "errors": [f"Unknown stage1 block: {stage1_name}"]}

    def fixed_nets(card: dict[str, Any]) -> dict[str, str]:
        nets: dict[str, str] = {}
        for pin, job in card["pins"].items():
            if job in FIXED_NETS:
                nets[pin] = FIXED_NETS[job]
            elif job.startswith(("bias_in:", "bias_out:")):
                nets[pin] = BIAS_NETS[job.split(":", 1)[1]]
        return nets

    drives = _pins_with(s1, "drive_out")
    s1_nets = fixed_nets(s1)
    instances: list[dict[str, Any]] = []
    comp_nets: list[str] = []
    errors: list[str] = []

    if s2 is None:
        for pin in drives.values():
            s1_nets[pin] = "OUT"
        comp = None
    else:
        needs = _pins_with(s2, "drive_in")
        missing = [lvl for lvl in needs if lvl not in drives]
        if missing:
            return {"ok": False, "errors": [f"Stage2 '{stage2_name}' requires {missing} drive not provided by '{stage1_name}'"]}
        link = {"n": "gn", "p": "gp"} if len(needs) > 1 else {lvl: "o1" for lvl in needs}
        s2_nets = fixed_nets(s2)
        for lvl, pin in needs.items():
            s2_nets[pin] = link[lvl]
            s1_nets[drives[lvl]] = link[lvl]
            comp_nets.append(link[lvl])
        for lvl in drives:
            if lvl not in needs:
                s1_nets[drives[lvl]] = next(iter(link.values()))
        instances.append({"id": "s2", "block": s2["name"], "nets": s2_nets, "params": {}})

    instances.insert(0, {"id": "s1", "block": s1["name"], "nets": s1_nets, "params": {}})
    if comp is not None:
        for idx, net in enumerate(sorted(comp_nets), start=1):
            params = dict(comp.get("params", {}))
            if "comp_cc" in (s2 or {}):
                params["cc"] = s2["comp_cc"]  # type: ignore[index]
            nets = {pin: (net if job == "comp_a" else FIXED_NETS[job]) for pin, job in comp["pins"].items()}
            instances.append({"id": f"c{idx}", "block": comp["name"], "nets": nets, "params": params})

    bias_idx = 0
    while True:
        needed = {name for inst in instances for name in _pins_with(blocks[inst["block"]], "bias_in")}
        made = {name for inst in instances for name in _pins_with(blocks[inst["block"]], "bias_out")}
        lacking = sorted(needed - made)
        if not lacking:
            break
        provider = next(
            (c for c in blocks.values() if c["role"] == "bias" and lacking[0] in _pins_with(c, "bias_out")),
            None,
        )
        if provider is None:
            errors.append(f"No bias block provides '{lacking[0]}'")
            break
        bias_idx += 1
        instances.insert(bias_idx - 1, {"id": f"b{bias_idx}", "block": provider["name"], "nets": fixed_nets(provider), "params": {}})

    if errors:
        return {"ok": False, "errors": errors}

    # Expand blocks into ngspice subckt text and normalize into a structure table
    lines = [".subckt opamp INP INN OUT VDD VSS"]
    for inst in instances:
        card = blocks[inst["block"]]
        params = {**card.get("params", {}), **inst.get("params", {})}
        cir_text = (BLOCKS_DIR / f"{inst['block']}.cir").read_text(encoding="utf-8")
        for raw in cir_text.splitlines():
            line = raw.strip()
            if not line or line.startswith("*"):
                continue
            tokens = line.split()
            cnt = NODE_COUNT.get(tokens[0][0].upper(), 2)
            nodes = [inst["nets"][n] if n in card["pins"] else f"{n}_{inst['id']}" for n in tokens[1:1 + cnt]]
            rest = [tok.format(**params) for tok in tokens[1 + cnt:]]
            lines.append(" ".join([f"{tokens[0]}_{inst['id']}", *nodes, *rest]))
    lines.append(".ends opamp")
    subckt_raw = "\n".join(lines)
    table = circuit_to_table(parse_ngspice_subckt(subckt_raw))
    problems = rule_problems(table)
    return {
        "ok": not problems,
        "name": "__".join(p for p in (stage1_name, stage2_name, comp_name) if p),
        "description": f"Modular assembly: {s1.get('title', stage1_name)}"
        + (f" + {s2.get('title', stage2_name)}" if s2 else "")
        + (f" + {comp.get('title', comp_name)}" if comp else ""),
        "table": table_text(table).replace("\n", "; "),
        "parsed_table": table,
        "problems": problems,
        "source": "block_library",
    }


def _build_flan_t5_prompt(specifications: list[dict[str, Any]], prompt_hint: str = "") -> str:
    """Formats specifications into a compact FLAN-T5 input sentence."""
    parts = ["design opamp"]
    for sp in specifications[:10]:
        sym = sp.get("symbol") or sp.get("name") or ""
        if not sym:
            continue
        target = sp.get("typ") if sp.get("typ") is not None else (sp.get("min") if sp.get("min") is not None else sp.get("max"))
        unit = sp.get("unit") or ""
        if target is not None:
            parts.append(f"{sym}={target}{unit}")
    if prompt_hint:
        parts.append(prompt_hint[:160])
    return "; ".join(parts)


_FLAN_T5_CACHE: dict[str, tuple[Any, Any]] = {}


def _resolve_flan_t5_model_dir() -> Path | None:
    """Resolves fine-tuned FLAN-T5 weights from EDAI_MODEL_DIR or default repo models/flan_t5_structure."""
    env_dir = os.environ.get("EDAI_MODEL_DIR", "").strip()
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir)
    repo_default = Path(__file__).resolve().parents[2] / "models" / "flan_t5_structure"
    if repo_default.is_dir() and (repo_default / "config.json").is_file():
        return repo_default
    return None


def _try_flan_t5_generate(sentence: str, num_beams: int = 5, num_samples: int = 3) -> list[dict[str, Any]]:
    """Attempts candidate generation with fine-tuned FLAN-T5 if weights and torch/transformers exist."""
    model_path = _resolve_flan_t5_model_dir()
    if model_path is None:
        return []
    try:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    except ImportError:
        return []

    model_key = str(model_path)
    if model_key in _FLAN_T5_CACHE:
        tokenizer, model = _FLAN_T5_CACHE[model_key]
    else:
        tokenizer = AutoTokenizer.from_pretrained(model_key)
        model = AutoModelForSeq2SeqLM.from_pretrained(model_key).eval()
        _FLAN_T5_CACHE[model_key] = (tokenizer, model)
    encoded = tokenizer([sentence], return_tensors="pt", truncation=True, max_length=256)
    outputs: list[tuple[str, str]] = []
    with torch.no_grad():
        beam_ids = model.generate(**encoded, max_new_tokens=768, num_beams=num_beams, num_return_sequences=num_beams)
        for t in tokenizer.batch_decode(beam_ids, skip_special_tokens=True):
            outputs.append(("flan_t5_beam", " ".join(t.split())))
        if num_samples > 0:
            samp_ids = model.generate(
                **encoded, max_new_tokens=768, do_sample=True, top_p=0.95, temperature=0.8, num_return_sequences=num_samples
            )
            for t in tokenizer.batch_decode(samp_ids, skip_special_tokens=True):
                outputs.append(("flan_t5_sample", " ".join(t.split())))

    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for idx, (how, text) in enumerate(outputs, start=1):
        if text in seen:
            continue
        seen.add(text)
        try:
            tbl = parse_table_text(text)
            probs = rule_problems(tbl)
        except ValueError as err:
            tbl = None
            probs = [f"Format: {err}"]
        results.append({
            "name": f"flan_t5_cand_{idx}",
            "description": f"FLAN-T5 generated topology ({how})",
            "table": text,
            "parsed_table": tbl,
            "problems": probs,
            "ok": not probs,
            "source": how,
        })
    return results


def generate_topology_candidates(
    specifications: list[dict[str, Any]] | None = None,
    prompt_hint: str = "",
    *,
    include_blocks: bool = True,
    max_candidates: int = 8,
    auto_size_preview: bool = False,
    subckt_name: str = "OPAMP",
    pin_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    Generates and rule-validates op-amp topology candidates from:
      1. Fine-tuned FLAN-T5 model (if EDAI_MODEL_DIR + torch/transformers are configured)
      2. Modular op-amp block library (stage1 x stage2 x Miller compensation)
      3. Canonical built-in structure templates
    Optionally computes gm/ID initial sizing for each valid candidate.
    """
    specs = specifications or []
    sentence = _build_flan_t5_prompt(specs, prompt_hint)
    candidates: list[dict[str, Any]] = []
    seen_tables: set[str] = set()

    # 1. Optional FLAN-T5 inference
    flan_cands = _try_flan_t5_generate(sentence)
    for c in flan_cands:
        if c["table"] not in seen_tables:
            seen_tables.add(c["table"])
            candidates.append(c)

    # 2. Modular block assemblies from jiyun's blocks/
    if include_blocks:
        lib = load_block_library()
        blocks = lib["blocks"]
        s1_list = [k for k, v in blocks.items() if v.get("role") == "stage1"]
        s2_list = [k for k, v in blocks.items() if v.get("role") == "stage2"]
        comp_list = [k for k, v in blocks.items() if v.get("role") == "compensation"]
        for s1 in s1_list:
            for s2 in s2_list:
                for comp in comp_list[:1] or [None]:
                    asm = assemble_block_topology(s1, s2, comp, library=lib)
                    if asm.get("ok") and asm["table"] not in seen_tables:
                        seen_tables.add(asm["table"])
                        candidates.append(asm)
                        if len(candidates) >= max_candidates + 4:
                            break
                if len(candidates) >= max_candidates + 4:
                    break
            if len(candidates) >= max_candidates + 4:
                break

    # 3. Canonical built-in structure templates
    for tmpl in BUILTIN_STRUCTURE_TEMPLATES:
        try:
            tbl = parse_table_text(tmpl["table"])
            probs = rule_problems(tbl)
            norm = table_text(tbl).replace("\n", "; ")
            if norm not in seen_tables:
                seen_tables.add(norm)
                candidates.append({
                    "name": tmpl["name"],
                    "description": tmpl["description"],
                    "table": norm,
                    "parsed_table": tbl,
                    "problems": probs,
                    "ok": not probs,
                    "source": "builtin_template",
                })
        except ValueError:
            pass

    # Filter & optionally attach gm/ID sizing preview
    valid_first = sorted(candidates, key=lambda c: (not c.get("ok", False), len(c.get("problems", []))))[:max_candidates]
    for c in valid_first:
        tbl = c.pop("parsed_table", None)
        if tbl and c.get("ok"):
            c["transistor_count"] = sum(1 for r in tbl["rows"] if r["kind"] in ("nmos", "pmos"))
            if auto_size_preview:
                sized = auto_size(tbl, subckt_name=subckt_name, pin_names=pin_names)
                c["sizing_preview"] = {
                    "ok": sized.get("ok", False),
                    "mode": sized.get("mode"),
                    "sizes": sized.get("sizes"),
                    "subckt_ltspice": sized.get("subckt_ltspice"),
                    "subckt_ngspice": sized.get("subckt_ngspice"),
                }

    return {
        "ok": True,
        "prompt": sentence,
        "flan_t5_active": bool(flan_cands),
        "total_generated": len(candidates),
        "valid_count": sum(1 for c in valid_first if c.get("ok")),
        "candidates": valid_first,
    }


def adapt_flan_t5_subckt_to_dut(
    subckt_ltspice: str,
    dut_name: str,
    pins: list[dict[str, Any]] | list[str],
) -> str | None:
    """
    Adapts a 5-port FLAN-T5 CMOS subcircuit (INP, INN, OUT, VDD, VSS) to any DUT's
    actual pin header order/names, and automatically clones auxiliary channels
    (e.g., _B / _2) for multi-channel ICs sharing the same supply rails.
    """
    import re
    from collections import defaultdict
    from ai_analog_designer.circuit_synthesis.dc_convergence_fixer import _classify_pin

    if not subckt_ltspice or not pins:
        return None

    clean_dut = re.sub(r"[^A-Za-z0-9_]", "_", str(dut_name or "DUT")).upper() or "DUT"
    pin_names = [str(p.get("name")) if isinstance(p, dict) else str(p) for p in pins]
    classified = [_classify_pin(p) for p in pins]

    prim: dict[str, str] = {}
    for pname, kind in classified:
        if kind == "VPOS" and "VDD" not in prim:
            prim["VDD"] = pname
        elif kind in ("VNEG", "GND") and "VSS" not in prim:
            prim["VSS"] = pname
        elif kind == "OUT" and "OUT" not in prim:
            prim["OUT"] = pname
        elif kind == "INP" and "INP" not in prim:
            prim["INP"] = pname
        elif kind == "INN" and "INN" not in prim:
            prim["INN"] = pname
    # Positional fallback if two INP-like signals exist without explicit INN
    if "INN" not in prim:
        for pname, kind in classified:
            if kind == "INP" and pname != prim.get("INP"):
                prim["INN"] = pname
                break

    if not all(k in prim for k in ("VDD", "VSS", "OUT", "INP", "INN")):
        return None

    # Parse models + body lines from generated subcircuit
    # Replace any internal ideal V/I bias sources (e.g. VBIAS_VB1 VDD VB1 1.1) with physical
    # resistive biasing so the subcircuit strictly passes PDG Stage-0 physical-only rules.
    model_lines: list[str] = []
    raw_body_lines: list[str] = []
    in_sub = False
    for ln in subckt_ltspice.splitlines():
        s = ln.strip()
        low = s.lower()
        if low.startswith(".model"):
            model_lines.append(s)
        elif low.startswith(".subckt"):
            in_sub = True
        elif low.startswith(".ends"):
            in_sub = False
        elif in_sub and s and not s.startswith("*"):
            raw_body_lines.append(s)

    if not raw_body_lines:
        return None

    # Track diode-connected MOSFET nodes (D == G) so we know whether a bias node is self-clamped
    diode_nodes: set[str] = set()
    for ln in raw_body_lines:
        toks = ln.split()
        if len(toks) >= 5 and toks[0][0].upper() == "M" and toks[1].upper() == toks[2].upper():
            diode_nodes.add(toks[1].upper())

    body_lines: list[str] = []
    for idx, ln in enumerate(raw_body_lines):
        toks = ln.split()
        if len(toks) >= 3 and toks[0][0].upper() in ("V", "I"):
            src_name, n1, n2 = toks[0], toks[1], toks[2]
            u1, u2 = n1.upper(), n2.upper()
            bias_node = n2 if u1 in ("VDD", "VSS") else (n1 if u2 in ("VDD", "VSS") else n1)
            rail_node = n1 if u1 in ("VDD", "VSS") else (n2 if u2 in ("VDD", "VSS") else "VDD")
            opp_rail = "VSS" if rail_node.upper() == "VDD" else "VDD"
            if bias_node.upper() in diode_nodes:
                # Node is already diode-clamped to rail_node; pull current to opposite rail via resistor
                body_lines.append(f"RBIAS_{src_name}_{idx} {bias_node} {opp_rail} 100k")
            else:
                # Pure gate bias node: physical resistive divider between VDD and VSS
                r_near = "68k" if rail_node.upper() == "VDD" else "68k"
                r_far = "180k"
                body_lines.append(f"RBIAS_A_{src_name}_{idx} {rail_node} {bias_node} {r_near}")
                body_lines.append(f"RBIAS_B_{src_name}_{idx} {bias_node} {opp_rail} {r_far}")
        else:
            body_lines.append(ln)

    def _remap_device_line(line: str, port_map: dict[str, str], ch_suffix: str = "") -> str:
        toks = line.split()
        if len(toks) < 4:
            return line
        prefix = toks[0][0].upper()
        n_terms = 4 if prefix == "M" else (3 if prefix in ("Q", "J") else 2)
        out_toks = [f"{toks[0]}{ch_suffix}"]
        for idx, tok in enumerate(toks[1:], start=1):
            if idx <= n_terms:
                up = tok.upper()
                if up in port_map:
                    out_toks.append(port_map[up])
                elif ch_suffix:
                    out_toks.append(f"{tok}{ch_suffix}")
                else:
                    out_toks.append(tok)
            else:
                out_toks.append(tok)
        return " ".join(out_toks)

    adapted_body = [_remap_device_line(ln, prim) for ln in body_lines]

    # Detect unwired auxiliary channels (_A/_B/_C/_D, _1/_2/_3/_4, or infix _B_P/_B_N)
    ch_groups: dict[str, dict[str, str]] = defaultdict(dict)
    ch_extra_sigs: dict[str, list[str]] = defaultdict(list)
    for pname, kind in classified:
        up = pname.upper()
        m = re.search(r"_([A-D]|[1-4])(?:_[PNM]|$)", up)
        if not m:
            continue
        ch = m.group(1)
        if kind == "OUT":
            ch_groups[ch]["OUT"] = pname
        elif kind == "INP":
            if "INP" not in ch_groups[ch]:
                ch_groups[ch]["INP"] = pname
            else:
                ch_extra_sigs[ch].append(pname)
        elif kind == "INN":
            if "INN" not in ch_groups[ch]:
                ch_groups[ch]["INN"] = pname
            else:
                ch_extra_sigs[ch].append(pname)
    for ch, extras in ch_extra_sigs.items():
        if "INP" not in ch_groups[ch] and extras:
            ch_groups[ch]["INP"] = extras.pop(0)
        if "INN" not in ch_groups[ch] and extras:
            ch_groups[ch]["INN"] = extras.pop(0)

    wired_outputs = {prim["OUT"]}
    for ch, grp in sorted(ch_groups.items()):
        if not all(k in grp for k in ("OUT", "INP", "INN")):
            continue
        if grp["OUT"] in wired_outputs:
            continue
        aux_map = {
            "VDD": prim["VDD"],
            "VSS": prim["VSS"],
            "OUT": grp["OUT"],
            "INP": grp["INP"],
            "INN": grp["INN"],
        }
        for ln in body_lines:
            adapted_body.append(_remap_device_line(ln, aux_map, ch_suffix=f"_CH{ch}"))
        wired_outputs.add(grp["OUT"])

    out_lines = [
        f"* FLAN-T5 Fine-Tuned Topology Seed (gm/ID Sized) for {clean_dut}",
        *model_lines,
        "",
        f".subckt {clean_dut} {' '.join(pin_names)}",
        *adapted_body,
        f".ends {clean_dut}",
        "",
    ]
    return "\n".join(out_lines)


def synthesize_flan_t5_seed(
    dut_name: str,
    pins: list[dict[str, Any]] | list[str],
    specifications: list[dict[str, Any]] | None = None,
    prompt_hint: str = "",
    max_try: int = 3,
) -> dict[str, Any]:
    """
    Runs the local fine-tuned FLAN-T5 topology generator, adapts the top valid
    candidates to the DUT pin interface, and verifies DC operating-point
    convergence in LTspice.
    """
    from ai_analog_designer.circuit_synthesis.dc_convergence_fixer import run_quick_dc_op_check

    res = generate_topology_candidates(
        specifications=specifications or [],
        prompt_hint=prompt_hint,
        include_blocks=False,
        max_candidates=max(5, max_try),
        auto_size_preview=True,
        subckt_name=dut_name,
        pin_names=["INP", "INN", "OUT", "VDD", "VSS"],
    )
    if not res.get("flan_t5_active"):
        return {"ok": False, "flan_t5_active": False, "reason": "FLAN-T5 model or torch/transformers unavailable."}

    flan_cands = [
        c for c in (res.get("candidates") or [])
        if str(c.get("source", "")).startswith("flan_t5") and c.get("ok")
    ]
    for cand in flan_cands[:max_try]:
        sp = (cand.get("sizing_preview") or {}).get("subckt_ltspice")
        if not sp:
            continue
        adapted = adapt_flan_t5_subckt_to_dut(sp, dut_name=dut_name, pins=pins)
        if not adapted:
            continue
        dc = run_quick_dc_op_check(adapted, subckt_name=dut_name, pins=pins, timeout_s=15)
        if dc.get("converged"):
            return {
                "ok": True,
                "flan_t5_active": True,
                "candidate_name": cand.get("name"),
                "source": cand.get("source"),
                "transistor_count": cand.get("transistor_count"),
                "netlist": adapted,
                "dc_diagnostic": dc.get("diagnostic", ""),
            }

    return {
        "ok": False,
        "flan_t5_active": True,
        "reason": f"Checked {min(len(flan_cands), max_try)} FLAN-T5 candidates; none passed DC convergence for this pin interface.",
    }
