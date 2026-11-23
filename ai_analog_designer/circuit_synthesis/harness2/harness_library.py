"""
Persistent Improvement Library for Harness² (Harnessing-Level Recursion).
Maintains cross-task accumulated experiences, failure modes, and adopted harness trees.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from .harness_tree import HarnessTree


class HarnessLibrary:
    """Persistent experience library storing adopted harness trees and lessons across IC tasks."""

    def __init__(self, root_dir: str = "harness2_library"):
        self.root_dir = os.path.abspath(root_dir)
        os.makedirs(self.root_dir, exist_ok=True)
        self.index_file = os.path.join(self.root_dir, "INDEX.json")
        self._ensure_index()

    def _ensure_index(self):
        if not os.path.exists(self.index_file):
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump({"experiences": [], "count": 0}, f, indent=2)

    def _normalize_category(self, category: str) -> str:
        s = str(category or "general").lower()
        if any(k in s for k in ("ref", "bandgap", "voltage reference")):
            return "voltage_reference"
        if any(k in s for k in ("opamp", "amplifier", "op-amp", "buffer")):
            return "operational_amplifier"
        if any(k in s for k in ("comparator", "comp")):
            return "comparator"
        if any(k in s for k in ("adc", "dac", "converter")):
            return "data_converter"
        return "general"

    def record_experience(
        self,
        task_id: str,
        category: str,
        cue: str,
        lesson: str,
        evidence: str,
        tree: HarnessTree,
        score_before: float,
        score_after: float
    ) -> None:
        """Stores a successful harness improvement and lesson (blocked in read-only eval mode)."""
        if os.environ.get("ANALOG_HARNESS2_READONLY", "0").strip().lower() in ("1", "true", "yes"):
            return
        norm_cat = self._normalize_category(category)
        entry_dir = os.path.join(self.root_dir, norm_cat, re.sub(r'[^a-zA-Z0-9_-]', '_', task_id))
        os.makedirs(entry_dir, exist_ok=True)

        exp_data = {
            "task_id": task_id,
            "category": norm_cat,
            "cue": cue,
            "lesson": lesson,
            "evidence": evidence,
            "score_before": score_before,
            "score_after": score_after,
            "delta_score": round(score_after - score_before, 2),
            "harness_tree": tree.to_dict()
        }

        # Write experience markdown and JSON
        with open(os.path.join(entry_dir, "EXPERIENCE.json"), "w", encoding="utf-8") as f:
            json.dump(exp_data, f, indent=2, ensure_ascii=False)

        md_content = f"""# Experience Record: {task_id} ({norm_cat})
**Score Delta:** {score_before:.1f}% -> {score_after:.1f}% (+{score_after - score_before:.1f}%)

## Cue
{cue}

## Lesson
{lesson}

## Evidence
{evidence}
"""
        with open(os.path.join(entry_dir, "EXPERIENCE.md"), "w", encoding="utf-8") as f:
            f.write(md_content)

        # Update index
        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                idx = json.load(f)
        except Exception:
            idx = {"experiences": [], "count": 0}

        idx["experiences"].append({
            "task_id": task_id,
            "category": norm_cat,
            "cue": cue[:120],
            "delta": round(score_after - score_before, 2),
            "path": os.path.relpath(entry_dir, self.root_dir)
        })
        idx["count"] = len(idx["experiences"])

        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(idx, f, indent=2, ensure_ascii=False)

    def retrieve_relevant_experiences(self, category: str) -> list[dict[str, Any]]:
        """Retrieves past lessons and skills for this category."""
        norm_cat = self._normalize_category(category)
        cat_dir = os.path.join(self.root_dir, norm_cat)
        if not os.path.exists(cat_dir):
            return []

        results = []
        for task_dir in os.listdir(cat_dir):
            p = os.path.join(cat_dir, task_dir, "EXPERIENCE.json")
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        results.append(json.load(f))
                except Exception:
                    pass
        return sorted(results, key=lambda x: x.get("delta_score", 0), reverse=True)

    def bootstrap_harness(self, category: str, base_tree: HarnessTree | None = None) -> HarnessTree:
        """Bootstraps a fresh harness tree with relevant past lessons from the library."""
        tree = (base_tree or HarnessTree()).clone()
        exps = self.retrieve_relevant_experiences(category)
        if not exps:
            return tree

        # Inject top 3 lessons into C3 Memory
        lessons_text = "\n### ACCUMULATED DOMAIN LESSONS (FROM HARNESS² LIBRARY):\n"
        for i, exp in enumerate(exps[:3], 1):
            lessons_text += f"{i}. [{exp.get('task_id')}] When: {exp.get('cue')}\n   Lesson: {exp.get('lesson')}\n"

        tree.c3_memory += lessons_text
        return tree
