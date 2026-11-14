"""Step 2: make an auditable candidate-page map, without extracting spec values."""
import re


def _role(title: str, target: str) -> str:
    lower = title.lower()
    if "table of contents" in lower:
        return "document_index"
    if re.match(r"^[123]\s+(features|applications|description)$", lower):
        return "product_overview"
    mentions = bool(re.search(r"(?<![A-Z0-9-])" + re.escape(target.upper()) + r"(?![A-Z0-9-])", title.upper()))
    parts = re.findall(r"\b[A-Z]{2,}\d+[A-Z0-9/-]*\b", title.upper())
    ambiguous = not parts or any("X" in p or "/" in p for p in parts)
    if "electrical characteristics" in lower:
        return "target_specs" if mentions else "specs_product_scope_review" if ambiguous else "other_product_specs"
    if "typical characteristics" in lower:
        return "target_typical_reference" if mentions else "typical_product_scope_review" if ambiguous else "other_product_typical_reference"
    if "pin configuration" in lower or "pin functions" in lower or "connection diagram" in lower:
        return "pin_interface"
    if any(t in lower for t in ["absolute maximum", "recommended operating", "esd ratings", "thermal information"]):
        return "operating_and_safety_conditions"
    if "parameter measurement" in lower:
        return "measurement_definitions"
    if any(t in lower for t in ["detailed description", "functional block", "feature description", "device functional", "overview"]):
        return "behavior_and_structure_reference"
    if any(t in lower for t in ["application", "power supply recommendations", "layout"]):
        return "application_reference"
    if any(t in lower for t in ["mechanical", "packaging", "package option", "orderable"]):
        return "package_reference"
    if "revision history" in lower or "documentation support" in lower:
        return "document_administration"
    if lower.endswith("features") or lower.endswith("description"):
        return "product_overview"
    return "unclassified"


def plan_pages(inventory: dict, target: str) -> dict:
    total = inventory["page_count"]
    # Use bookmark hierarchy to retain continuation pages through the next
    # section of the same/higher level. Unknown layouts remain review candidates.
    bookmarks = [b for b in inventory["bookmarks"] if 1 <= b["pdf_page"] <= total]
    ranges = []
    for index, entry in enumerate(bookmarks):
        stop = total
        for following in bookmarks[index + 1:]:
            if following["level"] <= entry["level"]:
                stop = max(entry["pdf_page"], following["pdf_page"] - 1)
                break
        ranges.append({**entry, "end_pdf_page": stop, "role": _role(entry["title"], target),
                       "evidence_source": "pdf_bookmark"})
    planned = []
    for page in inventory["pages"]:
        number = page["pdf_page"]
        evidence = [r for r in ranges if r["pdf_page"] <= number <= r["end_pdf_page"] and r["role"] != "unclassified"]
        if not evidence:
            # Local heading fallback. It only nominates pages; absence of a
            # recognized heading is never an automatic exclusion decision.
            for line in page["text"].splitlines():
                heading = re.match(r"^\d+(?:\.\d+)*\s+[A-Za-z]", line) or re.match(
                    r"^(?:electrical characteristics|typical characteristics|absolute maximum ratings|recommended operating conditions|pin configuration|connection diagram|functional block diagram|detailed description|application information|power supply recommendations)\b", line, re.I)
                if heading and "....." not in line:
                    role = _role(line, target)
                    if role != "unclassified":
                        evidence.append({"title": line, "role": role, "evidence_source": "native_text_heading"})
        roles = sorted({e["role"] for e in evidence})
        review = bool(page["flags"]) or not roles or bool(set(roles) & {"specs_product_scope_review", "typical_product_scope_review"})
        # Other-product pages are retained in the inventory and may be revisited;
        # they are not silently thrown away or accepted as target requirements.
        primary = {"target_specs", "specs_product_scope_review", "pin_interface", "operating_and_safety_conditions", "measurement_definitions"}
        references = {"target_typical_reference", "typical_product_scope_review", "behavior_and_structure_reference", "application_reference", "product_overview"}
        category = "primary_candidate" if primary.intersection(roles) else "reference_candidate" if references.intersection(roles) else "review_required" if review else "retained_other_section"
        planned.append({"pdf_page": number, "roles": roles, "category": category,
                        "requires_review": review,
                        "image_reading_recommended_for_details": review or bool(set(roles) & {
                            "target_specs", "specs_product_scope_review", "target_typical_reference", "pin_interface",
                            "measurement_definitions", "behavior_and_structure_reference"}),
                        "flags": page["flags"], "evidence": evidence})
    return {"target_product": target, "source_sha256": inventory["sha256"], "page_count": total,
            "mapped_pages": len(planned), "stage": "candidate planning only; not verified requirement extraction",
            "selection_is_final": False, "bookmark_ranges": ranges, "pages": planned,
            "limitations": ["Bookmarks/headings can be incomplete or incorrect; this is a reviewable candidate map.",
                            "Scanned/unreadable/unclassified pages require visual or OCR review.",
                            "Graphs and application examples are references, not automatically acceptance criteria.",
                            "Table values, MIN/TYP/MAX columns and source conditions are not extracted here."]}
