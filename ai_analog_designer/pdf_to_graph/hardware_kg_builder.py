import concurrent.futures as cf
import logging
import os
import re
from collections.abc import Callable
from typing import Any

import networkx as nx

from ..llm_client import LLMClient

logger = logging.getLogger(__name__)

ROLES = ["POWER", "GROUND", "BIAS", "REFERENCE", "CONTROL", "ENABLE", "SIGNAL", "FEEDBACK", "OUTPUT", "NC"]
SPEC_CATEGORIES = ["ELECTRICAL", "ABS_MAX", "RECOMMENDED", "THERMAL", "ESD"]


class HardwareKnowledgeGraph(nx.MultiDiGraph):
    pass


class HKGExtractionError(RuntimeError):
    """Raised when a datasheet's specification tables could not be extracted.

    Proceeding with an empty specification set makes later verification look
    successful while measuring nothing, so this is intentionally terminal.
    """

    def __init__(self, spec_pages: list[int], failed_pages: list[dict[str, Any]]):
        self.spec_pages = spec_pages
        self.failed_pages = failed_pages
        page_list = ", ".join(str(p.get("page", "?")) for p in failed_pages)
        super().__init__(
            "Specification-table extraction produced no usable rows "
            f"for pages {spec_pages}; failed pages: {page_list or 'unknown'}"
        )


PINS_PROMPT = """You are extracting the PIN INTERFACE and PORT DEPENDENCIES of an IC from its datasheet.
Pages are delimited by '===== PAGE N ====='.

{text}

TASK
1. Pick ONE representative package (prefer the 8-pin SOIC/PDIP, or the most common package if no 8-pin exists) and
   list EVERY pin of that package exactly once (including NC pins). Use the datasheet's canonical pin name.
   Pins that share a name (e.g. several ANODE or GND pins) are ONE net: list it once with all numbers in pin_number ("2,3,6,7").
2. For each pin give: role (one of {roles}), direction (INPUT|OUTPUT|POWER|GROUND|BIDIRECTIONAL|NC),
   Role definitions:
     POWER = supply input (VCC, V+, V-, VIN of a regulator); GROUND = 0V return (GND, ANODE of shunt reference);
     SIGNAL = analog/threshold input that is the measured stimulus (op-amp IN+/IN-, comparator inputs, 555 TRIG and THRES);
     CONTROL/ENABLE = digital-style gating (RESET, EN, SHDN); REFERENCE/BIAS = reference/bypass nodes (CONT, BYPASS, VREF);
     FEEDBACK = feedback/adjust/gain-setting pins (ADJ, REF of TL431, RG, GAIN);
     OUTPUT = driven/regulated node (OUT, VO, CATHODE of a shunt regulator, DISCH).
   the page number where the pin table shows it and a SHORT VERBATIM quote (<= 12 words) copied from that page.
3. List the causal port dependencies needed for test sequencing:
   - every supply pin AND every ground pin -> every output pin (POWER_FEED)
   - every signal input -> the output of ITS OWN channel only (SIGNAL_PATH) — never cross channels
   - control/enable/reset -> affected output (CONTROL_GATE); reference/feedback/bias pins -> affected output (FEEDBACK_LOOP / BIAS_FEED)
   Give settling_delay_us only if the datasheet states a time for it, else null.

Return JSON:
{{"ic_device": {{"name": str, "category": str, "description": str, "package": str}},
  "pins": [{{"name": str, "pin_number": str, "role": str, "direction": str, "description": str, "page": int, "evidence": str}}],
  "port_dependencies": [{{"source": str, "target": str, "dependency_type": str, "settling_delay_us": float|null, "condition": str}}],
  "functional_blocks": [{{"name": str, "type": str, "description": str, "input_ports": [str], "output_ports": [str]}}]}}
"""

