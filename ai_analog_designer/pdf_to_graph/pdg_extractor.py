import json
import os
import re
from typing import Any

import networkx as nx


def time_to_us(value: float, unit: str) -> float | None:
    u = (unit or "").strip().lower().replace("µ", "u").replace("μ", "u")
    if u in ("ns",):
        return value / 1000.0
    if u in ("us", "usec"):
        return value
    if u in ("ms",):
        return value * 1000.0
    if u in ("s", "sec"):
        return value * 1e6
    if u in ("ps",):
        return value / 1e6
    return None


def freq_to_mhz(value: float, unit: str) -> float | None:
    u = (unit or "").strip().lower()
    return {"hz": value / 1e6, "khz": value / 1e3, "mhz": value, "ghz": value * 1e3}.get(u)


class PortDependencyGraphExtractor:
    """
    Port Dependency Graph (PDG) extraction (AnalogVerifier Sec. 4.3).

    Precedence (Eq. 3): POWER < BIAS < CONTROL < SIGNAL < OUTPUT.
    Every edge carries an ``origin`` attribute so fidelity can be audited:
      - "datasheet": dependency stated/derived by the extractor from datasheet text
      - "rule":      injected by the precedence rule because the datasheet edge was missing
    Edge weights come from datasheet timing specs where available (``delay_source`` = symbol), else defaults.
    """
    ROLE_PRECEDENCE = {"GROUND": 0, "POWER": 0, "BIAS": 1, "REFERENCE": 1, "ENABLE": 2, "CONTROL": 2,
                       "SIGNAL": 3, "INPUT": 3, "FEEDBACK": 4, "OUTPUT": 4}

    DEFAULT_DELTAS_US = {"POWER_TO_BIAS": 20.0, "TO_CONTROL": 5.0, "TO_SIGNAL": 2.0, "TO_OUTPUT": 50.0}

    def __init__(self, delta_multiplier: float = 1.0):
        self.delta_multiplier = delta_multiplier

    @classmethod
    def extract_timing_specs_from_hkg(cls, hkg: nx.MultiDiGraph) -> dict[str, Any]:
        params = hkg.graph.get("raw_extraction", {}).get("electrical_parameters", [])
        timing = {"turnon_settling_us": None, "propagation_delay_us": None, "slew_rate_v_us": None,
                  "bandwidth_mhz": None, "sources": {}}
        for p in params:
            if not isinstance(p, dict) or str(p.get("category", "ELECTRICAL")).upper() != "ELECTRICAL":
                continue
            sym = str(p.get("symbol") or "").lower()
            name = str(p.get("name") or "").lower()
            unit = str(p.get("unit") or "")
            val = next((p.get(k) for k in ("typ", "max", "min") if isinstance(p.get(k), (int, float))), None)
            if val is None:
                continue
            fval = abs(float(val))
            text = f"{sym} {name}"
            if re.search(r"turn-?on|settling|start-?up|wake", text):
                t = time_to_us(fval, unit)
                if t is not None:
                    timing["turnon_settling_us"] = max(t, timing["turnon_settling_us"] or 0)
                    timing["sources"]["turnon_settling_us"] = p.get("symbol")
            elif re.search(r"propagation|response time|\btpd|\bt_?p(lh|hl)|delay", text):
                t = time_to_us(fval, unit)
                if t is not None:
                    timing["propagation_delay_us"] = max(t, timing["propagation_delay_us"] or 0)
                    timing["sources"]["propagation_delay_us"] = p.get("symbol")
            elif re.search(r"slew", text) or sym in ("sr", "sr+", "sr-"):
                if "v/" in unit.lower():
                    v = fval / 1000.0 if "ms" in unit.lower() else fval
                    timing["slew_rate_v_us"] = v
                    timing["sources"]["slew_rate_v_us"] = p.get("symbol")
            elif re.search(r"gain[- ]bandwidth|\bgbw|\bgbp|unity[- ]gain|bandwidth", text):
                f = freq_to_mhz(fval, unit)
                if f:
                    timing["bandwidth_mhz"] = f
                    timing["sources"]["bandwidth_mhz"] = p.get("symbol")
        return timing

    def _output_delay(self, timing):
        if timing["turnon_settling_us"]:
            return timing["turnon_settling_us"], f"Turn-on settling ({timing['turnon_settling_us']:.3g}us)", timing["sources"]["turnon_settling_us"]
        if timing["propagation_delay_us"]:
            return max(0.01, timing["propagation_delay_us"]) * 5, f"5x propagation delay ({timing['propagation_delay_us']:.3g}us)", timing["sources"]["propagation_delay_us"]
        if timing["slew_rate_v_us"]:
            d = 2.0 / timing["slew_rate_v_us"] + 1.0
            return d, f"Slew-rate settling of 2V step ({timing['slew_rate_v_us']:.3g}V/us)", timing["sources"]["slew_rate_v_us"]
        if timing["bandwidth_mhz"]:
            d = max(1.0, 5.0 / (2 * 3.14159 * timing["bandwidth_mhz"]))
            return d, f"5 tau of GBW ({timing['bandwidth_mhz']:.3g}MHz)", timing["sources"]["bandwidth_mhz"]
        return self.DEFAULT_DELTAS_US["TO_OUTPUT"], "Default output settling (no datasheet timing)", None

    def _llm_infer_pdg_edges_and_delays(
        self,
        raw: dict[str, Any],
        active_pins: list[tuple[str, str, dict[str, Any]]],
        prior_timing: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """
        Uses LLM probabilistic reasoning to infer causal Port Dependency Graph (PDG) edges
        and realistic physical settling delays (in us) when explicit datasheet edges or timing specs
        are sparse or non-standard.
        """
        if not active_pins or os.environ.get("ANALOG_DISABLE_LLM_PLANNER") == "1":
            return [], prior_timing

        existing_deps = raw.get("port_dependencies") or []
        if len(existing_deps) >= len(active_pins) and any(
            prior_timing.get(k) for k in ("turnon_settling_us", "propagation_delay_us", "slew_rate_v_us", "bandwidth_mhz")
        ):
            return [], prior_timing

        try:
            from ..llm_client import LLMClient
            llm = LLMClient(role="fast")
            if getattr(llm, "provider", "none") == "none":
                return [], prior_timing

            ic_meta = raw.get("ic_metadata") or {}
            compact_pins = [
                {"name": pname, "role": role, "desc": str((pdata or {}).get("description") or "")[:70]}
                for pname, role, pdata in active_pins
            ]
            compact_specs = [
                {
                    "symbol": s.get("symbol"),
                    "name": s.get("name"),
                    "typ": s.get("typ"),
                    "max": s.get("max"),
                    "unit": s.get("unit"),
                }
                for s in (raw.get("electrical_parameters") or [])[:20]
                if isinstance(s, dict)
            ]
            prompt = (
                "You are an expert analog IC causal Port Dependency Graph (PDG) analyzer.\n"
                f"IC Metadata: {json.dumps(ic_meta, ensure_ascii=False)}\n"
                f"Active Pins: {json.dumps(compact_pins, ensure_ascii=False)}\n"
                f"Sample Specs: {json.dumps(compact_specs, ensure_ascii=False)}\n\n"
                "Infer the causal port dependency edges (ordered from POWER/GROUND -> BIAS/REFERENCE -> CONTROL/ENABLE -> SIGNAL/INPUT -> OUTPUT) "
                "and realistic physical settling delays in microseconds (`delay_us`).\n"
                "Return ONLY valid JSON:\n"
                "{\n"
                "  \"timing_estimates\": {\"turnon_settling_us\": float_or_null, \"propagation_delay_us\": float_or_null, \"slew_rate_v_us\": float_or_null, \"bandwidth_mhz\": float_or_null},\n"
                "  \"edges\": [\n"
                "    {\"source\": \"<pin_name>\", \"target\": \"<pin_name>\", \"dependency_type\": \"POWER_FEED|SIGNAL_PATH|TO_SIGNAL|TO_CONTROL|POWER_TO_BIAS\", \"delay_us\": 10.0, \"condition\": \"...\"}\n"
                "  ]\n"
                "}"
            )
            res = llm.complete_json(
                prompt,
                system="Return only valid JSON with causal PDG edges and timing estimates.",
                temperature=0.0,
                max_tokens=800,
                stage="probabilistic_pdg_inference",
            )
            if not isinstance(res, dict):
                return [], prior_timing

            merged_timing = dict(prior_timing)
            merged_timing["sources"] = dict(prior_timing.get("sources") or {})
            te = res.get("timing_estimates") or {}
            if isinstance(te, dict):
                for tk in ("turnon_settling_us", "propagation_delay_us", "slew_rate_v_us", "bandwidth_mhz"):
                    if merged_timing.get(tk) is None and isinstance(te.get(tk), (int, float)) and float(te[tk]) > 0:
                        merged_timing[tk] = float(te[tk])
                        merged_timing["sources"][tk] = "llm_probabilistic_inference"

            valid_names = {p[0] for p in active_pins}
            inferred_edges = []
            for e in res.get("edges") or []:
                if isinstance(e, dict) and e.get("source") in valid_names and e.get("target") in valid_names:
                    inferred_edges.append(e)
            return inferred_edges, merged_timing
        except Exception:
            return [], prior_timing

    def extract_pdg(self, hkg: nx.MultiDiGraph) -> tuple[nx.DiGraph, dict[str, float], list[list[str]]]:
        timing = self.extract_timing_specs_from_hkg(hkg)
        raw = hkg.graph.get("raw_extraction", {})

        pins = []
        for n, d in hkg.nodes(data=True):
            if d.get("node_type") == "PIN":
                pd = d.get("data", {})
                pins.append((n, str(pd.get("role") or "SIGNAL").upper(), pd))
        if not pins:
            for p in raw.get("pins", []):
                pins.append((p.get("name", "PIN"), str(p.get("role") or "SIGNAL").upper(), p))

        pdg = nx.DiGraph()
        for pname, role, pdata in pins:
            pdg.add_node(pname, role=role, data=pdata)
        active = [p for p in pins if p[1] != "NC"]

        llm_edges, timing = self._llm_infer_pdg_edges_and_delays(raw, active, timing)
        out_delay, out_cond, out_src = self._output_delay(timing)

        def add(u, v, delay_us, dep_type, cond, origin, delay_source=None):
            # kind: "causal" = physical signal/power flow into the target; "sequencing" = Eq.3 ordering constraint only
            kind = "sequencing" if dep_type in ("POWER_TO_BIAS", "TO_CONTROL", "TO_SIGNAL") else "causal"
            pdg.add_edge(u, v, weight=delay_us * 1e-6 * self.delta_multiplier, delay_us=delay_us,
                         dependency_type=dep_type, condition=cond, origin=origin, delay_source=delay_source, kind=kind)

        # 1. Datasheet-derived dependencies
        for dep in raw.get("port_dependencies", []) or []:
            src, tgt = dep.get("source"), dep.get("target")
            if src in pdg and tgt in pdg and src != tgt and pdg.nodes[src]["role"] != "NC" and pdg.nodes[tgt]["role"] != "NC":
                d = dep.get("settling_delay_us")
                if isinstance(d, (int, float)) and d > 0:
                    delay, dsrc = float(d), "datasheet_edge"
                elif self.ROLE_PRECEDENCE.get(pdg.nodes[tgt]["role"], 3) == 4:
                    delay, dsrc = out_delay, out_src
                else:
                    delay, dsrc = self.DEFAULT_DELTAS_US["TO_SIGNAL"], None
                add(src, tgt, delay, dep.get("dependency_type", "DEPENDS_ON"),
                    dep.get("condition") or "Datasheet dependency", "datasheet", dsrc)

        # 1b. LLM-inferred probabilistic causal dependencies (for edges not already present)
        for dep in llm_edges:
            src, tgt = dep.get("source"), dep.get("target")
            if src in pdg and tgt in pdg and src != tgt and not pdg.has_edge(src, tgt):
                d = dep.get("delay_us")
                delay = float(d) if isinstance(d, (int, float)) and d > 0 else out_delay
                add(
                    src,
                    tgt,
                    delay,
                    str(dep.get("dependency_type") or "DEPENDS_ON"),
                    str(dep.get("condition") or "LLM probabilistic causal inference"),
                    "llm_probabilistic",
                    "llm_probabilistic_inference",
                )

        # 2. Precedence-rule completion — only where the datasheet layer left a pin without any driver
        lvl = lambda r: self.ROLE_PRECEDENCE.get(r, 3)
        power = [p[0] for p in active if lvl(p[1]) == 0]
        bias = [p[0] for p in active if lvl(p[1]) == 1]
        ctrl = [p[0] for p in active if lvl(p[1]) == 2]
        sig = [p[0] for p in active if lvl(p[1]) == 3]
        outs = [p[0] for p in active if lvl(p[1]) == 4]

        def complete(targets, sources, delay, dep_type, cond, dsrc=None):
            for t in targets:
                if any(pdg.has_edge(s, t) for s in sources) or not sources:
                    continue
                for s in sources:
                    if s != t:
                        add(s, t, delay, dep_type, cond, "rule", dsrc)

        complete(bias, power, self.DEFAULT_DELTAS_US["POWER_TO_BIAS"], "POWER_TO_BIAS", "Bias stabilization after supply ramp")
        complete(ctrl, bias or power, self.DEFAULT_DELTAS_US["TO_CONTROL"], "TO_CONTROL", "Control threshold settling")
        complete(sig, ctrl or bias or power, self.DEFAULT_DELTAS_US["TO_SIGNAL"], "TO_SIGNAL", "Operating point stabilization")
        complete(outs, power, out_delay, "POWER_FEED", out_cond, out_src)
        # Outputs with no signal driver at all get one from inputs (single-channel assumption)
        for o in outs:
            if not any(pdg.has_edge(s, o) for s in sig + ctrl + bias) and sig:
                for s in sig:
                    add(s, o, out_delay, "SIGNAL_PATH", out_cond, "rule", out_src)

        # Break cycles (Algorithm 1 line 2)
        while not nx.is_directed_acyclic_graph(pdg):
            cyc = nx.find_cycle(pdg)
            u, v = cyc[-1][0], cyc[-1][1]
            pdg.remove_edge(u, v)

        topo = list(nx.topological_sort(pdg))
        sigma: dict[str, float] = {}
        for p in topo:
            ins = list(pdg.in_edges(p, data=True))
            sigma[p] = max((sigma[q] + d.get("weight", 1e-6) for q, _, d in ins), default=0.0)

        level_map: dict[str, int] = {}
        for v in topo:
            preds = list(pdg.predecessors(v))
            level_map[v] = max(level_map[u] for u in preds) + 1 if preds else 0
        levels = [[] for _ in range((max(level_map.values()) if level_map else 0) + 1)]
        for node, l in level_map.items():
            levels[l].append(node)

        pdg.graph["timing_specs"] = timing
        pdg.graph["schedule"] = sigma
        return pdg, sigma, levels
