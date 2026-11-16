"""
Dual-Harness² Co-Evolution Coordinator.
Synchronizes the bidirectional evolution of:
  1. Circuit Synthesizer (Harness2CircuitArchitect, C1-C8)
  2. Neuro-Symbolic Verifier (Harness2VerifierArchitect, V1-V3)
Anchored strictly by physical analog circuit rules and the Golden Oracle Gatekeeper.
"""
from __future__ import annotations

import logging
from typing import Any

from ai_analog_designer.circuit_synthesis.harness2.harness2_architect import (
    Harness2CircuitArchitect,
)

from .harness2_verifier_architect import Harness2VerifierArchitect

logger = logging.getLogger("DualHarness2Coordinator")


class DualHarness2Coordinator:
    """
    Co-evolutionary manager ensuring that whenever the Synthesizer faces unsupported specs,
    the Verifier autonomously evolves physical measurement fixtures (validated against Golden Models)
    before the Synthesizer iterates on circuit convergence.
    """

    def __init__(
        self,
        circuit_architect: Harness2CircuitArchitect | None = None,
        verifier_architect: Harness2VerifierArchitect | None = None
    ):
        self.circuit_architect = circuit_architect or Harness2CircuitArchitect()
        self.verifier_architect = verifier_architect or Harness2VerifierArchitect()
        self.anchor = self.verifier_architect.anchor

        # Apply any pre-existing verifier evolutions immediately to spec_planner
        self.verifier_architect.patch_spec_planner()

    def prepare_dual_evolution_for_ic(
        self,
        ic_info: dict[str, Any],
        pins: list[dict[str, Any]],
        specifications: list[dict[str, Any]],
        spec_plan: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Step 1 of Co-evolution: Checks if target IC requires Verifier evolution.
        If unsupported specs exist, evolves the Verifier first using Golden Oracle Gatekeeper.
        """
        part_name = ic_info.get("name", "ANALOG_IC")
        logger.info(f"=== [Dual-Harness²] Synchronizing Co-evolution for {part_name} ===")

        unsupported = self.verifier_architect.identify_unsupported_specs(specifications, spec_plan)
        if unsupported:
            logger.info(f"  [Verifier Evolution] Detected {len(unsupported)} unmeasured/unsupported specs: {[s.get('symbol') for s in unsupported]}")
            evolve_res = self.verifier_architect.evolve_verifier_for_specs(ic_info, pins, unsupported)
            self.verifier_architect.patch_spec_planner()
            return {
                "verifier_evolved": True,
                "evolved_count": evolve_res.get("evolved_count", 0),
                "unsupported_remaining": len(unsupported) - evolve_res.get("evolved_count", 0)
            }
        else:
            logger.info("  [Verifier Status] Verifier fully covers target device specifications.")
            return {"verifier_evolved": False, "evolved_count": 0, "unsupported_remaining": 0}