SPECS_PROMPT = """You are extracting SPECIFICATION TABLES of the IC '{ic}' from its datasheet.
Pages are delimited by '===== PAGE N ====='.

{text}

The text was rebuilt from word coordinates: '|' separates table cells, and every number lying under a
MIN / TYP / MAX column header is tagged like 2{{TYP}} or 4{{MAX}}. ALWAYS put a number into the slot given by its
tag (a row '0.4{{TYP}} 1{{MAX}}' means min=null, typ=0.4, max=1). Rows wrapped over several lines belong together.

TASK: extract every row of the specification tables. For EACH row:
- category: ABS_MAX (Absolute Maximum Ratings), RECOMMENDED (Recommended Operating Conditions),
  ESD (ESD ratings), THERMAL (thermal information), ELECTRICAL (electrical/switching/timing characteristics = testable).
- symbol, name, min, typ, max (numbers exactly as printed, null if blank), unit exactly as printed,
  test_conditions (condition column + table header conditions such as VS=5V, TA=25C),
  page (where the row is), evidence (SHORT verbatim snippet of that row, <= 15 words).
- Keep EVERY row, including full-temperature-range rows and per-variant rows; record the variant and temperature
  range inside test_conditions (e.g. "LM358B, TA = -40C to 85C"). One output object per printed row/condition line.
  Rows with several condition lines (e.g. IOUT = 50uA / 1mA / 5mA) produce one object per line.
- related_pins: pin names this spec is measured at (e.g. OUT, VCC).

Return JSON: {{"electrical_parameters": [{{"symbol": str, "name": str, "category": str, "min": number|null,
 "typ": number|null, "max": number|null, "unit": str, "test_conditions": str, "page": int, "evidence": str,
 "related_pins": [str]}}]}}
"""


def _num(v):
    if v is None or isinstance(v, (int, float)):
        return v
    s = str(v).strip().replace("−", "-").replace("–", "-").replace("±", "")
    m = re.match(r'^[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?$', s)
    return float(s) if m else None


