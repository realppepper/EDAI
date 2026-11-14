"""Step 1: inspect EVERY PDF page locally; no rendering or AI calls."""
import hashlib
from pathlib import Path
import pymupdf


def inspect_pdf(pdf_path: str) -> dict:
    source = Path(pdf_path).resolve()
    pages = []
    with pymupdf.open(source) as document:
        if document.needs_pass:
            raise ValueError("Password-protected PDF: unlock before inspection")
        bookmarks = [{"level": level, "title": title, "pdf_page": page}
                     for level, title, page, *_ in document.get_toc()]
        for index in range(len(document)):
            page = document[index]
            flags = []
            error = None
            words = []
            try:
                text = page.get_text()
            except Exception as exc:
                text = ""
                error = type(exc).__name__
                flags.append("text_read_error")
            try:
                words = [{"text": w[4], "bbox": list(w[:4]),
                          "block": w[5], "line": w[6], "word": w[7]}
                         for w in page.get_text("words")]
            except Exception:
                flags.append("word_coordinates_unavailable")
            nonspace = "".join(text.split())
            if len(nonspace) < 80:
                flags.append("little_or_no_native_text")
            if nonspace and nonspace.count("\ufffd") / len(nonspace) > 0.01:
                flags.append("text_encoding_problem")
            pages.append({"pdf_page": index + 1, "text": text,
                          "words": words,
                          "word_coordinate_space": "PyMuPDF unrotated page coordinates, points",
                          "page_rotation_degrees": page.rotation, "cropbox": list(page.cropbox),
                          "text_characters": len(text), "width": page.rect.width,
                          "height": page.rect.height, "flags": flags, "error": error})
    return {"source_pdf": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "page_count": len(pages), "inspected_pages": len(pages),
            "all_pages_inventoried": True,
            "all_pages_text_read_successfully": all(p["error"] is None for p in pages),
            "method": "PyMuPDF native text and PDF bookmarks; no image rendering, no OCR/LLM",
            "bookmarks": bookmarks, "pages": pages}
