"""
Unified EDAI Circuit Studio Routes.
Connects seungcheol's Circuit Studio v03 UI/UX & SPICE sweep loop with jiyun's
FLAN-T5/block topology explorer, GF180 gm/ID sizer, SVG schematic renderer, and
AnalogVerifier's NetlistValidator, HKG/PDG, LLMClient, and IEEE MCP search.
"""
from __future__ import annotations

import copy
import io
import json
import mimetypes
import os
import secrets
import threading
import time
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any

from ai_analog_designer.circuit_synthesis.flan_t5_topology import generate_topology_candidates
from ai_analog_designer.circuit_synthesis.gm_id_sizer import auto_size, parse_table_text
from ai_analog_designer.circuit_synthesis.netlist_validator import NetlistValidator
from ai_analog_designer.circuit_synthesis.schematic_svg import render_schematic_svg
from ai_analog_designer.hermes_core.base_circuit_generator import (
    extract_evidence,
    generate_base_circuit,
    prepare_sources,
    validate_any_netlist,
    validate_confirmation,
)
from ai_analog_designer.hermes_core.ieee_mcp_client import IEEEMCPClient
from ai_analog_designer.neuro_symbolic_verifier.spice_sweep_engine import (
    optimize,
    resolve_simulator,
    validate_project,
)

EDAI_WEB_DIR = Path(__file__).resolve().parent / "edai_web"
EXAMPLES_DIR = EDAI_WEB_DIR / "examples"
RUNS_DIR = Path.cwd() / "output_edai_runs"

TOKEN = secrets.token_urlsafe(24)
LOCK = threading.RLock()
AI_LOCK = threading.Lock()
JOBS: dict[str, dict[str, Any]] = {}
REVIEWS: dict[str, dict[str, Any]] = {}
CONFIRMATIONS: dict[str, dict[str, Any]] = {}

STUDIO_CONFIG: dict[str, Any] = {
    "simulator": "ltspice" if os.name == "nt" else "ngspice",
    "simulator_path": "",
    "model": "",
}


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {k: copy.deepcopy(v) for k, v in job.items() if k not in ("cancel", "folder")}


def _sweep_worker(job: dict[str, Any], source: str, settings: dict[str, Any], config: dict[str, Any]) -> None:
    def on_result(r: dict[str, Any], best: dict[str, Any] | None) -> None:
        with LOCK:
            job["runs"].append(r)
            job["best_iteration"] = best["iteration"] if best else None

    try:
        result = optimize(source, settings, config, job["folder"], on_result, job["cancel"])
        with LOCK:
            job["state"] = "cancelled" if result["cancelled"] else "completed"
            job["feasible_count"] = result["feasible_count"]
    except Exception as exc:
        with LOCK:
            job["state"] = "failed"
            job["error"] = str(exc)


def _llm_status() -> dict[str, Any]:
    try:
        from ai_analog_designer.llm_client import LLMClient
        client = LLMClient(default_model=STUDIO_CONFIG.get("model") or None)
        routing = client.routing_config()
        return {
            "ai_ready": True,
            "llm_provider": client.provider,
            "ai_model": client.default_model,
            "extract_model": routing["routes"]["extract_specs"][0],
            "synth_model": routing["routes"]["hermes_initial"][0],
        }
    except Exception:
        return {
            "ai_ready": False,
            "llm_provider": os.environ.get("LLM_PROVIDER", "none"),
            "ai_model": STUDIO_CONFIG.get("model", ""),
            "extract_model": "",
            "synth_model": "",
        }


def _send_bytes(handler: Any, data: bytes, status: int = 200, mime: str = "text/html; charset=utf-8", download: str | None = None) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", mime)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    if download:
        handler.send_header("Content-Disposition", f'attachment; filename="{download}"')
    handler.end_headers()
    handler.wfile.write(data)


