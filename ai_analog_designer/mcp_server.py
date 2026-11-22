"""
Unified EDAI / AnalogVerifier MCP Server (FastMCP).
Exposes deterministic circuit synthesis, gm/ID sizing, SPICE syntax/physical validation,
LTspice/ngspice simulation & parameter sweep, SVG schematic rendering, and IEEE academic
literature search over MCP stdio so external AI coding agents (Antigravity, Claude Code,
Cursor) can operate the exact same core tools as the autonomous Web Studio backend.

Usage:
  python -m ai_analog_designer.mcp_server
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore[no-redef]

from ai_analog_designer.circuit_synthesis.flan_t5_topology import generate_topology_candidates
from ai_analog_designer.circuit_synthesis.gm_id_sizer import auto_size, check_opamp_pdg, parse_table_text
from ai_analog_designer.circuit_synthesis.netlist_validator import NetlistValidator
from ai_analog_designer.circuit_synthesis.schematic_svg import render_schematic_svg
from ai_analog_designer.hermes_core.base_circuit_generator import validate_any_netlist
from ai_analog_designer.hermes_core.ieee_mcp_client import IEEEMCPClient
from ai_analog_designer.neuro_symbolic_verifier.spice_sweep_engine import optimize, resolve_simulator

mcp = MCPServer("edai-analogverifier")


@mcp.tool()
def search_ieee_papers(query: str, max_results: int = 3, publication_title: str = "") -> dict[str, Any]:
    """Search peer-reviewed IEEE circuit design papers (abstracts, DOIs, venues)."""
    # Pass mcp_command="" inside the MCP server itself to prevent recursive stdio spawning
    client = IEEEMCPClient(mcp_command="", mcp_args=[])
    return client.search_papers(query=query, max_results=max_results, publication_title=publication_title)


@mcp.tool()
def read_ieee_paper(article_number: str, needed_reason: str = "") -> dict[str, Any]:
    """Read official IEEE article full-text JATS XML body (sections, paragraphs, equations) by article_number."""
    from ai_analog_designer.hermes_core.ieee_mcp_client import fetch_ieee_article_body

    if not str(needed_reason or "").strip():
        return {"ok": False, "full_text_retrieved": False, "error": "A concrete needed_reason is required"}
    return fetch_ieee_article_body(str(article_number))


@mcp.tool()
def extract_hkg_pdg(pdf_path: str, max_pages: int = 15) -> dict[str, Any]:
    """Extract pin interface and Port Dependency Graph (PDG) schedule from a datasheet PDF."""
    from ai_analog_designer.pdf_to_graph import PDGVisualizer

    res = PDGVisualizer.extract_from_pdf(pdf_path, max_pages=max_pages)
    pins = res.get("pins", [])
    schedule = res.get("schedule", {})
    opamp_fit = check_opamp_pdg(pins)
    return {
        "ok": True,
        "ic_name": res.get("ic_info", {}).get("name", Path(pdf_path).stem),
        "pins": pins,
        "schedule_us": {k: round(v * 1e6, 2) for k, v in schedule.items()},
        "opamp_5pin_check": opamp_fit,
    }


@mcp.tool()
def tool_generate_topology_candidates(
    specifications_json: str = "[]",
    prompt_hint: str = "",
    max_candidates: int = 6,
    auto_size_preview: bool = True,
    subckt_name: str = "OPAMP",
) -> dict[str, Any]:
    """Generate rule-validated op-amp topology candidates via FLAN-T5 / modular block library."""
    specs = json.loads(specifications_json) if specifications_json else []
    return generate_topology_candidates(
        specifications=specs,
        prompt_hint=prompt_hint,
        max_candidates=max_candidates,
        auto_size_preview=auto_size_preview,
        subckt_name=subckt_name,
    )


@mcp.tool()
def tool_auto_size_gm_id(
    structure_table: str,
    unit_current_ua: float = 20.0,
    output_scale: float = 1.0,
    simulator: str = "auto",
    subckt_name: str = "OPAMP",
) -> dict[str, Any]:
    """Size an op-amp structure table deterministically using GF180 6V gm/ID curves."""
    tbl = parse_table_text(structure_table)
    return auto_size(
        tbl,
        unit_current=unit_current_ua * 1e-6,
        output_scale=output_scale,
        simulator=simulator,
        subckt_name=subckt_name,
    )


@mcp.tool()
def tool_validate_netlist_syntax(netlist: str, subckt_name: str = "DUT") -> dict[str, Any]:
    """Validate SPICE netlist syntax, port alignment, and strict physical analog rules."""
    return validate_any_netlist(netlist, subckt_name=subckt_name)


@mcp.tool()
def tool_sweep_parameters_grid(
    netlist: str,
    settings_json: str,
    simulator: str = "ltspice",
    simulator_path: str = "",
) -> dict[str, Any]:
    """Run bounded LTspice/ngspice parameter optimization sweep on a single-file SPICE deck."""
    settings = json.loads(settings_json)
    cfg = {"simulator": simulator, "simulator_path": simulator_path}
    resolve_simulator(cfg)
    with tempfile.TemporaryDirectory(prefix="edai_mcp_sweep_") as tmpdir:
        return optimize(netlist, settings, cfg, Path(tmpdir))


@mcp.tool()
def tool_render_schematic_svg(structure_table: str = "", netlist: str = "", title: str = "Circuit Schematic") -> dict[str, Any]:
    """Render an SVG schematic from either a structure table or a SPICE netlist."""
    return render_schematic_svg(
        structure_table=structure_table or None,
        netlist=netlist or None,
        title=title,
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
