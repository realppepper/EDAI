"""
Harness² Verifier Architect: Recursive Self-Improvement Engine for the Neuro-Symbolic Verifier.
Completes the Dual-Harness² architecture by allowing the Verifier to autonomously evolve
alongside the Circuit Synthesizer through Propose-Probe-Compose cycles anchored by
the Golden Oracle Gatekeeper.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from ai_analog_designer.llm_client import LLMClient

from .golden_oracle_anchor import GoldenOracleAnchor
from .harness2_verifier_tree import Harness2VerifierTree

logger = logging.getLogger("Harness2VerifierArchitect")


class Harness2VerifierArchitect:
    """
    Autonomous architect for the Verifier.
    Expands spec classification (V1), fixture circuits (V2), and unit scaling (V3)
    when unsupported IC categories or complex specs (THD, settling, frequency, dropout) are encountered.
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        experience_dir: str = "harness2_library/verifier_experience"
    ):
        self.llm_client = llm_client or LLMClient()
        self.anchor = GoldenOracleAnchor()
        self.tree = Harness2VerifierTree()
        self.experience_dir = os.path.abspath(experience_dir)
        os.makedirs(self.experience_dir, exist_ok=True)
        self._load_persistent_experience()

    def _load_persistent_experience(self):
        """Loads accumulated verifier lessons from the persistent library."""
        exp_file = os.path.join(self.experience_dir, "VERIFIER_EXPERIENCE.json")
        if os.path.exists(exp_file):
            try:
                with open(exp_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.tree = Harness2VerifierTree.from_dict(data)
                logger.info(f"Loaded {len(self.tree.v1_kind_rules)} classifier rules and {len(self.tree.v2_fixture_templates)} fixtures from verifier experience.")
            except Exception as e:
                logger.warning(f"Could not load verifier experience: {e}")

    def save_persistent_experience(self):
        """Persists approved verifier lessons to disk."""
        exp_file = os.path.join(self.experience_dir, "VERIFIER_EXPERIENCE.json")
        try:
            with open(exp_file, "w", encoding="utf-8") as f:
                json.dump(self.tree.to_dict(), f, indent=2)
            logger.info("Persisted evolved verifier rules to library.")
        except Exception as e:
            logger.warning(f"Could not save verifier experience: {e}")

    def identify_unsupported_specs(
        self,
        specifications: list[dict[str, Any]],
        spec_plan: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Identifies specs marked as unsupported or lacking physical fixtures."""
        unsupported = []
        items = spec_plan.get("items") or spec_plan.get("rows") or []
        if items:
            seen_syms = set()
            for idx, it in enumerate(items):
                st = it.get("status") or it.get("result") or ""
                if st in ("UNSUPPORTED_KIND", "NO_FIXTURE"):
                    sym = it.get("symbol")
                    if sym and sym not in seen_syms:
                        seen_syms.add(sym)
                        spec_obj = specifications[idx] if idx < len(specifications) else it
                        unsupported.append(spec_obj)
            return unsupported
        for s in specifications:
            unsupported.append(s)
        return unsupported

    def evolve_verifier_for_specs(
        self,
        ic_info: dict[str, Any],
        pins: list[dict[str, Any]],
        unsupported_specs: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Executes Propose-Probe-Compose cycle for the Verifier:
          1. Propose: LLM synthesizes new classification regex & pure physical analog fixture deck
          2. Probe: Golden Oracle runs fixture against TI/ADI macromodels to verify 100% accuracy
          3. Compose: Gatekeeper approves and permanently merges new fixture into verifier library
        """
        if not unsupported_specs:
            return {"evolved_count": 0, "rules": []}

        device_class = ic_info.get("category", "analog_ic")
        logger.info(f"[Dual-Harness² Verifier] Proposing evolution for {len(unsupported_specs)} unsupported specs in {device_class}...")

        evolved_rules = []

        for spec in unsupported_specs[:5]:  # Batch first 5 new specs
            sym = spec.get("symbol", "SPEC")
            name = spec.get("name", "")
            unit = spec.get("unit", "")
            cond = spec.get("test_conditions", "")

            # 1. PROPOSE (LLM Synthesis of pure physical fixture)
            prompt = f"""You are a Principal Test & Verification Architect in Analog IC Design.
Design an automated LTspice physical measurement fixture for an unsupported specification.

## TARGET SPECIFICATION:
- Symbol: {sym}
- Name: {name}
- Expected Unit: {unit}
- Test Conditions: {cond}
- DUT Category: {device_class}

## STRICT INVARIANTS (MANDATORY):
1. Pure Physical Analog Stimulus:
   - Use standard independent voltage/current sources: `V... DC`, `SINE(0 amp freq delay)`, `PULSE(v1 v2 td tr tf pw per)`
   - Use passive components: `R...`, `C...`, `L...`
   - STRICTLY PROHIBITED: ABSOLUTELY NO BEHAVIORAL SOURCES (Bxxx elements, V=if(...), I=if(...), table, laplace).
   - STRICTLY PROHIBITED: ABSOLUTELY NO LOGIC A-DEVICES.
2. DUT Instantiation:
   - Must include `.include "golden_dut.sub"`
   - Must instantiate DUT with subcircuit pins: `XDUT <nodes...> DUT`
3. Measurement Directives:
   - Must generate one or more `.meas` lines computing the target parameter.
   - Output measurement name should be '{sym.lower()}'.

## OUTPUT FORMAT:
Respond with:
<kind_name>canonical_kind_slug</kind_name>
<symbol_regex>^REGEX$</symbol_regex>
<name_regex>regex_for_name</name_regex>
<fixture_deck>
* Pure physical testbench
.include "golden_dut.sub"
...
.end
</fixture_deck>
"""
            resp = self.llm_client.complete(prompt, max_tokens=2048, tag="verifier_propose")

            # Parse proposal
            m_kind = re.search(r'<kind_name>(.*?)</kind_name>', resp, re.IGNORECASE)
            m_sym = re.search(r'<symbol_regex>(.*?)</symbol_regex>', resp, re.IGNORECASE)
            m_deck = re.search(r'<fixture_deck>(.*?)</fixture_deck>', resp, re.DOTALL | re.IGNORECASE)

            if not (m_kind and m_sym and m_deck):
                logger.warning(f"Could not parse verifier proposal for spec '{sym}'.")
                continue

            kind_slug = m_kind.group(1).strip()
            sym_regex = m_sym.group(1).strip()
            deck_code = m_deck.group(1).strip()

            # 2. PROBE (Golden Oracle Anchor Gatekeeper)
            audit_res = self.anchor.audit_fixture_candidate(
                target_kind=kind_slug,
                target_class=device_class,
                proposed_deck_template=deck_code,
                expected_range=(spec.get("min"), spec.get("max")),
                unit=unit
            )

            logger.info(f"  [Golden Oracle Gatekeeper] Spec '{sym}' -> Accepted: {audit_res['accepted']} | Pass Rate: {audit_res['pass_rate']}% | Diagnostic: {audit_res['diagnostic']}")

            # 3. COMPOSE (Only if Golden Oracle Gatekeeper validates 100% pass and 0 false verdicts)
            if audit_res["accepted"]:
                rule = {
                    "classes": [device_class.lower()],
                    "symbol_regex": sym_regex,
                    "name_regex": re.escape(name.lower()),
                    "kind": kind_slug,
                    "canonical_unit": unit,
                    "magnitude_compare": False
                }
                self.tree.register_classifier_rule(rule)
                self.tree.register_fixture_template(kind_slug, deck_code)
                evolved_rules.append(rule)
            else:
                logger.warning(f"Proposal for '{sym}' REJECTED by Golden Oracle Gatekeeper to prevent reward hacking.")

        if evolved_rules:
            self.save_persistent_experience()

        return {
            "evolved_count": len(evolved_rules),
            "rules": evolved_rules
        }

    def patch_spec_planner(self):
        """Dynamically patches spec_planner.KIND_RULES with evolved classification rules."""
        from ai_analog_designer.neuro_symbolic_verifier import spec_planner
        existing_kinds = {r[3] for r in spec_planner.KIND_RULES}
        added = 0
        for r in self.tree.v1_kind_rules:
            if r["kind"] not in existing_kinds:
                entry = (
                    tuple(r["classes"]),
                    r["symbol_regex"],
                    r["name_regex"],
                    r["kind"],
                    r["canonical_unit"],
                    r["magnitude_compare"]
                )
                spec_planner.KIND_RULES.append(entry)
                existing_kinds.add(r["kind"])
                added += 1
        if added > 0:
            logger.info(f"[Dual-Harness² Verifier] Injected {added} evolved classification rules into active spec_planner.")
