"""Native cell-evidence extraction plus a separate manual/API spec boundary.

An API extractor can implement the same extract(packet) protocol later. This
module checks format/provenance only; it does not prove source accuracy.
"""
import json
import hashlib
import re
from pathlib import Path
from typing import Protocol
import pymupdf
from ..pdf_03_render_pages import save_json


class Extractor(Protocol):
    def extract(self, packet: dict) -> dict: ...


class ManualJSONExtractor:
    def __init__(self, path: str):
        self.path = Path(path)

    def extract(self, packet: dict) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))


from ..support.native_tables import NativeTableExtractor, parse_numeric_cell


def extract_native_tables(run_dir: str, pages: list[int] | None = None) -> dict:
    root = Path(run_dir)
    inventory = json.loads((root / "01_pdf_inventory.json").read_text(encoding="utf-8"))
    plan = json.loads((root / "02_page_plan.json").read_text(encoding="utf-8"))
    if plan["source_sha256"] != inventory["sha256"]:
        raise ValueError("Page plan and inventory refer to different PDFs")
    if pages is None:
        pages = [p["pdf_page"] for p in plan["pages"] if set(p["roles"]) & {"target_specs", "specs_product_scope_review"}]
    if not pages or set(pages) - {p["pdf_page"] for p in plan["pages"]}:
        raise ValueError("No usable electrical-table candidates, or requested pages absent from page plan")
    packet = {"source_sha256": inventory["sha256"], "pages": [
        {"pdf_page": p["pdf_page"], "roles": p["roles"]} for p in plan["pages"] if p["pdf_page"] in pages]}
    result = NativeTableExtractor(inventory["source_pdf"], plan["target_product"]).extract(packet)
    save_json(root / "06_code_table_evidence.json", result)
    lines = ["# 원본 표 셀의 코드 추출 결과", "", "원본 PDF 머리글 좌표로 값을 배치했습니다. 사양 의미·조건·완전성은 아직 검증하지 않았습니다.", "",
             "| PDF page / row | MIN | TYP | MAX | Unit | Parameter and conditions | Review |", "|---|---|---|---|---|---|---|"]
    for row in result["rows"]:
        raw = [row["limit_cells"][k]["raw"] or "—" for k in ("min","typ","max")]
        left = " / ".join(c["text"] for c in row["raw_parameter_and_conditions"])
        lines.append("| " + " | ".join(str(v).replace("|","∣") for v in [row['id'],*raw,row['raw_unit'],left,'; '.join(row['review_reasons'])]) + " |")
    (root / "06_code_table_evidence.md").write_text("\n".join(lines), encoding="utf-8")
    return result


def build_packet(run_dir: str, pages: list[int]) -> dict:
    root = Path(run_dir)
    checks = json.loads((root / "05_layout_checks.json").read_text(encoding="utf-8"))
    blocked = set(checks["blocked_pages"]) & set(pages)
    if blocked:
        raise ValueError(f"Source pages blocked: {sorted(blocked)}")
    packet = {"source_sha256": checks["source_sha256"], "pages": []}
    for number in pages:
        page = json.loads((root / "pages" / f"page_{number:04d}.json").read_text(encoding="utf-8"))
        packet["pages"].append({"pdf_page": number, "roles": page["roles"], "text": page["document_text"],
                                "layout_warnings": next(r["warnings"] for r in checks["pages"] if r["pdf_page"] == number)})
    return packet  # no full-document native text/word coordinates


def extract_rows(run_dir: str, extractor: Extractor, pages: list[int]) -> dict:
    root = Path(run_dir)
    packet = build_packet(run_dir, pages)
    save_json(root / "06_extraction_packet.json", packet)
    document = extractor.extract(packet)
    if document.get("source_sha256") != packet["source_sha256"]:
        raise ValueError("Extracted document source hash mismatch")
    specs = document.get("electrical_specs")
    if not isinstance(specs, list) or not specs:
        raise ValueError("Expected a nonempty electrical_specs list")
    ids = set()
    for row in specs:
        if not row.get("id") or row["id"] in ids: raise ValueError("Missing/duplicate spec ID")
        ids.add(row["id"])
        if row.get("source", {}).get("pdf_page") not in pages: raise ValueError("Spec references an unsupplied page")
        if not row.get("symbol") or not row.get("source", {}).get("evidence"): raise ValueError("Missing spec identity/evidence")
        if not isinstance(row.get("limits"), dict): raise ValueError("Missing limit object")
        if set(row["limits"]) != {"min", "typ", "max"}: raise ValueError("Expected MIN/TYP/MAX slots")
    document["format_checks"] = {"passed": True, "spec_rows": len(specs), "source_accuracy_verified": False}
    save_json(root / "06_spec_candidates.json", document)
    return document
