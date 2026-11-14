"""Step 3: render reviewed page categories, retaining PDF/image provenance."""
import hashlib
import json
from pathlib import Path
import pymupdf


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def render_pages(inventory_path: str, plan_path: str, output_dir: str, dpi: int = 150) -> dict:
    if not 72 <= dpi <= 200:
        raise ValueError("Use 72–200 DPI for the page-image parsing stage")
    inventory = json.loads(Path(inventory_path).read_text(encoding="utf-8"))
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    source = Path(inventory["source_pdf"])
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if source_hash != inventory["sha256"] or source_hash != plan["source_sha256"]:
        raise ValueError("PDF/inventory/plan hashes differ. Re-run steps 1–2.")
    out = Path(output_dir).resolve()
    selected = [p for p in plan["pages"] if p["category"] in ("primary_candidate", "reference_candidate")]
    numbers = [p["pdf_page"] for p in selected]
    if not numbers or len(numbers) != len(set(numbers)):
        raise ValueError("Expected a nonempty, unique candidate page list")
    result = {"stage": "pdf_03_render_pages", "completed": False, "source_pdf": str(source),
              "source_sha256": source_hash, "target_product": plan["target_product"], "dpi": dpi,
              "requested_pages": numbers, "images": [],
              "pending_review_pages": [p["pdf_page"] for p in plan["pages"] if p["category"] == "review_required"],
              "retained_other_pages": [p["pdf_page"] for p in plan["pages"] if p["category"] == "retained_other_section"],
              "scope": "Candidate pages, not a certified complete list of target requirements"}
    manifest_path = out / "03_render_manifest.json"
    with pymupdf.open(source) as document:
        for candidate in selected:
            number = candidate["pdf_page"]
            if not 1 <= number <= len(document):
                raise ValueError(f"Invalid PDF page: {number}")
            page = document[number - 1]
            image_path = out / "images" / f"page_{number:04d}_{source_hash[:12]}_{dpi}dpi.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            if image_path.exists():
                pixmap = pymupdf.Pixmap(str(image_path))
                reused = True
            else:
                pixmap = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
                pixmap.save(image_path)
                reused = False
            image_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
            result["images"].append({"pdf_page": number, "roles": candidate["roles"],
                "category": candidate["category"], "image_path": str(image_path), "image_sha256": image_hash,
                "width_pixels": pixmap.width, "height_pixels": pixmap.height, "dpi": dpi,
                "page_rect_points": list(page.rect), "cropbox_points": list(page.cropbox),
                "page_rotation_degrees": page.rotation, "page_rotation_matrix": list(page.rotation_matrix),
                "reused_image": reused})
            save_json(manifest_path, result)
            print(f"[render] PDF page {number}: {'reused' if reused else 'saved'}", flush=True)
    result["completed"] = True
    save_json(manifest_path, result)
    return result
