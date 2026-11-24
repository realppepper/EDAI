import base64
import concurrent.futures as cf
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

import pymupdf

DEFAULT_NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")

PAGE_CLASS_KEYWORDS = {
    "pin_configuration": ["pin configuration", "pin functions", "terminal functions", "pinout", "pin description",
                          "pin assignments", "pin attributes"],
    "abs_max": ["absolute maximum ratings"],
    "esd": ["esd ratings", "electrostatic discharge"],
    "recommended": ["recommended operating conditions"],
    "thermal": ["thermal information", "thermal characteristics"],
    "electrical": ["electrical characteristics", "switching characteristics", "timing requirements",
                   "dc characteristics", "ac characteristics", "operating characteristics",
                   "dynamic characteristics", "performance characteristics"],
    "typical_characteristics": ["typical characteristics"],
    "functional": ["functional block diagram", "detailed description", "feature description",
                   "device functional modes", "theory of operation", "block diagram"],
    "application": ["application information", "typical application"],
}


class PDFDatasheetParser:
    """
    State-of-the-art layout-aware PDF datasheet parser powered by NVIDIA Nemotron-Parse.
    Converts PDF document pages into high-fidelity structured LaTeX tables and Markdown,
    eliminating heuristic pixel coordinate errors, duplicate words, and collapsed columns.
    """

    def __init__(
        self,
        max_pages: int = 30,
        api_key: str | None = None,
        model: str = "nvidia/nemotron-3.5-parse",
        concurrency: int = 3,
        dpi: int = 150,
        use_nemotron: bool = True
    ):
        self.max_pages = max_pages
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY") or DEFAULT_NVIDIA_API_KEY
        self.model = model
        self.concurrency = max(1, concurrency)
        self.dpi = dpi
        self.use_nemotron = use_nemotron

    @staticmethod
    def sanitize_pin_name(raw_name: str) -> str:
        """Sanitizes pin names preserving polarities (+/-) and disambiguating ports."""
        if not raw_name:
            return "PIN"
        name = str(raw_name).strip()
        name = name.replace("+", "_P").replace("-", "_N").replace("−", "_N").replace("/", "_").replace("#", "_B")
        name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        name = re.sub(r'_+', '_', name).strip('_')
        return name or "PIN"

    def _call_nemotron_parse(self, png_bytes: bytes, max_retries: int = 2) -> dict[str, Any]:
        """Calls NVIDIA NIM nemotron-3.5-parse retrieval endpoint with multipart/form-data PNG payload."""
        boundary = f"----EDAINemotronBoundary{int(time.time() * 1000)}"
        options_json = json.dumps({"decoding": {"max_output_tokens": 9000}}).encode("utf-8")
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="document"; filename="page.png"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode("utf-8") + png_bytes + (
            f"\r\n--{boundary}\r\n"
            'Content-Disposition: form-data; name="options"\r\n\r\n'
        ).encode("utf-8") + options_json + f"\r\n--{boundary}--\r\n".encode("utf-8")

        url = f"https://ai.api.nvidia.com/v1/retrieval/{self.model}/parse"
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Accept": "application/json",
            },
            method="POST",
        )

        last_err = None
        for attempt in range(max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code == 429 and attempt < max_retries:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                break
            except Exception as e:
                last_err = e
                if attempt < max_retries:
                    time.sleep(1.0)
                    continue
                break
        raise last_err or RuntimeError("Failed to call Nemotron-3.5-Parse API.")

    @staticmethod
    def _parse_nemotron35_content(content: str) -> tuple[str, list[dict[str, Any]]]:
        """Strips Nemotron-3.5-Parse coordinate/class tags into clean Markdown + LaTeX tables and blocks."""
        blocks: list[dict[str, Any]] = []
        md_lines: list[str] = []
        pattern = re.compile(
            r"(?:<x_[\d.]+><y_[\d.]+>)?(.*?)(?:<x_[\d.]+><y_[\d.]+>)?<class_([^>]+)>",
            re.DOTALL,
        )
        for m in pattern.finditer(content):
            b_text = re.sub(r"<(?:x|y)_[\d.]+>", "", m.group(1)).strip()
            b_class = m.group(2).strip().lower()
            if not b_text:
                continue
            b_type = "table" if "table" in b_class or "\\begin{tabular}" in b_text else (
                "header" if "header" in b_class or "title" in b_class else (
                    "figure" if "picture" in b_class or "figure" in b_class else "text"
                )
            )
            blocks.append({"type": b_type, "class": b_class, "text": b_text})
            md_lines.append(b_text)
        if not md_lines:
            cleaned = re.sub(r"<(?:x|y)_[\d.]+>|<class_[^>]+>", "", content).strip()
            return cleaned, blocks
        return "\n\n".join(md_lines).strip(), blocks

    def parse_page_with_nemotron(self, page_index_0based: int, doc: pymupdf.Document) -> dict[str, Any]:
        """Renders single page to image and parses it via NVIDIA Nemotron-3.5-Parse."""
        page_num = page_index_0based + 1
        page = doc[page_index_0based]
        
        # 1. Fallback raw text directly from PyMuPDF
        raw_text = page.get_text()

        if not self.use_nemotron or not self.api_key:
            classes = self.classify_page(raw_text)
            return {
                "page_num": page_num,
                "text": raw_text,
                "layout_text": raw_text,
                "classes": classes,
                "blocks": []
            }

        try:
            # 2. Render to PNG image
            pix = page.get_pixmap(dpi=self.dpi)
            png_bytes = pix.tobytes("png")

            # 3. Request Nemotron-3.5-Parse
            res_data = self._call_nemotron_parse(png_bytes)

            # 4. Extract structured Markdown/LaTeX blocks
            content = res_data.get("content", "")
            structured_text, blocks = self._parse_nemotron35_content(content) if content else ("", [])
            final_text = structured_text if structured_text else raw_text
            classes = self.classify_page(final_text or raw_text)

            return {
                "page_num": page_num,
                "text": final_text,
                "layout_text": final_text,
                "classes": classes,
                "blocks": blocks
            }
        except Exception as e:
            # Graceful fallback to raw text if remote call fails
            classes = self.classify_page(raw_text)
            return {
                "page_num": page_num,
                "text": raw_text,
                "layout_text": raw_text,
                "classes": classes,
                "blocks": [],
                "error": str(e)
            }

    @staticmethod
    def classify_page(text: str) -> list[str]:
        lower = text.lower()
        classes = [c for c, kws in PAGE_CLASS_KEYWORDS.items() if any(k in lower for k in kws)]
        toc_hits = len(re.findall(r'\.{5,}\s*\d+', text))
        if toc_hits >= 6:
            return ["toc"]
        return classes

    KEY_PAGE_WORDS = ("electrical characteristics", "pin configuration", "pin functions",
                      "absolute maximum ratings", "recommended operating conditions")

    @classmethod
    def pick_pages(cls, doc, max_pages: int) -> list[int]:
        """읽을 쪽 (0부터). 앞에서부터 max_pages 쪽이 기본이고, 그 뒤에 핵심 표 쪽(전기적 특성, 핀, 정격)이 있으면
        뒤쪽 앞번호 쪽 대신 그 쪽을 넣는다 (쪽 수는 그대로). 긴 묶음 데이터시트에서 표가 30쪽 뒤에 있어도 놓치지 않게."""
        total = len(doc)
        if total <= max_pages:
            return list(range(total))
        def is_key(text: str) -> bool:      # 개정 이력 쪽은 표 제목을 언급만 하므로 뺀다
            return (any(w in text for w in cls.KEY_PAGE_WORDS)
                    and not any(w in text for w in ("revision history", "changes from revision")))
        keys = [0] + [i for i in range(1, total) if is_key(doc[i].get_text().lower())]   # 1쪽(칩 이름·개요)은 항상
        keys = keys[:max_pages]
        fill = [i for i in range(total) if i not in keys][:max_pages - len(keys)]
        return sorted(set(keys) | set(fill))

    def parse_pdf(
        self,
        pdf_path: str,
        progress_callback: Callable[[int, int, int, str | None], None] | None = None,
    ) -> dict[str, Any]:
        """
        Parses all PDF pages concurrently using NVIDIA Nemotron-Parse.
        Returns unified dictionary with page-level provenance.
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"Datasheet PDF not found at {pdf_path}")

        doc = pymupdf.open(pdf_path)
        total_pages = len(doc)
        page_indices = self.pick_pages(doc, self.max_pages)
        pages_to_process = len(page_indices)

        pages: dict[int, dict[str, Any]] = {}
        tables_found = []

        # Concurrently parse pages through Nemotron-Parse
        completed_pages = 0
        with cf.ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            future_to_idx = {
                executor.submit(self.parse_page_with_nemotron, p_idx, doc): p_idx + 1
                for p_idx in page_indices
            }
            for future in cf.as_completed(future_to_idx):
                p_num = future_to_idx[future]
                page_error = None
                try:
                    res = future.result()
                    pages[p_num] = {
                        "text": res["text"],
                        "layout_text": res["layout_text"],
                        "classes": res["classes"],
                        "blocks": res.get("blocks", [])
                    }
                except Exception as e:
                    page_error = str(e)
                    raw_text = doc[p_num - 1].get_text()
                    pages[p_num] = {
                        "text": raw_text,
                        "layout_text": raw_text,
                        "classes": self.classify_page(raw_text),
                        "blocks": [],
                        "error": page_error
                    }
                finally:
                    completed_pages += 1
                    if progress_callback:
                        progress_callback(completed_pages, pages_to_process, p_num, page_error)

        # Also collect basic tables if detected by pymupdf
        for p_idx in page_indices:
            try:
                page_tables = doc[p_idx].find_tables()
                for t in page_tables.tables:
                    t_data = t.extract()
                    if t_data and len(t_data) > 1:
                        tables_found.append({"page": p_idx + 1, "header": t_data[0], "rows": t_data[1:]})
            except Exception:
                pass
        doc.close()

        sections = self._segment_functional_sections(pages)
        return {
            "source_file": os.path.basename(pdf_path),
            "source_path": os.path.abspath(pdf_path),
            "total_pages": total_pages,
            "processed_pages": pages_to_process,
            "pages": pages,
            "sections": sections,
            "tables": tables_found,
            "parser_engine": "nvidia/nemotron-parse" if self.use_nemotron else "pymupdf_fallback"
        }

    def _segment_functional_sections(self, pages: dict[int, dict[str, Any]]) -> dict[str, str]:
        """Legacy flat sections (kept for backwards compatibility)."""
        sec = {"overview": "", "pin_configuration": "", "electrical_specifications": "", "functional_description": ""}
        for pn in sorted(pages):
            text, cls = pages[pn]["text"], pages[pn]["classes"]
            if pn == 1:
                sec["overview"] += text + "\n"
            if "pin_configuration" in cls:
                sec["pin_configuration"] += text + "\n"
            if any(c in cls for c in ("abs_max", "recommended", "electrical", "esd", "thermal")):
                sec["electrical_specifications"] += text + "\n"
            if "functional" in cls:
                sec["functional_description"] += text + "\n"
        return sec

    @staticmethod
    def _prior_score_page(pn: int, pg: dict[str, Any], purpose: str, table_pages: set) -> float:
        """Calculates a soft prior relevance score for a page when LLM selection is unavailable or combined."""
        text = (pg.get("text") or "")
        lower = text.lower()
        cls = set(pg.get("classes") or [])
        if "toc" in cls:
            return -10.0

        score = 0.0
        has_table = pn in table_pages
        if purpose == "pins":
            if "pin_configuration" in cls:
                score += 10.0
            if re.search(r"\b(pin\s+configuration|pin\s+functions|terminal\s+functions|pinout|pin\s+assignments?|connection\s+diagram)\b", lower):
                score += 8.0
            if re.search(r"\b(pin\s*no|pin\s*name|i/o|description)\b", lower):
                score += 5.0
            if pn <= 6:
                score += 3.0
            if has_table:
                score += 2.0
        elif purpose == "specs":
            # Strictly prioritize actual Electrical / Parametric / Switching Characteristics over Abs Max / Thermal
            if "electrical" in cls:
                score += 20.0
            if re.search(r"\b(electrical\s+characteristics|dc\s+characteristics|ac\s+characteristics|switching\s+characteristics|operating\s+characteristics)\b", lower):
                score += 15.0
            if re.search(r"\bparameter\b", lower) and re.search(r"\b(min|typ|max)\b", lower):
                score += 12.0
            unit_hits = len(re.findall(r"\b(mv|ua|na|ma|db|mhz|khz|v/us|ns|us|mohm|kohm)\b", lower))
            score += min(10.0, unit_hits * 0.5)
            if has_table:
                score += 4.0
            if "typical characteristics" in lower[:450] and "electrical characteristics" not in lower[:450]:
                score -= 12.0
            if "recommended" in cls and "electrical" not in cls:
                score += 4.0
            if "abs_max" in cls and "electrical" not in cls:
                score += 2.0
            if ("thermal" in cls or "esd" in cls) and "electrical" not in cls:
                score += 0.5
        elif purpose == "functional":
            if "functional" in cls:
                score += 10.0
            if re.search(r"\b(functional\s+block|schematic|detailed\s+description|theory\s+of\s+operation|application)\b", lower):
                score += 6.0
        return score

    @classmethod
    def _llm_rank_pages(cls, parsed: dict[str, Any]) -> dict[str, list[int]]:
        """Uses an LLM probabilistic classifier over compact page digests to select the best pages
        for 'pins', 'specs' (prioritizing Electrical Characteristics tables), and 'functional'."""
        cache = parsed.get("_llm_page_selection")
        if isinstance(cache, dict) and cache:
            return cache

        pages = {int(k): v for k, v in (parsed.get("pages") or {}).items()}
        if not pages or os.environ.get("ANALOG_DISABLE_LLM_PLANNER") == "1":
            return {}

        try:
            from ..llm_client import LLMClient
            llm = LLMClient(role="fast")
            if getattr(llm, "provider", "none") == "none":
                return {}

            table_pages = {int(t.get("page", 0)) for t in (parsed.get("tables") or []) if t.get("page")}
            digests = []
            for pn in sorted(pages)[:35]:
                txt = (pages[pn].get("text") or "").strip()
                if not txt:
                    continue
                lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
                head = " | ".join(lines[:6])[:260]
                unit_cnt = len(re.findall(r"\b(mV|uA|nA|mA|dB|MHz|kHz|V/us|ns|us|kOhm|Ohm)\b", txt, re.IGNORECASE))
                digests.append({
                    "page": pn,
                    "has_table": pn in table_pages,
                    "unit_density": unit_cnt,
                    "prior_tags": pages[pn].get("classes", []),
                    "header_snippet": head,
                })

            if not digests:
                return {}

            prompt = (
                "You are an expert analog IC datasheet analyzer. Given compact page digests from a PDF datasheet, "
                "probabilistically select and rank the best page numbers for each extraction purpose:\n"
                "1. 'pins': Pages containing Pin Configuration, Pin Functions, Terminal Assignments, or Connection Diagrams.\n"
                "2. 'specs': Pages containing testable **Electrical Characteristics** / Parametric Specification tables "
                "(with Parameter, Test Conditions, Min/Typ/Max, Units). Put actual Electrical Characteristics pages FIRST, "
                "before Recommended Operating Conditions or Absolute Maximum Ratings. Exclude TOC, graphs-only ('Typical Characteristics'), and package outlines.\n"
                "3. 'functional': Pages with Functional Block Diagram, Simplified Schematic, or Detailed Circuit Description.\n\n"
                f"Page digests:\n{json.dumps(digests, ensure_ascii=False)}\n\n"
                "Return JSON with keys: {\"pins\": [int, ...], \"specs\": [int, ...], \"functional\": [int, ...]} ordered from highest probability/relevance to lowest."
            )
            data = llm.complete_json(
                prompt,
                system="Return only valid JSON with integer page lists ranked by relevance.",
                temperature=0.0,
                max_tokens=600,
                stage="pdf_page_selection",
            )
            if isinstance(data, dict):
                valid_pns = set(pages.keys())
                res = {}
                for k in ("pins", "specs", "functional"):
                    raw_list = data.get(k) or []
                    if isinstance(raw_list, list):
                        clean = []
                        for x in raw_list:
                            try:
                                val = int(x)
                                if val in valid_pns and val not in clean:
                                    clean.append(val)
                            except (ValueError, TypeError):
                                pass
                        res[k] = clean
                parsed["_llm_page_selection"] = res
                return res
        except Exception:
            pass
        return {}

    @classmethod
    def select_pages(cls, parsed: dict[str, Any], purpose: str) -> list[int]:
        """Selects and ranks the page numbers relevant for a given extraction purpose using
        LLM probabilistic page ranking combined with structural density priors."""
        pages = {int(k): v for k, v in (parsed.get("pages") or {}).items()}
        if not pages:
            return []

        table_pages = {int(t.get("page", 0)) for t in (parsed.get("tables") or []) if t.get("page")}
        scored = [(cls._prior_score_page(pn, pages[pn], purpose, table_pages), pn) for pn in sorted(pages)]
        prior_ranked = [pn for sc, pn in sorted(scored, key=lambda x: (-x[0], x[1])) if sc > 0]

        if purpose == "specs":
            # Include continuation pages immediately following high-confidence electrical pages
            extra = []
            for pn in list(prior_ranked):
                nxt = pn + 1
                if nxt in pages and nxt not in prior_ranked and "electrical" in (pages[pn].get("classes") or []):
                    t = (pages[nxt].get("text") or "").lower()
                    if ("(continued)" in t or ("parameter" in t and ("min" in t or "typ" in t or "max" in t))) \
                            and "typical characteristics" not in t[:400]:
                        extra.append(nxt)
            for e in extra:
                if e not in prior_ranked:
                    prior_ranked.append(e)

        llm_sel = cls._llm_rank_pages(parsed).get(purpose) or []
        merged: list[int] = []
        for pn in llm_sel + prior_ranked:
            if pn in pages and pn not in merged:
                merged.append(pn)

        if not merged:
            merged = [pn for pn in sorted(pages)][:4 if purpose == "pins" else 10]
        if purpose == "pins" and 1 in pages and 1 not in merged:
            merged = [1] + merged
        return merged

    @staticmethod
    def audit_pages(parsed: dict[str, Any]) -> dict[int, str]:
        """Page texts used by the provenance audit."""
        return {pn: v["text"] + "\n" + v.get("layout_text", "") for pn, v in (parsed.get("pages") or {}).items()}

    @staticmethod
    def page_tagged_text(parsed: dict[str, Any], page_numbers: list[int], budget_chars: int = 60000,
                          layout: bool = False) -> str:
        out, used = [], 0
        for pn in page_numbers:
            pg = parsed["pages"].get(pn) or parsed["pages"].get(str(pn))
            t = pg.get("layout_text") if layout and pg.get("layout_text") else pg["text"]
            chunk = f"\n===== PAGE {pn} =====\n{t}"
            if used + len(chunk) > budget_chars:
                chunk = chunk[: max(0, budget_chars - used)]
            out.append(chunk)
            used += len(chunk)
            if used >= budget_chars:
                break
        return "".join(out)
