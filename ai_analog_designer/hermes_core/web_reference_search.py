"""
Web & IEEE Academic Circuit Reference Search Engine.
Triple-Engine Integration combining:
  1. IEEE Xplore / OpenAlex Academic Engine (Peer-reviewed transistor topology & design equations)
  2. Tavily Search API (Synthesized architectural overviews & technical datasheets)
  3. Exa Neural Search API (Deep semantic netlist & application note retrieval)

Extracts transistor-level schematics, peer-reviewed design rationale, SPICE macromodels,
and manufacturer application notes to ground Hermes Agent and Harness² synthesis.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ai_analog_designer.llm_client import _load_env

_load_env()

logger = logging.getLogger("WebCircuitReferenceSearch")

IEEE_XPLORE_API_URL = "https://ieeexploreapi.ieee.org/api/v1/search/articles"
IEEE_OPENALEX_HOST_ORG = "https://openalex.org/P4310319808"  # IEEE Organization ID in OpenAlex


class WebCircuitReferenceSearcher:
    """
    IEEE Academic Literature retriever (IEEE Xplore API + OpenAlex).
    Tavily and Exa are intentionally excluded; IEEE_API_KEY is strictly required.
    """

    def __init__(
        self,
        tavily_api_key: str | None = None,
        exa_api_key: str | None = None,
        ieee_api_key: str | None = None,
        timeout_s: float = 12.0,
    ):
        _load_env()
        self.ieee_api_key = (
            ieee_api_key
            or os.environ.get("IEEE_API_KEY")
            or ""
        ).strip()
        if not self.ieee_api_key:
            raise RuntimeError(
                "Missing required API key 'IEEE_API_KEY' for WebCircuitReferenceSearcher. "
                "Set IEEE_API_KEY in your environment or .env."
            )
        self.timeout_s = timeout_s
        self._cache: dict[str, dict[str, Any]] = {}

    @staticmethod
    def normalize_ieee_query(query: str, max_terms: int = 5) -> str:
        """
        Compacts verbose agent queries into 4-5 core IEEE technical keywords.
        IEEE Xplore & OpenAlex treat all words as a strict boolean AND; long queries
        or military part suffixes (LM741-MIL, LM741_MIL) cause 0-result failures.
        """
        q = re.sub(r"\b[A-Za-z]{2}\d{3,4}[A-Za-z0-9_-]*\b", " ", query)
        noise = {
            "mil", "spice", "netlist", "subckt", "internal", "schematic", "model",
            "circuit", "transistor", "level", "equivalent", "application", "note",
            "design", "stages", "topology", "range", "adjustment", "large", "signal",
            "the", "and", "for", "with", "from", "into", "using",
        }
        tokens: list[str] = []
        seen: set[str] = set()
        for raw_tok in re.findall(r"[A-Za-z]{3,}", q):
            low = raw_tok.lower()
            if low in noise or low in seen:
                continue
            seen.add(low)
            tokens.append(low)
            if len(tokens) >= max_terms:
                break
        if not tokens:
            return "operational amplifier differential pair"
        return " ".join(tokens)

    def search_ieee_academic(
        self,
        query: str,
        max_results: int = 3
    ) -> dict[str, Any]:
        """
        Direct OpenAlex / IEEE literature search for peer-reviewed circuit design papers.
        Extracts papers from IEEE JSSC, IEEE TCAS, IEEE Access, and related journals,
        reconstructs full technical abstracts, and highlights circuit design rationale.
        Operates completely standalone with 0 external daemon dependencies.
        """
        clean_q = self.normalize_ieee_query(query, max_terms=5)
        if not clean_q:
            return {"provider": "ieee_academic", "ok": False, "papers": []}

        papers: list[dict[str, Any]] = []

        # 1. Primary Query: Official IEEE Xplore API using IEEE_API_KEY (with progressive 3-term retry)
        candidate_queries = [clean_q]
        short_q = self.normalize_ieee_query(query, max_terms=3)
        if short_q and short_q != clean_q:
            candidate_queries.append(short_q)

        for q_try in candidate_queries:
            encoded_try = urllib.parse.quote(q_try)
            url_ieee_api = (
                f"{IEEE_XPLORE_API_URL}?apikey={urllib.parse.quote(self.ieee_api_key)}"
                f"&querytext={encoded_try}&max_records={max_results}"
            )
            req_ieee = urllib.request.Request(
                url_ieee_api,
                headers={"Accept": "application/json", "User-Agent": "AnalogVerifier/2.0"}
            )
            try:
                with urllib.request.urlopen(req_ieee, timeout=self.timeout_s) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    for art in (data.get("articles") or [])[:max_results]:
                        authors_list = [
                            a.get("full_name", "")
                            for a in (art.get("authors") or {}).get("authors", [])[:3]
                            if a.get("full_name")
                        ]
                        doi = art.get("doi") or ""
                        papers.append({
                            "title": art.get("title") or "Untitled IEEE Paper",
                            "venue": art.get("publication_title") or "IEEE Xplore",
                            "year": str(art.get("publication_year") or ""),
                            "authors": authors_list,
                            "doi": doi,
                            "url": art.get("html_url") or (f"https://doi.org/{doi}" if doi else ""),
                            "abstract": (art.get("abstract") or "").strip()[:1600],
                        })
                if papers:
                    break
            except Exception as e:
                logger.warning(f"IEEE Xplore API search error for '{q_try}': {e}")

        encoded_q = urllib.parse.quote(short_q or clean_q)

        if papers:
            return {
                "provider": "ieee_xplore",
                "ok": True,
                "count": len(papers),
                "papers": papers,
            }

        # 2. Fallback: OpenAlex IEEE-filtered works if IEEE Xplore returned 0 articles
        url_ieee = (
            f"https://api.openalex.org/works?search={encoded_q}"
            f"&per-page={max_results}&filter=primary_location.source.host_organization:{IEEE_OPENALEX_HOST_ORG}"
        )
        req = urllib.request.Request(
            url_ieee,
            headers={"User-Agent": "AnalogVerifier/2.0 (mailto:engineering@analogverifier.org)"}
        )

        raw_items = []
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                raw_items = data.get("results", [])
        except Exception as e:
            logger.warning(f"IEEE filtered search error for '{clean_q}': {e}")

        # 2. Fallback: If IEEE host org filter returned fewer than 2 results, supplement with general engineering works
        if len(raw_items) < 2:
            url_fallback = f"https://api.openalex.org/works?search={encoded_q}&per-page={max_results}"
            req_fb = urllib.request.Request(
                url_fallback,
                headers={"User-Agent": "AnalogVerifier/2.0 (mailto:engineering@analogverifier.org)"}
            )
            try:
                with urllib.request.urlopen(req_fb, timeout=self.timeout_s) as resp:
                    data_fb = json.loads(resp.read().decode("utf-8"))
                    raw_fallback = data_fb.get("results", [])
                    seen_ids = {w.get("id") for w in raw_items}
                    for fb_w in raw_fallback:
                        if fb_w.get("id") not in seen_ids:
                            raw_items.append(fb_w)
                            if len(raw_items) >= max_results:
                                break
            except Exception as e:
                logger.warning(f"Academic fallback search error for '{clean_q}': {e}")

        # 3. Parse metadata and reconstruct inverted index abstracts
        for w in raw_items[:max_results]:
            title = w.get("title") or "Untitled Academic Paper"
            doi = w.get("doi") or ""
            year = str(w.get("publication_year") or "")
            loc = w.get("primary_location") or {}
            source_obj = loc.get("source") or {}
            venue = source_obj.get("display_name") or "IEEE / Academic Journal"
            landing_url = loc.get("landing_page_url") or doi or f"https://doi.org/{doi}"

            # Reconstruct abstract from inverted index
            inv = w.get("abstract_inverted_index") or {}
            abstract = ""
            if inv:
                pos_list = []
                for word, positions in inv.items():
                    for p in positions:
                        pos_list.append((p, word))
                pos_list.sort(key=lambda x: x[0])
                abstract = " ".join(item[1] for item in pos_list)

            # Authors
            authors = [
                a.get("author", {}).get("display_name", "")
                for a in w.get("authorships", [])[:3]
                if a.get("author", {}).get("display_name")
            ]

            papers.append({
                "title": title,
                "venue": venue,
                "year": year,
                "authors": authors,
                "doi": doi,
                "url": landing_url,
                "abstract": abstract.strip()[:1600],
            })

        return {
            "provider": "ieee_academic",
            "ok": bool(papers),
            "count": len(papers),
            "papers": papers
        }

    def search_tavily(
        self,
        query: str,
        max_results: int = 4,
        search_depth: str = "basic"
    ) -> dict[str, Any]:
        """Queries Tavily Search API with non-technical domain filtering."""
        if not self.tavily_api_key:
            return {"provider": "tavily", "ok": False, "error": "Missing TAVILY_API_KEY", "results": []}

        payload = {
            "api_key": self.tavily_api_key,
            "query": query,
            "search_depth": search_depth,
            "include_answer": True,
            "include_raw_content": False,
            "max_results": max_results,
            "exclude_domains": [
                "youtube.com", "youtu.be", "pinterest.com",
                "instructables.com", "reddit.com", "quora.com"
            ],
        }
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "AnalogVerifier-Hermes/2.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            results = []
            for item in data.get("results", []):
                results.append({
                    "source": "tavily",
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": (item.get("content") or "")[:1500],
                    "score": item.get("score", 0.0),
                })
            return {
                "provider": "tavily",
                "ok": True,
                "answer": data.get("answer") or "",
                "results": results,
            }
        except Exception as e:
            logger.warning(f"Tavily search error for '{query}': {e}")
            return {"provider": "tavily", "ok": False, "error": str(e), "answer": "", "results": []}

    def search_exa(
        self,
        query: str,
        num_results: int = 4
    ) -> dict[str, Any]:
        """Queries Exa Neural Search API for datasheets, app notes, and SPICE netlists."""
        if not self.exa_api_key:
            return {"provider": "exa", "ok": False, "error": "Missing EXA_API_KEY", "results": []}

        payload = {
            "query": query,
            "type": "auto",
            "numResults": num_results,
            "contents": {
                "text": {"maxCharacters": 2000},
                "highlights": {"numSentences": 3},
            },
        }
        req = urllib.request.Request(
            "https://api.exa.ai/search",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": self.exa_api_key,
                "Content-Type": "application/json",
                "User-Agent": "AnalogVerifier-Hermes/2.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            results = []
            for item in data.get("results", []):
                highlights = item.get("highlights") or []
                text = item.get("text") or ""
                snippet = "\n".join(highlights) if highlights else text[:1500]
                if text and snippet != text[:1500]:
                    snippet = f"{snippet}\n{text[:1000]}"
                results.append({
                    "source": "exa",
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": snippet.strip()[:1800],
                    "score": item.get("score", 0.0),
                })
            return {
                "provider": "exa",
                "ok": True,
                "results": results,
            }
        except Exception as e:
            logger.warning(f"Exa search error for '{query}': {e}")
            return {"provider": "exa", "ok": False, "error": str(e), "results": []}

    @staticmethod
    def _extract_spice_hints(texts: list[str]) -> list[str]:
        """
        Extracts clean, physical SPICE netlist blocks or model lines.
        Filters out LTspice proprietary behavioral devices (A... SCHMITT, SRFLOP)
        and malformed single-line snippets.
        """
        hints: list[str] = []
        for txt in texts:
            if not txt:
                continue

            # Extract subcircuits
            for m in re.finditer(r'(\.subckt\b[\s\S]{10,2000}?\.ends\b[^\r\n]*)', txt, re.IGNORECASE):
                snippet = m.group(1).strip()
                # Filter out LTspice proprietary A-devices which break standard Ngspice
                if re.search(r'\bA\d+\s+.*\b(?:SCHMITT|SRFLOP|DIFF|OTA)\b', snippet, re.IGNORECASE):
                    continue
                # Require genuine circuit primitives
                if not re.search(r'\b[QMRCD]\w*\b', snippet):
                    continue
                if snippet not in hints:
                    hints.append(snippet)

            # Extract physical model cards
            for m in re.finditer(r'(?m)^(\.model\s+[A-Za-z0-9_]+\s+(?:NPN|PNP|NMOS|PMOS|D|SW|VSWITCH)\b[^\r\n]*)', txt, re.IGNORECASE):
                model_line = m.group(1).strip()
                if model_line not in hints:
                    hints.append(model_line)

        return hints[:6]

    def search(
        self,
        query: str,
        exa_query: str | None = None,
        ieee_query: str | None = None,
        max_results_per_engine: int = 4
    ) -> dict[str, Any]:
        """
        Executes parallel IEEE Academic, Tavily, and Exa searches.
        Formats a structured engineering context with peer-reviewed literature,
        circuit design rationale, and physical SPICE models.
        """
        q_ieee = (ieee_query or query).strip()

        cache_key = f"ieee||{q_ieee.lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        ieee_res = self.search_ieee_academic(q_ieee, max_results_per_engine)
        tavily_res: dict[str, Any] = {"ok": False, "answer": "", "results": []}
        exa_res: dict[str, Any] = {"ok": False, "results": []}

        seen_urls = set()
        combined_results: list[dict[str, Any]] = []
        raw_texts: list[str] = []

        if tavily_res.get("answer"):
            raw_texts.append(tavily_res["answer"])

        for item in tavily_res.get("results", []) + exa_res.get("results", []):
            url = (item.get("url") or "").strip()
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            combined_results.append(item)
            raw_texts.append(item.get("snippet", ""))

        spice_hints = self._extract_spice_hints(raw_texts)

        # -------------------------------------------------------------
        # Format Structured Engineering Markdown
        # -------------------------------------------------------------
        md_lines = [f"### Circuit Design References & Literature (Target: `{q_ieee}`)\n"]

        # 1. IEEE Academic Literature (Peer-Reviewed Topology & Rationale)
        ieee_papers = ieee_res.get("papers", [])
        if ieee_papers:
            md_lines.append("#### 📚 IEEE & Peer-Reviewed Academic Literature (Design Rationale & Sizing):")
            for idx, p in enumerate(ieee_papers, 1):
                p_title = p.get("title", "Research Paper")
                p_venue = p.get("venue", "IEEE Journal")
                p_year = p.get("year", "")
                p_doi = p.get("doi") or p.get("url", "")
                p_authors = ", ".join(p.get("authors", []))
                md_lines.append(f"{idx}. **{p_title}** ({p_year})")
                md_lines.append(f"   - **Venue**: *{p_venue}* | Authors: {p_authors} | DOI: {p_doi}")
                if p.get("abstract"):
                    snippet = re.sub(r'\s+', ' ', p['abstract']).strip()[:500]
                    md_lines.append(f"   - **Design Insights**: {snippet}...\n")

        # 2. Synthesized Architectural Overview (Tavily)
        if tavily_res.get("answer"):
            clean_ans = re.sub(r'\s+', ' ', tavily_res["answer"]).strip()
            md_lines.append(f"#### 🏛️ Synthesized Architecture Overview:\n{clean_ans}\n")

        # 3. Clean Physical SPICE Models / Subcircuits
        if spice_hints:
            md_lines.append("#### ⚡ Extracted SPICE Subcircuit & Device Models (Physical Only):")
            for h in spice_hints:
                md_lines.append(f"```spice\n{h}\n```")

        # 4. Manufacturer Application Notes & Technical Sources
        if combined_results:
            md_lines.append("#### 🌐 Manufacturer Technical Application Notes & Web References:")
            for idx, r in enumerate(combined_results[:5], 1):
                src_tag = r.get("source", "web").upper()
                title = r.get("title") or "Technical Reference"
                url = r.get("url") or ""
                snippet = re.sub(r'\s+', ' ', r.get("snippet") or "").strip()[:350]
                md_lines.append(f"{idx}. **[{src_tag}] {title}** ({url})\n   - {snippet}")

        formatted_markdown = "\n".join(md_lines)

        out = {
            "status": "SUCCESS" if ieee_res.get("ok") else "PARTIAL_OR_FAILED",
            "query": q_ieee,
            "ieee_ok": bool(ieee_res.get("ok")),
            "tavily_ok": bool(tavily_res.get("ok")),
            "exa_ok": bool(exa_res.get("ok")),
            "ieee_papers": ieee_papers,
            "tavily_answer": tavily_res.get("answer", ""),
            "spice_hints": spice_hints,
            "references_count": len(combined_results) + len(ieee_papers),
            "references": combined_results[:8],
            "formatted_markdown": formatted_markdown,
        }
        self._cache[cache_key] = out
        return out

    def search_circuit_reference(
        self,
        ic_name: str,
        category: str = "",
        extra_query: str = "",
        failed_specs: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Builds specialized analog IC topology & SPICE reference queries
        for IEEE Academic Literature, Tavily, and Exa.
        """
        clean_ic = re.sub(r'_(?:VERIFIED|HERMES|TEST|DUT)$', '', ic_name, flags=re.IGNORECASE)
        cat_str = category.replace("_", " ") if category else "analog IC"
        spec_str = ""
        if failed_specs:
            spec_str = " " + " ".join(failed_specs[:3])

        # IEEE academic query: focused on circuit architecture, stages, and compensation
        q_ieee = f"{cat_str} {clean_ic} circuit differential pair transistor compensation topology {extra_query}".strip()

        # Tavily query: engineering schematic and transistor topology
        q_tavily = (
            f"{clean_ic} {cat_str} internal circuit schematic transistor topology "
            f"SPICE model design stages {extra_query}{spec_str}"
        ).strip()

        # Exa query: focused on SPICE subcircuit netlists and application notes
        q_exa = (
            f"{clean_ic} {cat_str} SPICE subcircuit netlist .subckt transistor level "
            f"equivalent schematic application note {extra_query}"
        ).strip()

        return self.search(
            query=q_tavily,
            exa_query=q_exa,
            ieee_query=q_ieee,
            max_results_per_engine=4
        )
