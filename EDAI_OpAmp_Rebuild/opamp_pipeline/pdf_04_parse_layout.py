"""Step 4: parse page images with Nemotron 3.5 Parse; no spec interpretation."""
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request
import urllib.error
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from .pdf_03_render_pages import save_json

MODEL = "nvidia/nemotron-3.5-parse"
ENDPOINT = "https://ai.api.nvidia.com/v1/retrieval/nvidia/nemotron-3.5-parse/parse"


def cache_key(image_hash: str, endpoint: str, max_tokens: int) -> str:
    return hashlib.sha256(json.dumps({"image": image_hash, "model": MODEL,
        "endpoint": endpoint, "max_output_tokens": max_tokens, "decoder_version": 1}, sort_keys=True).encode()).hexdigest()


def decode_layout(response: dict) -> dict:
    if response.get("finish_reason") in ("length", "max_tokens"):
        raise ValueError("Output limit reached: incomplete page response")
    raw = response.get("content")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Missing page content")
    strip = lambda s: re.sub(r"<(?:[xy]_[^>]+|class_[^>]+|/?s)>", "", s).strip()
    blocks = []
    for match in re.finditer(r"(.*?)<class_([^>]+)>", raw, re.S):
        segment, label = match.groups()
        coords = [{"axis": axis, "value": float(value)}
                  for axis, value in re.findall(r"<([xy])_([0-9.]+)>", segment)]
        blocks.append({"type": label.lower(), "text": strip(segment), "coordinates_normalized": coords})
    return {"document_text": strip(raw), "blocks": blocks,
            "coordinate_note": "Keep raw control tokens; normalized image coordinates, not native PDF word coordinates",
            "requires_finish_reason_review": response.get("finish_reason") not in ("stop", "eos", "end_turn")}


def request_page(image_bytes: bytes, api_key: str, endpoint: str, max_tokens: int) -> dict:
    boundary = "EDAIDocument" + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="page.png"\r\nContent-Type: image/png\r\n\r\n'.encode()
            + image_bytes
            + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="options"\r\nContent-Type: application/json\r\n\r\n'.encode()
            + json.dumps({"decoding": {"max_output_tokens": max_tokens}}).encode()
            + f'\r\n--{boundary}--\r\n'.encode())
    request = urllib.request.Request(endpoint, data=body, headers={"Authorization": f"Bearer {api_key}",
        "Accept": "application/json", "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_layout(manifest_path: str, output_dir: str, api_key: str, workers: int = 2,
                 max_tokens: int = 8000, endpoint: str = ENDPOINT) -> dict:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if not manifest.get("completed"):
        raise ValueError("Rendering stage has not completed")
    if not api_key:
        raise ValueError("NVIDIA_API_KEY is missing")
    out = Path(output_dir).resolve()
    started = time.monotonic()

    def one_page(image):
        number = image["pdf_page"]
        result_path = out / "pages" / f"page_{number:04d}.json"
        data = Path(image["image_path"]).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != image["image_sha256"]:
            raise ValueError(f"Image hash mismatch on page {number}")
        signature = cache_key(digest, endpoint, max_tokens)
        if result_path.exists():
            try:
                previous = json.loads(result_path.read_text(encoding="utf-8"))
                if not isinstance(previous,dict):raise ValueError('Cache must be an object')
                if (previous.get("status") == "ok" and previous.get("cache_key") == signature
                        and previous.get('image_sha256') == digest):
                    if not isinstance(previous.get('raw_response'),dict):raise ValueError('Invalid cached response')
                    decoded = decode_layout(previous['raw_response'])
                    rebound={**previous,**decoded,'pdf_page':number,'roles':image['roles'],
                        'source_sha256':manifest['source_sha256'],'image_sha256':digest,
                        'model':MODEL,'endpoint':endpoint,'max_output_tokens':max_tokens,
                        'decoder_version':1,'reused_result':True}
                    save_json(result_path,rebound)
                    return rebound
            except (ValueError,KeyError,TypeError):
                pass  # Corrupt/incompatible cache: explicitly regenerate, not abort.
        result = {"pdf_page": number, "roles": image["roles"], "source_sha256": manifest["source_sha256"],
                  "image_sha256": digest, "model": MODEL, "cache_key": signature,
                  "max_output_tokens": max_tokens, "endpoint": endpoint, "decoder_version": 1, "status": "failed",
                  "reused_result": False, "attempts": []}
        for attempt in range(1, 3):
            tick = time.monotonic()
            try:
                response = request_page(data, api_key, endpoint, max_tokens)
                result["raw_response"] = response
                decoded = decode_layout(response)
                result.update(decoded)
                result["status"] = "ok"
                result["attempts"].append({"attempt": attempt, "status": "ok", "seconds": round(time.monotonic()-tick, 2)})
                break
            except urllib.error.HTTPError as exc:
                error = f"NVIDIA HTTP {exc.code}"
                retry = exc.code == 429 or exc.code >= 500
            except ValueError as exc:
                error = str(exc)
                retry = False
            except Exception as exc:
                error = f"NVIDIA request failed ({type(exc).__name__})"
                retry = True
            result["attempts"].append({"attempt": attempt, "status": "failed", "error": error,
                                       "seconds": round(time.monotonic()-tick, 2)})
            result["error"] = error
            if not retry or attempt == 2:
                break
            time.sleep(2)
        if result["status"] == "ok":
            result.pop("error", None)
        save_json(result_path, result)
        return result

    results = {}
    def checkpoint():
        ordered = [results[k] for k in sorted(results)]
        summary = {"stage": "pdf_04_parse_layout", "model": MODEL, "source_sha256": manifest["source_sha256"],
            "requested_pages": manifest["requested_pages"], "processed_pages": sorted(results),
            "succeeded_pages": [r["pdf_page"] for r in ordered if r["status"] == "ok"],
            "failed_pages": [r["pdf_page"] for r in ordered if r["status"] != "ok"],
            "reused_pages": [r["pdf_page"] for r in ordered if r.get("reused_result")],
            "new_api_attempts": sum(len(r.get("attempts", [])) for r in ordered if not r.get("reused_result")),
            "output_tokens_this_run": sum(r.get("raw_response", {}).get("usage", {}).get("output_tokens", 0)
                                          for r in ordered if not r.get("reused_result")),
            "pending_review_pages": manifest.get("pending_review_pages", []),
            "completed": len(results) == len(manifest["requested_pages"]),
            "all_requested_pages_succeeded": len(results) == len(manifest["requested_pages"]) and all(r["status"] == "ok" for r in ordered),
            "seconds_this_run": round(time.monotonic()-started, 2),
            "scope": "Raw page parsing only; no verified spec JSON, graph digitization or netlist extraction"}
        save_json(out / "04_parse_summary.json", summary)
        return summary
    checkpoint()
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 3))) as pool:
        jobs = {pool.submit(one_page, image): image for image in manifest["images"]}
        for future in as_completed(jobs):
            image = jobs[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {"pdf_page": image["pdf_page"], "status": "failed", "error": f"Local processing failed ({type(exc).__name__})"}
                save_json(out / "pages" / f"page_{image['pdf_page']:04d}.json", result)
            results[image["pdf_page"]] = result
            checkpoint()
            print(f"[parse] PDF page {image['pdf_page']}: {result['status']}" + (" (reused)" if result.get("reused_result") else ""), flush=True)
    return checkpoint()