class HardwareKnowledgeGraphBuilder:
    """Builds the Hardware Knowledge Graph (HKG) from a parsed datasheet using two parallel LLM extraction passes
    (interface/dependencies and specification tables), each with page-level provenance."""

    def __init__(self, llm_client: LLMClient | None = None, max_spec_pages: int = 10, parallel_spec_calls: int = 2):
        self.llm = llm_client or LLMClient()
        self.max_spec_pages = max(1, int(os.environ.get("HKG_MAX_SPEC_PAGES", str(max_spec_pages))))
        # Three in-flight calls (two table pages plus pin extraction) stay
        # below the provider's four-request global cap.  The old value of six
        # made seven pages contend at once, then all hit their TTFT deadlines.
        configured_parallelism = int(os.environ.get("HKG_PARALLEL_SPEC_CALLS", parallel_spec_calls))
        self.parallel_spec_calls = max(1, min(configured_parallelism, 3))
        self.spec_page_retries = max(0, int(os.environ.get("HKG_SPEC_PAGE_RETRIES", "1")))
        self.spec_max_tokens = max(512, int(os.environ.get("HKG_SPEC_MAX_TOKENS", "4000")))
        self.retry_spec_max_tokens = max(
            self.spec_max_tokens,
            int(os.environ.get("HKG_RETRY_SPEC_MAX_TOKENS", "5000")),
        )
        single_shot_env = os.environ.get("HKG_SINGLE_SHOT_SPECS")
        if single_shot_env is None:
            self.single_shot_specs = getattr(self.llm, "provider", "") == "groq"
        else:
            self.single_shot_specs = single_shot_env.strip().lower() in {"1", "true", "yes"}

    def extract_raw(
        self,
        parsed_data: dict[str, Any],
        progress_callback: Callable[[int, int, int, str | None], None] | None = None,
        pins_only: bool = False,
    ) -> dict[str, Any]:
        from .pdf_parser import PDFDatasheetParser as P
        if "pages" not in parsed_data:  # legacy input
            return self._legacy_extract(parsed_data)

        pin_pages = P.select_pages(parsed_data, "pins")
        func_pages = P.select_pages(parsed_data, "functional")[:2]
        spec_pages = [] if pins_only else P.select_pages(parsed_data, "specs")[: self.max_spec_pages]
        pin_text_limit = int(os.environ.get("HKG_PIN_TEXT_CHARS", "12000"))
        pin_text = P.page_tagged_text(parsed_data, sorted(set(pin_pages + func_pages)), pin_text_limit)
        ic_guess = re.sub(r'\.pdf$', '', parsed_data.get("source_file", "IC"), flags=re.IGNORECASE).upper()

        # Spec tables are extracted ONE PAGE PER CALL in parallel: a single call over all spec pages emits
        # ~10k output tokens (100-170 s on NIM and frequently truncated); per-page calls emit 1-2k tokens each.
        sys_p = "You are a meticulous analog IC datasheet analyst. Extract only what the datasheet states. Never invent values."
        spec_jobs = {}
        spec_rows: dict[int, list[dict[str, Any]]] = {}
        failed_pages: list[dict[str, Any]] = []

        def extract_spec_page(page_num: int, *, retry: bool = False) -> list[dict[str, Any]]:
            text = P.page_tagged_text(parsed_data, [page_num], 14000, layout=True)
            tag = f"hkg_specs_retry_p{page_num}" if retry else f"hkg_specs_p{page_num}"
            rows = self.llm.complete_json(
                SPECS_PROMPT.format(text=text, ic=ic_guess),
                system_prompt=sys_p,
                max_tokens=self.retry_spec_max_tokens if retry else self.spec_max_tokens,
                tag=tag,
                timeout_profile="extraction",
            ).get("electrical_parameters") or []
            rows = [row for row in rows if isinstance(row, dict)]
            if not rows:
                logger.info(f"Page {page_num} contained no specification table rows.")
                return []
            for row in rows:
                if not row.get("page"):
                    row["page"] = page_num
            return rows

        # Single-shot specification extraction for large-context/high-output models (e.g. Groq openai/gpt-oss-120b)
        if self.single_shot_specs and spec_pages:
            logger.info(
                f"Single-shot specification extraction across pages {spec_pages} "
                f"using {self.llm.model_tiers.get('capable', self.llm.default_model)}..."
            )
            combined_spec_text = P.page_tagged_text(parsed_data, spec_pages, 60000, layout=True)
            try:
                pins_json = self.llm.complete_json(
                    PINS_PROMPT.format(text=pin_text, roles="|".join(ROLES)),
                    system_prompt=sys_p,
                    max_tokens=3000,
                    tag="hkg_pins",
                    timeout_profile="extraction",
                )
                single_res = self.llm.complete_json(
                    SPECS_PROMPT.format(text=combined_spec_text, ic=ic_guess),
                    system_prompt=sys_p,
                    model=self.llm.model_tiers.get("capable"),
                    max_tokens=16384,
                    tag="hkg_specs_single_shot",
                    timeout_profile="extraction",
                )
                rows = [r for r in (single_res.get("electrical_parameters") or []) if isinstance(r, dict)]
                if rows:
                    for idx, pn in enumerate(spec_pages):
                        if progress_callback:
                            progress_callback(idx + 1, len(spec_pages), pn, None)
                    specs_json = {"electrical_parameters": rows}
                    raw_pins = pins_json.get("pins") or pins_json.get("pin_interface") or []
                    cleaned_pins = []
                    for p in raw_pins:
                        if isinstance(p, dict):
                            p_copy = dict(p)
                            if not p_copy.get("name") and p_copy.get("pin_name"):
                                p_copy["name"] = p_copy["pin_name"]
                            cleaned_pins.append(p_copy)
                    return {
                        "ic_info": pins_json.get("ic_info", {}),
                        "pins": cleaned_pins,
                        "port_dependencies": pins_json.get("port_dependencies", []),
                        "functional_blocks": pins_json.get("functional_blocks", []),
                        "electrical_parameters": specs_json["electrical_parameters"],
                        "failed_spec_pages": [],
                    }
                logger.warning("Single-shot spec extraction returned 0 rows; falling back to per-page extraction.")
            except Exception as e:
                logger.warning(f"Single-shot spec extraction failed ({e}); falling back to per-page extraction.")

        if self.parallel_spec_calls <= 1:
            pins_json = self.llm.complete_json(
                PINS_PROMPT.format(text=pin_text, roles="|".join(ROLES)),
                system_prompt=sys_p,
                max_tokens=min(2500, self.spec_max_tokens),
                tag="hkg_pins",
                timeout_profile="extraction",
            )
            completed_pages = 0
            for pn in spec_pages:
                try:
                    spec_rows[pn] = extract_spec_page(pn)
                    completed_pages += 1
                    if progress_callback:
                        progress_callback(completed_pages, len(spec_pages), pn, None)
                except Exception as e:
                    completed_pages += 1
                    failure = {"page": pn, "error": str(e)[:300], "attempts": 1}
                    failed_pages.append(failure)
                    if progress_callback:
                        progress_callback(completed_pages, len(spec_pages), pn, failure["error"])
        else:
            try:
                from opentelemetry import context as otel_context
                parent_ctx = otel_context.get_current()
            except Exception:
                otel_context = None
                parent_ctx = None

            def _with_ctx(fn, *args, **kwargs):
                if otel_context is not None and parent_ctx is not None:
                    tok = otel_context.attach(parent_ctx)
                    try:
                        return fn(*args, **kwargs)
                    finally:
                        otel_context.detach(tok)
                return fn(*args, **kwargs)

            with cf.ThreadPoolExecutor(max_workers=1 + self.parallel_spec_calls) as ex:
                f_pins = ex.submit(
                    _with_ctx,
                    self.llm.complete_json,
                    PINS_PROMPT.format(text=pin_text, roles="|".join(ROLES)),
                    system_prompt=sys_p,
                    max_tokens=min(3000, self.spec_max_tokens),
                    tag="hkg_pins",
                    timeout_profile="extraction",
                )
                for pn in spec_pages:
                    spec_jobs[ex.submit(_with_ctx, extract_spec_page, pn)] = pn
                completed_pages = 0
                for f in cf.as_completed(spec_jobs):
                    pn = spec_jobs[f]
                    try:
                        spec_rows[pn] = f.result()
                        completed_pages += 1
                        if progress_callback:
                            progress_callback(completed_pages, len(spec_pages), pn, None)
                    except Exception as e:
                        completed_pages += 1
                        failure = {"page": pn, "error": str(e)[:300], "attempts": 1}
                        failed_pages.append(failure)
                        if progress_callback:
                            progress_callback(completed_pages, len(spec_pages), pn, failure["error"])
                pins_json = f_pins.result()

        # A first-pass timeout is usually transient provider congestion.  Retry
        # only the affected page, serially, on the frontier tier.  This avoids
        # recreating the original six-way thundering herd and preserves the
        # fast/capable path for normal pages.
        unresolved = list(failed_pages)
        for retry_index in range(1, self.spec_page_retries + 1):
            if not unresolved:
                break
            next_unresolved = []
            for failure in unresolved:
                pn = int(failure["page"])
                try:
                    spec_rows[pn] = extract_spec_page(pn, retry=True)
                    failed_pages.remove(failure)
                    if progress_callback:
                        progress_callback(len(spec_rows), len(spec_pages), pn, None)
                except Exception as e:
                    failure["attempts"] = retry_index + 1
                    failure["error"] = str(e)[:300]
                    next_unresolved.append(failure)
                    if progress_callback:
                        progress_callback(len(spec_rows), len(spec_pages), pn, failure["error"])
            unresolved = next_unresolved

        specs_json = {"electrical_parameters": []}
        for pn in sorted(spec_rows):
            specs_json["electrical_parameters"].extend(spec_rows[pn])

        if spec_pages and not specs_json["electrical_parameters"]:
            logger.warning(
                f"Specification extraction produced no usable rows for pages {spec_pages}. "
                "Proceeding with extracted pins, device metadata, and port dependencies."
            )

        raw_pins = pins_json.get("pins") or pins_json.get("pin_interface") or []
        cleaned_pins = []
        for p in raw_pins:
            if isinstance(p, dict):
                p_copy = dict(p)
                if not p_copy.get("name") and p_copy.get("pin_name"):
                    p_copy["name"] = p_copy["pin_name"]
                cleaned_pins.append(p_copy)

        data = {
            "ic_device": pins_json.get("ic_device") or {"name": ic_guess, "category": "ANALOG"},
            "pins": cleaned_pins,
            "port_dependencies": pins_json.get("port_dependencies") or [],
            "functional_blocks": pins_json.get("functional_blocks") or [],
            "electrical_parameters": [],
            "provenance": {"pin_pages": pin_pages, "spec_pages": spec_pages, "func_pages": func_pages,
                           "failed_spec_pages": failed_pages, "source_file": parsed_data.get("source_file")},
        }
        seen = set()
        for p in specs_json.get("electrical_parameters") or []:
            if not isinstance(p, dict):
                continue
            for k in ("min", "typ", "max"):
                p[k] = _num(p.get(k))
            cat = str(p.get("category") or "ELECTRICAL").upper()
            p["category"] = cat if cat in SPEC_CATEGORIES else "ELECTRICAL"
            key = (str(p.get("symbol")).upper(), p["category"], p.get("min"), p.get("typ"), p.get("max"),
                   str(p.get("test_conditions"))[:40])
            if key in seen:
                continue
            seen.add(key)
            data["electrical_parameters"].append(p)
        return data

    def build_kg_from_parsed_pdf(
        self,
        parsed_data: dict[str, Any],
        progress_callback: Callable[[int, int, int, str | None], None] | None = None,
        pins_only: bool = False,
    ) -> nx.MultiDiGraph:
        data = self.extract_raw(parsed_data, progress_callback=progress_callback, pins_only=pins_only)
        G = self._json_to_networkx_graph(data)
        from .pdf_parser import PDFDatasheetParser
        G.graph["parsed_pages"] = PDFDatasheetParser.audit_pages(parsed_data)
        return G

    # ------------------------------------------------------------------
    def _legacy_extract(self, parsed_data):
        s = parsed_data.get("sections", {})
        text = "\n".join([s.get("overview", "")[:4000], s.get("pin_configuration", "")[:6000],
                          s.get("electrical_specifications", "")[:14000]])
        pins = self.llm.complete_json(PINS_PROMPT.format(text=text, roles="|".join(ROLES)), tag="hkg_pins")
        specs = self.llm.complete_json(SPECS_PROMPT.format(text=text, ic="IC"), tag="hkg_specs")
        pins["electrical_parameters"] = specs.get("electrical_parameters", [])
        return pins

    @staticmethod
    def _unsanitize(pname: str) -> str:
        s = str(pname)
        if s.endswith("_P"):
            return s[:-2] + "+"
        if s.endswith("_N"):
            return s[:-2] + "-"
        return s

    def _json_to_networkx_graph(self, data: dict[str, Any]) -> nx.MultiDiGraph:
        from .pdf_parser import PDFDatasheetParser
        G = HardwareKnowledgeGraph()
        ic_info = data.get("ic_device") or {"name": "DUT_IC", "category": "ANALOG"}
        if not isinstance(ic_info, dict):
            ic_info = {"name": str(ic_info), "category": "ANALOG"}
        ic_name = ic_info.get("name", "DUT_IC")
        G.add_node(ic_name, node_type="IC_DEVICE", data=ic_info)

        # Pins are modelled as NETS: several package pins with the same name (e.g. TL431 SOIC-8 has four ANODE pins)
        # are the same internal node and are merged into one PDG port carrying all pin numbers.
        rename = {}
        merged: dict[str, dict[str, Any]] = {}
        for idx, pin in enumerate(data.get("pins") or []):
            if not isinstance(pin, dict):
                continue
            raw = pin.get("raw_name") or pin.get("name") or f"PIN_{idx}"
            if str(raw) == str(pin.get("name")) and re.search(r"_(P|N)$", str(raw)):
                raw = self._unsanitize(raw)   # cached extraction lost the original spelling ("IN1+" -> "IN1_P")
            pname = PDFDatasheetParser.sanitize_pin_name(raw)
            if pname in merged:
                merged[pname].setdefault("pin_numbers", [merged[pname].get("pin_number")])
                merged[pname]["pin_numbers"].append(pin.get("pin_number"))
                continue
            rename.setdefault(str(raw), pname)
            pin["raw_name"] = raw
            pin["name"] = pname
            pin["role"] = str(pin.get("role") or "SIGNAL").upper()
            merged[pname] = pin
        data["pins"] = list(merged.values())
        for pname, pin in merged.items():
            G.add_node(pname, node_type="PIN", data=pin)
            G.add_edge(ic_name, pname, relation="HAS_PIN")

        def resolve(n):
            n = str(n or "")
            return rename.get(n) or PDFDatasheetParser.sanitize_pin_name(n)

        for idx, blk in enumerate(data.get("functional_blocks") or []):
            blk = blk if isinstance(blk, dict) else {"name": str(blk)}
            bname = f"BLK_{blk.get('name') or idx}"
            G.add_node(bname, node_type="FUNCTIONAL_BLOCK", data=blk)
            G.add_edge(ic_name, bname, relation="HAS_BLOCK")
            for inp in blk.get("input_ports") or []:
                if resolve(inp) in G:
                    G.add_edge(resolve(inp), bname, relation="FEEDS_BLOCK")
            for outp in blk.get("output_ports") or []:
                if resolve(outp) in G:
                    G.add_edge(bname, resolve(outp), relation="DRIVES_PORT")

        clean_deps = []
        for dep in data.get("port_dependencies") or []:
            if not isinstance(dep, dict):
                continue
            src, tgt = resolve(dep.get("source")), resolve(dep.get("target"))
            if src in G and tgt in G and src != tgt:
                dep = dict(dep, source=src, target=tgt)
                clean_deps.append(dep)
                G.add_edge(src, tgt, relation=dep.get("dependency_type", "DEPENDS_ON"),
                           settling_delay_us=_num(dep.get("settling_delay_us")), condition=dep.get("condition") or "")
        data["port_dependencies"] = clean_deps

        for idx, param in enumerate(data.get("electrical_parameters") or []):
            if not isinstance(param, dict):
                continue
            sym = param.get("symbol") or param.get("name") or f"PARAM_{idx}"
            param["symbol"] = sym
            nid = f"SPEC_{sym}_{idx}"
            G.add_node(nid, node_type="SPEC_PARAM", data=param, symbol=sym)
            G.add_edge(ic_name, nid, relation="SPECIFIES")
            for rp in param.get("related_pins") or []:
                if resolve(rp) in G:
                    G.add_edge(resolve(rp), nid, relation="GOVERNS")

        G.graph["raw_extraction"] = data
        return G
