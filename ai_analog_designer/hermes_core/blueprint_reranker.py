"""
Domain-Aware Circuit Blueprint & Academic Literature Reranker.
Reranks candidate SPICE blueprints and literature extracts using
multi-factor physical compatibility, pin overlap, and SPICE primitive density.
"""
from __future__ import annotations

import os
import re
from typing import Any


class BlueprintReranker:
    """
    Reranks candidate circuit blueprints and IEEE reference netlists
    to ensure the most physically viable, pin-compatible, and high-performance
    topology is surfaced to the synthesis agent.
    """

    def __init__(
        self,
        target_dut: str = "",
        target_category: str = "",
        target_pins: list[str] | None = None,
        min_elements: int = 3
    ):
        self.target_dut = (target_dut or "").lower().strip()
        self.target_category = (target_category or "").lower().strip()
        self.target_pins = [p.lower().strip() for p in (target_pins or [])]
        self.min_elements = min_elements

    def score_candidate(self, candidate: dict[str, Any], query: str = "") -> tuple[float, dict[str, float]]:
        """
        Calculates a composite relevance score for a candidate blueprint.
        Factors:
          1. Lexical / Semantic match against query & DUT name (weight: 0.30)
          2. Category alignment (weight: 0.25)
          3. Pin interface compatibility (weight: 0.20)
          4. SPICE physical primitive viability (.model, Q/M transistors) (weight: 0.25)
        """
        query_terms = [t.strip().lower() for t in re.split(r'[\s,_\-]+', query) if len(t.strip()) > 1]
        content = candidate.get("content", "")
        content_low = content.lower()
        title = candidate.get("title", "").lower()
        file_path = candidate.get("file", "").lower()

        # Factor 1: Lexical match
        lexical_hits = 0
        for term in query_terms:
            if term in title or term in file_path:
                lexical_hits += 2.0
            elif term in content_low:
                lexical_hits += 1.0
        
        # DUT name bonus
        if self.target_dut and (self.target_dut in title or self.target_dut in file_path or self.target_dut in content_low):
            lexical_hits += 5.0

        lexical_score = min(1.0, lexical_hits / max(4.0, len(query_terms) * 1.5))

        # Factor 2: Category alignment
        cat_score = 0.2  # baseline
        if self.target_category:
            if self.target_category in file_path or self.target_category in content_low:
                cat_score = 1.0
            else:
                # Partial category mapping
                cat_aliases = {
                    "comparator": ["cmp", "diff", "schmitt", "detector"],
                    "operational_amplifier": ["opamp", "amplifier", "buffer", "two-stage"],
                    "audio_amplifier": ["audio", "btl", "class-d", "speaker", "sound"],
                    "power_management": ["buck", "ldo", "regulat", "converter", "dcdc"],
                    "voltage_reference": ["bandgap", "shunt", "tl431", "reference"]
                }
                aliases = cat_aliases.get(self.target_category, [])
                if any(al in file_path or al in content_low for al in aliases):
                    cat_score = 0.8

        # Factor 3: Pin compatibility
        pin_score = 0.5
        if self.target_pins:
            matched_pins = 0
            for p in self.target_pins:
                # Check for pin token in content or subckt line
                if re.search(rf'\b{re.escape(p)}\b', content_low):
                    matched_pins += 1
            pin_score = matched_pins / max(1, len(self.target_pins))

        # Factor 4: Physical SPICE primitive viability
        spice_score = 0.0
        has_subckt = ".subckt" in content_low and ".ends" in content_low
        has_models = ".model" in content_low
        # Count physical transistors and passives
        bjt_count = len(re.findall(r'(?m)^\s*Q\w+', content))
        mos_count = len(re.findall(r'(?m)^\s*M\w+', content))
        res_count = len(re.findall(r'(?m)^\s*R\w+', content))
        has_bad_macros = bool(re.search(r'(?m)^\s*A\w+', content))

        if has_subckt:
            spice_score += 0.3
        if has_models:
            spice_score += 0.2
        if (bjt_count + mos_count) >= 2:
            spice_score += 0.3
        if res_count >= 1:
            spice_score += 0.2
        if has_bad_macros:
            spice_score = max(0.0, spice_score - 0.4)  # penalize non-physical behavioral gates

        # Composite weighted score
        final_score = (
            0.30 * lexical_score +
            0.25 * cat_score +
            0.20 * pin_score +
            0.25 * spice_score
        )

        details = {
            "lexical": round(lexical_score, 3),
            "category": round(cat_score, 3),
            "pin": round(pin_score, 3),
            "spice": round(spice_score, 3),
            "composite": round(final_score, 4)
        }
        return final_score, details

    def rerank(
        self,
        candidates: list[dict[str, Any]],
        query: str = "",
        top_k: int = 5
    ) -> list[dict[str, Any]]:
        """
        Reranks a list of candidate blueprints and returns top_k items
        with attached 'rerank_score' and 'rerank_details'.
        """
        if not candidates:
            return []

        scored = []
        for idx, cand in enumerate(candidates):
            score, details = self.score_candidate(cand, query=query)
            item = dict(cand)
            item["rerank_score"] = score
            item["rerank_details"] = details
            item["_idx"] = idx
            scored.append(item)

        # Optional LLM probabilistic semantic reranking blended with physical SPICE viability prior
        if len(scored) > 1 and os.environ.get("ANALOG_ENABLE_LLM_RERANKER", "1") == "1" and os.environ.get("ANALOG_DISABLE_LLM_PLANNER") != "1":
            try:
                import json

                from ..llm_client import LLMClient
                llm = LLMClient()
                if getattr(llm, "provider", "none") != "none":
                    briefs = [
                        {
                            "idx": it["_idx"],
                            "title": it.get("title") or it.get("file") or f"candidate_{it['_idx']}",
                            "snippet": str(it.get("content") or "")[:240],
                            "prior_score": it["rerank_score"],
                        }
                        for it in scored[:10]
                    ]
                    prompt = (
                        "You are an analog IC topology reranker. Score each candidate blueprint in [0.0, 1.0] "
                        f"for semantic and topological compatibility with target DUT='{self.target_dut}', "
                        f"category='{self.target_category}', pins={self.target_pins}, query='{query}'.\n"
                        f"Candidates: {json.dumps(briefs, ensure_ascii=False)}\n"
                        "Return JSON: {\"scores\": {\"0\": 0.85, ...}}"
                    )
                    res = llm.complete_json(
                        prompt,
                        system="Return only valid JSON with candidate index scores in [0.0, 1.0].",
                        temperature=0.0,
                        max_tokens=300,
                        stage="probabilistic_blueprint_reranker",
                    )
                    llm_scores = (res or {}).get("scores") if isinstance(res, dict) else None
                    if isinstance(llm_scores, dict):
                        for it in scored:
                            raw_s = llm_scores.get(str(it["_idx"]))
                            if isinstance(raw_s, (int, float)):
                                llm_val = min(1.0, max(0.0, float(raw_s)))
                                blended = round(0.65 * it["rerank_score"] + 0.35 * llm_val, 4)
                                it["rerank_details"]["llm_semantic"] = round(llm_val, 3)
                                it["rerank_details"]["composite"] = blended
                                it["rerank_score"] = blended
            except Exception:
                pass

        for it in scored:
            it.pop("_idx", None)

        # Sort descending by composite score
        scored.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored[:top_k]