def handle_edai_get(handler: Any, path: str, query: dict[str, list[str]]) -> bool:
    """Handles unified EDAI Circuit Studio GET routes. Returns True if handled."""
    if path in ("/", "/index.html"):
        p = EDAI_WEB_DIR / "index.html"
        _send_bytes(handler, p.read_bytes(), mime="text/html; charset=utf-8")
        return True

    if path == "/bootstrap.js":
        _send_bytes(handler, f"window.EDAI_TOKEN={json.dumps(TOKEN)};".encode("utf-8"), mime="text/javascript; charset=utf-8")
        return True

    static_map = {
        "/app.js": ("app.js", "text/javascript; charset=utf-8"),
        "/review.js": ("review.js", "text/javascript; charset=utf-8"),
        "/edai_extensions.js": ("edai_extensions.js", "text/javascript; charset=utf-8"),
        "/style.css": ("style.css", "text/css; charset=utf-8"),
    }
    if path in static_map:
        fname, mime = static_map[path]
        _send_bytes(handler, (EDAI_WEB_DIR / fname).read_bytes(), mime=mime)
        return True

    if path.startswith("/studio/"):
        rel = urllib.parse.unquote(path[len("/studio/"):]) or "index.html"
        base = (EDAI_WEB_DIR / "studio").resolve()
        target = (base / rel).resolve()
        if not target.is_relative_to(base) or not target.is_file():
            handler.send_json({"error": "Not found"}, status=404)
            return True
        _send_bytes(handler, target.read_bytes(), mime=mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        return True

    if path == "/api/edai/status":
        try:
            engine, _ = resolve_simulator(STUDIO_CONFIG)
            ready, sim_err = True, None
        except ValueError as exc:
            engine, ready, sim_err = STUDIO_CONFIG.get("simulator"), False, str(exc)
        llm_info = _llm_status()
        handler.send_json({
            "simulator": engine,
            "ready": ready,
            "error": sim_err,
            "ieee_mcp_ready": IEEEMCPClient().is_mcp_configured(),
            **llm_info,
        })
        return True

    if path == "/api/settings":
        handler.send_json(STUDIO_CONFIG)
        return True

    if path == "/api/example":
        name = (query.get("name", ["common_source"])[0] or "common_source").lower()
        stem = "observed_opamp_20261111" if name == "opamp" else "common_source"
        cir_path = EXAMPLES_DIR / f"{stem}.cir"
        cfg_path = EXAMPLES_DIR / f"{stem}.json"
        handler.send_json({
            "netlist": cir_path.read_text(encoding="utf-8"),
            "settings": json.loads(cfg_path.read_text(encoding="utf-8")),
        })
        return True

    if path.startswith("/api/jobs/"):
        parts = path.split("/")
        if len(parts) < 4:
            handler.send_json({"error": "Invalid job path"}, status=404)
            return True
        jid = parts[3]
        with LOCK:
            job = JOBS.get(jid)
            if not job:
                handler.send_json({"error": "Job not found"}, status=404)
                return True
            if len(parts) == 4:
                handler.send_json(_public_job(job))
                return True
            if len(parts) == 5 and parts[4] == "download":
                if job["state"] == "running":
                    handler.send_json({"error": "Wait until execution finishes before downloading."}, status=409)
                    return True
                mem = io.BytesIO()
                with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
                    for p in job["folder"].rglob("*"):
                        if p.is_file():
                            z.write(p, p.relative_to(job["folder"]))
                    best_cir = job["folder"] / "best.cir"
                    target_net = best_cir.read_text(encoding="utf-8") if best_cir.is_file() else job.get("netlist", "")
                    if target_net:
                        try:
                            svg_res = render_schematic_svg(netlist=target_net, title=f"EDAI {jid}")
                            z.writestr("schematic.svg", svg_res["svg"])
                        except Exception:
                            pass
                _send_bytes(handler, mem.getvalue(), mime="application/zip", download=f"EDAI_SPICE_{jid}.zip")
                return True
        handler.send_json({"error": "Not found"}, status=404)
        return True

    return False


def handle_edai_post(handler: Any, path: str) -> bool:
    """Handles unified EDAI Circuit Studio POST routes. Returns True if handled."""
    edai_post_paths = {
        "/api/settings",
        "/api/extract",
        "/api/confirm",
        "/api/run",
        "/api/cancel",
        "/api/generate_base",
        "/api/validate_netlist",
        "/api/schematic_svg",
        "/api/ieee/search",
        "/api/topology/candidates",
        "/api/topology/auto_size",
    }
    if path not in edai_post_paths:
        return False

    try:
        size = int(handler.headers.get("Content-Length", "0"))
        if not 0 < size <= 15_000_000:
            handler.send_json({"error": "Request body must be between 1 byte and 15 MB."}, status=413)
            return True
        data = json.loads(handler.rfile.read(size).decode("utf-8"))

        if path == "/api/settings":
            with LOCK:
                if any(j["state"] == "running" for j in JOBS.values()) or AI_LOCK.locked():
                    raise ValueError("Cannot modify settings while a job is running.")
                engine = data.get("simulator")
                if engine not in ("ngspice", "ltspice"):
                    raise ValueError("simulator must be 'ngspice' or 'ltspice'.")
                STUDIO_CONFIG["simulator"] = engine
                STUDIO_CONFIG["simulator_path"] = str(data.get("simulator_path", "")).strip()
                STUDIO_CONFIG["model"] = str(data.get("model", "")).strip()[:200]
            handler.send_json({"ok": True})
            return True

        if path == "/api/extract":
            if not AI_LOCK.acquire(blocking=False):
                raise ValueError("Another extraction/AI request is currently running.")
            try:
                llm_client = None
                if data.get("use_ai"):
                    from ai_analog_designer.llm_client import LLMClient
                    llm_client = LLMClient(default_model=STUDIO_CONFIG.get("model") or None)
                result = extract_evidence(data, llm_client=llm_client)
            finally:
                AI_LOCK.release()
            rid = secrets.token_hex(16)
            with LOCK:
                if len(REVIEWS) >= 10:
                    REVIEWS.pop(next(iter(REVIEWS)))
                REVIEWS[rid] = result
            handler.send_json({**result, "review_id": rid})
            return True

        if path == "/api/confirm":
            with LOCK:
                review = REVIEWS.get(data.get("review_id"))
                if not review:
                    raise ValueError("Review session expired; please re-extract source files.")
                snapshot = validate_confirmation(data, review)
                cid = secrets.token_hex(16)
                if len(CONFIRMATIONS) >= 20:
                    CONFIRMATIONS.pop(next(iter(CONFIRMATIONS)))
                CONFIRMATIONS[cid] = snapshot
            handler.send_json({"confirmation_id": cid, "snapshot": snapshot})
            return True

        if path == "/api/run":
            source = data.get("netlist", "")
            settings = validate_project(source, data.get("settings", {}))
            resolve_simulator(STUDIO_CONFIG)
            provenance = None
            if data.get("confirmation_id"):
                provenance = CONFIRMATIONS.get(data["confirmation_id"])
                if not provenance:
                    raise ValueError("Document confirmation expired; please confirm sources again.")
            with LOCK:
                if any(j["state"] == "running" for j in JOBS.values()):
                    handler.send_json({"error": "A sweep job is already running."}, status=409)
                    return True
                jid = time.strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(3)
                folder = RUNS_DIR / jid
                folder.mkdir(parents=True, exist_ok=True)
                if provenance:
                    (folder / "document_review.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
                job = {
                    "id": jid,
                    "state": "running",
                    "runs": [],
                    "settings": settings,
                    "netlist": source,
                    "best_iteration": None,
                    "cancel": threading.Event(),
                    "folder": folder,
                    "error": None,
                    "feasible_count": 0,
                }
                JOBS[jid] = job
            threading.Thread(target=_sweep_worker, args=(job, source, settings, dict(STUDIO_CONFIG)), daemon=True).start()
            handler.send_json({"id": jid}, status=202)
            return True

        if path == "/api/cancel":
            with LOCK:
                job = JOBS.get(data.get("id"))
                if not job:
                    handler.send_json({"error": "Job not found"}, status=404)
                    return True
                job["cancel"].set()
            handler.send_json({"ok": True})
            return True

        if path == "/api/generate_base":
            if not AI_LOCK.acquire(blocking=False):
                handler.send_json({"error": "AI request already in progress."}, status=409)
                return True
            try:
                from ai_analog_designer.llm_client import LLMClient
                cid = data.get("confirmation_id")
                snapshot = CONFIRMATIONS.get(cid) if cid else None
                files = data.get("files", [])
                if files and not snapshot:
                    raise ValueError("Please extract and confirm source evidence before generating.")
                instruction = str(data.get("instruction", ""))
                if snapshot:
                    _, present = prepare_sources(files)
                    if present != snapshot["sources"]:
                        raise ValueError("Uploaded files changed since confirmation; please re-confirm.")
                    instruction += "\nUSER CONFIRMED EVIDENCE AND GOALS:\n" + json.dumps(snapshot, ensure_ascii=False)
                client = LLMClient(default_model=STUDIO_CONFIG.get("model") or None)
                res = generate_base_circuit(
                    instruction=instruction,
                    files=files,
                    previous=data.get("previous"),
                    simulator=STUDIO_CONFIG.get("simulator", "ltspice"),
                    ieee_context=str(data.get("ieee_context", "")),
                    llm_client=client,
                )
                res["confirmation_id"] = cid
                handler.send_json(res)
            finally:
                AI_LOCK.release()
            return True

        if path == "/api/validate_netlist":
            res = validate_any_netlist(data.get("netlist", ""), subckt_name=data.get("subckt_name"))
            handler.send_json(res)
            return True

        if path == "/api/schematic_svg":
            res = render_schematic_svg(
                structure_table=data.get("structure_table") or None,
                netlist=data.get("netlist") or None,
                sizes=data.get("sizes") or None,
                title=str(data.get("title") or "Circuit Schematic"),
            )
            handler.send_json(res)
            return True

        if path == "/api/ieee/search":
            client = IEEEMCPClient()
            res = client.search_papers(
                query=str(data.get("query", "")),
                max_results=int(data.get("max_results", 4)),
                publication_title=str(data.get("publication_title", "")),
            )
            handler.send_json(res)
            return True

        if path == "/api/topology/candidates":
            res = generate_topology_candidates(
                specifications=data.get("specifications") or [],
                prompt_hint=str(data.get("prompt_hint", "")),
                max_candidates=int(data.get("max_candidates", 6)),
                auto_size_preview=bool(data.get("auto_size_preview", False)),
                subckt_name=str(data.get("subckt_name") or "OPAMP"),
            )
            handler.send_json(res)
            return True

        if path == "/api/topology/auto_size":
            tbl_str = str(data.get("structure_table", ""))
            tbl = parse_table_text(tbl_str)
            sized = auto_size(
                tbl,
                unit_current=float(data.get("unit_current_ua", 20.0)) * 1e-6,
                output_scale=float(data.get("output_scale", 1.0)),
                simulator=str(data.get("simulator") or "auto"),
                subckt_name=str(data.get("subckt_name") or "OPAMP"),
            )
            subckt = sized.get("subckt_ltspice") or sized.get("subckt_ngspice") or ""
            if subckt:
                sized["validator"] = validate_any_netlist(subckt, subckt_name=str(data.get("subckt_name") or "OPAMP"))
            svg_res = render_schematic_svg(structure_table=tbl_str, sizes=sized.get("sizes"), title="gm/ID Sized OP-Amp")
            sized["schematic_svg"] = svg_res.get("svg")
            sized["schematic_renderer"] = svg_res.get("renderer")
            handler.send_json(sized)
            return True

    except (ValueError, KeyError, TypeError) as exc:
        handler.send_json({"error": str(exc)}, status=400)
        return True
    except Exception as exc:
        handler.send_json({"error": str(exc)}, status=500)
        return True

    return False
