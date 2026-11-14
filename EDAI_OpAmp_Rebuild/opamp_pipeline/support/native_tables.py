"""Original-PDF table geometry reader shared by staged and comparison workflows."""
import hashlib
import re
from pathlib import Path
import pymupdf

def _words_inside(words: list, bbox: list | tuple | None) -> list:
    if bbox is None:
        return []
    x0, y0, x1, y1 = bbox
    return sorted([w for w in words if x0 <= (w[0]+w[2])/2 <= x1 and y0 <= (w[1]+w[3])/2 <= y1],
                  key=lambda w: (round(w[1], 1), w[0]))


def _text(words: list) -> str:
    return " ".join(w[4] for w in words).strip()


def parse_numeric_cell(raw: str) -> dict:
    """Parse a single scalar only. Never discard formula/composite content."""
    value = raw.strip().replace("−", "-").replace("–", "-")
    if not value:
        return {"raw": raw, "value": None, "status": "blank", "notation": None}
    notation = "plus_minus" if value.startswith("±") else "signed_scalar"
    token = value.removeprefix("±").strip()
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", token):
        return {"raw": raw, "value": None, "status": "needs_interpretation", "notation": None}
    return {"raw": raw, "value": float(token), "status": "numeric", "notation": notation}


class NativeTableExtractor:
    """Reconstruct limit columns from original PDF header coordinates.

    Table detection supplies row bounds, while native word centres and header
    rectangles determine MIN/TYP/MAX. This avoids trusting merged data-cell
    indices. Conditions and units remain evidence text, not interpreted policy.
    """
    def __init__(self, source_pdf: str, target_product: str):
        self.source_pdf = Path(source_pdf)
        self.target_product = target_product.upper()

    def extract(self, packet: dict) -> dict:
        if hashlib.sha256(self.source_pdf.read_bytes()).hexdigest() != packet["source_sha256"]:
            raise ValueError("Original PDF hash mismatch")
        records, excluded, issues = [], [], []
        with pymupdf.open(self.source_pdf) as document:
            for item in packet["pages"]:
                number = item["pdf_page"]
                page = document[number-1]
                words = page.get_text("words")
                tables = page.find_tables().tables
                if not tables:
                    issues.append({"pdf_page": number, "reason": "No native grid table found; use visual/LLM review"})
                for table_index, table in enumerate(tables):
                    header_index, header_boxes = None, {}
                    for index, row in enumerate(table.rows):
                        found = {}
                        duplicate_labels = False
                        for cell in row.cells:
                            label = _text(_words_inside(words, cell)).upper()
                            if label in ("MIN", "TYP", "MAX", "UNIT"):
                                if label.lower() in found:
                                    duplicate_labels = True
                                found[label.lower()] = cell
                        if not duplicate_labels and {"min", "typ", "max"}.issubset(found):
                            header_index, header_boxes = index, found
                            break
                    if header_index is None:
                        issues.append({"pdf_page": number, "table_index": table_index, "reason": "Unique MIN/TYP/MAX header row not found"})
                        continue
                    first_limit = min(b[0] for k,b in header_boxes.items() if k != "unit")
                    active_cells = {}
                    row_starts = [min((c[1] for c in r.cells if c), default=None) for r in table.rows]
                    for index in range(header_index+1, len(table.rows)):
                        cells = table.rows[index].cells
                        y0 = row_starts[index]
                        if y0 is None:
                            continue
                        subsequent = [y for y in row_starts[index+1:] if y is not None and y > y0+0.1]
                        y1 = min(subsequent) if subsequent else table.bbox[3]
                        centre_y = (y0+y1)/2
                        for column, cell in enumerate(cells):
                            if cell is not None:
                                active_cells[column] = cell
                            elif column in active_cells and not (active_cells[column][1] <= centre_y <= active_cells[column][3]):
                                del active_cells[column]
                        limit_cells = {}
                        for slot in ("min", "typ", "max"):
                            hb = header_boxes[slot]
                            bbox = [hb[0], y0, hb[2], y1]
                            selected = _words_inside(words, bbox)
                            limit_cells[slot] = {**parse_numeric_cell(_text(selected)), "bbox_points": bbox,
                                "header_bbox_points": list(hb), "native_words": [{"text": w[4], "bbox": list(w[:4])} for w in selected]}
                        if not any(c["raw"] for c in limit_cells.values()):
                            continue
                        left_cells = []
                        seen = set()
                        for column, cell in sorted(active_cells.items()):
                            box = tuple(cell)
                            if cell[2] <= first_limit+0.5 and box not in seen:
                                seen.add(box)
                                text = _text(_words_inside(words, cell))
                                if text:
                                    left_cells.append({"column": column, "text": text, "bbox_points": list(cell)})
                        label = " | ".join(c["text"] for c in left_cells)
                        products = set(re.findall(r"\b[A-Z]{2,}\d+[A-Z0-9-]*\b", label.upper()))
                        # Explicit model labels in inherited cells have physical
                        # row-span bounds; don't carry a model label past them.
                        ambiguous_family = any("X" in p for p in products)
                        if products and self.target_product not in products and not ambiguous_family:
                            excluded.append({"pdf_page": number, "table_index": table_index, "row_index": index,
                                             "raw_label": label, "reason": "Explicit other-product row label"})
                            continue
                        unit_text = ""
                        unit_box = None
                        if "unit" in header_boxes:
                            unit_column = next((j for j,c in enumerate(table.rows[header_index].cells) if c == header_boxes["unit"]), None)
                            unit_box = active_cells.get(unit_column)
                            if unit_box:
                                unit_text = _text(_words_inside(words, unit_box))
                        review = [f"{k}: non-scalar expression preserved" for k,c in limit_cells.items() if c["status"] == "needs_interpretation"]
                        if products and self.target_product not in products and ambiguous_family:
                            review.append("Family model notation needs product-scope interpretation")
                        if not unit_text: review.append("Unit cell not resolved")
                        if not label: review.append("Parameter/condition cells not resolved")
                        if "specs_product_scope_review" in item["roles"]: review.append("Document/product scope requires review")
                        record = {"id": f"NATIVE-P{number}-T{table_index}-R{index}",
                            "raw_parameter_and_conditions": left_cells,
                            "limits": {k:c["value"] for k,c in limit_cells.items()}, "limit_cells": limit_cells,
                            "raw_unit": unit_text, "requires_review": bool(review), "review_reasons": review,
                            "unit_cell_evidence": {"bbox_points": list(unit_box) if unit_box else None, "raw": unit_text},
                            "numeric_placement_status": "header_coordinate_assignment_only",
                            "conditions_semantics_verified": False,
                            "source": {"pdf_page": number, "table_index": table_index, "row_index": index,
                                       "row_bbox_points": [table.bbox[0],y0,table.bbox[2],y1], "evidence": label}}
                        records.append(record)
        return {"stage": "spec_01_native_table_evidence", "target_product": self.target_product,
                "source_sha256": packet["source_sha256"], "authorship": "deterministic_original_pdf_geometry",
                "external_llm_calls": 0, "rows": records, "excluded_rows": excluded, "table_issues": issues,
                "source_accuracy_verified": False,
                "scope": "Raw cell evidence, not finalized spec identity, inherited conditions, unit policy or acceptance criteria"}
