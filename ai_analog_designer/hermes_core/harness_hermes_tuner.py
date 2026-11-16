"""
Harness²-Hermes Tuner: Bridges and shapes the Hermes Agent using the Harness² 8-component framework (C1-C8).
Converts HarnessTree into Hermes workspace assets (SOUL.md, MEMORY.md, skills/analog_blueprints/)
and synchronizes newly evolved skills and memories back into Harness² persistent storage.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from ai_analog_designer.circuit_synthesis.harness2.harness_library import HarnessLibrary
from ai_analog_designer.circuit_synthesis.harness2.harness_tree import HarnessTree

from .hermes_agent import HermesAgent

logger = logging.getLogger("HarnessHermesTuner")


class HarnessHermesTuner:
    """
    Governor & Meta-Tuner that refines Hermes Agent via Harness² (C1-C8).
    """

    def __init__(self, library_root: str = "harness2_library"):
        self.library = HarnessLibrary(root_dir=library_root)

    def bootstrap_tree(self, category: str, part_name: str, base_tree: HarnessTree | None = None) -> HarnessTree:
        """Bootstraps a HarnessTree from cross-task experience library."""
        tree = self.library.bootstrap_harness(category=category, base_tree=base_tree)

        # In addition to C3 lessons, pull blueprints from relevant experiences into C5 skills
        exps = self.library.retrieve_relevant_experiences(category)
        for exp in exps:
            h_tree = exp.get("harness_tree", {})
            past_skills = h_tree.get("c5_skills", {})
            for skill_name, skill_val in past_skills.items():
                if skill_name not in tree.c5_skills:
                    tree.c5_skills[skill_name] = skill_val

        logger.info(f"Bootstrapped HarnessTree for {part_name} ({category}) with {len(tree.c5_skills)} blueprint skills.")
        return tree

    def tune_hermes(
        self,
        agent: HermesAgent,
        tree: HarnessTree,
        category: str,
        part_name: str
    ) -> None:
        """
        Shapes and configures Hermes Agent using the 8 Harness² components:
          - C1 (System Prompt & Domain Directives) -> SOUL.md
          - C2 (Guardrails & Invariants) -> Invariant rules in SOUL.md
          - C3 (Experience Memory & Convergence Traps) -> memories/MEMORY.md
          - C4 (Tool Guidance & PDG Alignment) -> Tool instructions in SOUL.md
          - C5 (Skills / Blueprint Registry) -> skills/analog_blueprints/<name>/SKILL.md
          - C6-C8 (Scripts, Subagents, Plugins) -> Helper modules
        """
        logger.info(f"Tuning Hermes Agent with Harness² for {part_name} ({category})...")

        # 1. Tune C1 & C2 & C4 -> SOUL.md
        soul_content = f"""# Hermes Analog IC Designer Persona (SOUL.md)
Governed by Google Research Harness² Architecture (arXiv:2603.22472).

## Core Identity & Philosophy (C1 System Prompt)
{tree.c1_system_prompt.strip()}

## Strict Physical Analog Invariants & Guardrails (C2 Guardrails)
{tree.c2_guardrails.strip()}

## Tool Guidance & Simulation Alignment (C4 Tool Guidance)
{tree.c4_tool_guidance.strip()}
"""
        with open(agent.soul_path, "w", encoding="utf-8") as f:
            f.write(soul_content)

        # 2. Tune C3 -> memories/MEMORY.md
        memory_content = f"""# Hermes Long-Term Memory (MEMORY.md)
Accumulated design heuristics, convergence traps, and proven physical rules.

{tree.c3_memory.strip()}
"""
        with open(agent.memory_path, "w", encoding="utf-8") as f:
            f.write(memory_content)

        # 3. Tune C5 -> skills/analog_blueprints/
        self._populate_blueprint_skills(agent, tree.c5_skills, category)

        logger.info(f"Hermes Agent successfully tuned! Workspace ready at: {agent.workspace_dir}")

    def _populate_blueprint_skills(self, agent: HermesAgent, c5_skills: dict[str, Any], default_category: str):
        """Converts C5 skills dictionary into individual Hermes SKILL.md documents."""
        for skill_name, skill_data in c5_skills.items():
            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', skill_name).lower()
            skill_dir = os.path.join(agent.blueprints_dir, safe_name)
            os.makedirs(skill_dir, exist_ok=True)

            if isinstance(skill_data, str):
                body = skill_data
                desc = f"Domain Subcircuit Blueprint for {safe_name}"
            elif isinstance(skill_data, dict):
                body = skill_data.get("subckt_code", "") or skill_data.get("content", str(skill_data))
                desc = skill_data.get("description", f"Blueprint {safe_name}")
            else:
                body = str(skill_data)
                desc = f"Blueprint {safe_name}"

            skill_md = f"""---
name: {safe_name}
category: {default_category}
description: {desc[:120]}
---

# Blueprint Skill: {skill_name}

## Description
{desc}

## SPICE Topology & Netlist
```spice
{body.strip()}
```
"""
            skill_file = os.path.join(skill_dir, "SKILL.md")
            with open(skill_file, "w", encoding="utf-8") as f:
                f.write(skill_md)

    def sync_back_to_harness(
        self,
        agent: HermesAgent,
        tree: HarnessTree,
        task_id: str,
        category: str,
        score_before: float,
        score_after: float
    ) -> HarnessTree:
        """
        Synchronizes newly learned memories and created blueprint skills from Hermes back into HarnessTree & Library.
        """
        evolved_tree = tree.clone()

        # 1. Sync Memory from MEMORY.md
        if os.path.exists(agent.memory_path):
            with open(agent.memory_path, "r", encoding="utf-8") as f:
                new_mem = f.read()
            evolved_tree.c3_memory = new_mem

        # 2. Sync Blueprint Skills from skills/analog_blueprints/
        if os.path.exists(agent.blueprints_dir):
            for skill_entry in os.listdir(agent.blueprints_dir):
                skill_file = os.path.join(agent.blueprints_dir, skill_entry, "SKILL.md")
                if os.path.exists(skill_file):
                    try:
                        with open(skill_file, "r", encoding="utf-8") as f:
                            content = f.read()
                        m_code = re.search(r'```(?:spice)?\s*(.*?)\s*```', content, re.DOTALL)
                        code = m_code.group(1).strip() if m_code else content
                        evolved_tree.c5_skills[skill_entry] = code
                    except Exception:
                        pass

        # 3. If improvement occurred, record in persistent HarnessLibrary
        if score_after > score_before:
            cue = f"Synthesizing {task_id} ({category}) with Hermes Autonomous Agent"
            lesson = f"Evolved {len(evolved_tree.c5_skills)} blueprint skills and refined convergence rules in MEMORY.md."
            evidence = f"Pass rate improved from {score_before:.1f}% to {score_after:.1f}%."
            self.library.record_experience(
                task_id=task_id,
                category=category,
                cue=cue,
                lesson=lesson,
                evidence=evidence,
                tree=evolved_tree,
                score_before=score_before,
                score_after=score_after
            )
            logger.info(f"Recorded new experience in HarnessLibrary for {task_id} (+{score_after - score_before:.1f}%)")

        return evolved_tree
