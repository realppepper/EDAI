"""
IEEE MCP Client Adapter.
Bridges AnalogVerifier's HermesAgent and Web Studio with an external IEEE MCP server
(e.g. `ai_analog_designer.mcp_server` or dahun's `ref_01_ieee_server.py`) via stdio,
with graceful fallback to `WebCircuitReferenceSearcher.search_ieee_academic` or OpenAlex.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shlex
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

logger = logging.getLogger("IEEEMCPClient")

IEEE_OPENALEX_HOST_ORG = "https://openalex.org/P4310319808"
MAX_FULLTEXT_BYTES = 8_000_000


def parse_ieee_jats_body(xml_text: str, article_number: str) -> dict[str, Any]:
    """Parses official IEEE JATS XML full-text response into structured sections & paragraphs."""
    if "<!DOCTYPE" in xml_text.upper() or "<!ENTITY" in xml_text.upper():
        raise ValueError("External XML entities are not supported")
    root = ET.fromstring(xml_text)  # nosec B314 - DOCTYPE/ENTITY explicitly rejected above

    def _tag(e: ET.Element) -> str:
        return e.tag.rsplit("}", 1)[-1].lower()

    if _tag(root) not in {"response", "article"}:
        raise ValueError("Not an IEEE/JATS article response")
    body = next((e for e in root.iter() if _tag(e) == "body"), None)
    if body is None:
        raise ValueError("No article body; metadata/login/error is not full text")
    if not any(_tag(e) == "sec" for e in body.iter()):
        raise ValueError("Article sections missing")

    blocks: list[dict[str, Any]] = []

    def _text(e: ET.Element) -> str:
        return " ".join(" ".join(e.itertext()).split())

    def _walk(e: ET.Element, section: str = "Article body", section_id: str = "body") -> None:
        for child in e:
            kind = _tag(child)
            if kind in {"abstract", "ref-list", "references"}:
                continue
            if kind == "sec":
                title = next((_text(c) for c in child if _tag(c) == "title"), section)
                _walk(child, title, child.get("id", section_id))
            elif kind in {"p", "disp-formula", "table-wrap", "fig"}:
                val = _text(child)
                if val:
                    blocks.append({
                        "id": f"{section_id}-b{len(blocks) + 1}",
                        "section": section,
                        "section_id": section_id,
                        "kind": kind,
                        "text": val,
                    })
            elif kind not in {"title", "label"}:
                _walk(child, section, section_id)

    _walk(body)
    paragraphs = [b for b in blocks if b["kind"] == "p"]
    if len(paragraphs) < 2 or sum(len(b["text"]) for b in paragraphs) < 500:
        raise ValueError("Insufficient article body; not accepted as full-text evidence")
    return {
        "ok": True,
        "article_number": str(article_number),
        "full_text_retrieved": True,
        "evidence_scope": "article_body_text",
        "source_url": f"https://ieeexplore.ieee.org/document/{article_number}",
        "source_xml_sha256": hashlib.sha256(xml_text.encode("utf-8")).hexdigest(),
        "blocks": blocks,
        "body_characters": sum(len(b["text"]) for b in blocks),
    }


def fetch_ieee_article_body(article_number: str, api_key: str | None = None) -> dict[str, Any]:
    """Fetches official IEEE full-text JATS XML for an article_number."""
    number = str(article_number or "").strip()
    if not re.fullmatch(r"[0-9]{1,12}", number):
        return {"ok": False, "article_number": number, "full_text_retrieved": False, "error": "Invalid article number"}
    key = (api_key or os.environ.get("IEEE_API_KEY") or "").strip()
    if not key:
        return {"ok": False, "article_number": number, "full_text_retrieved": False, "error": "Missing IEEE_API_KEY"}
    url = (
        f"https://ieeexploreapi.ieee.org/api/v1/search/document/{number}/fulltext?"
        + urllib.parse.urlencode({"apikey": key, "format": "xml"})
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "EDAI-AnalogVerifier/2.0", "Accept": "application/xml"},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            data = response.read(MAX_FULLTEXT_BYTES + 1)
        if len(data) > MAX_FULLTEXT_BYTES:
            raise ValueError("Full-text response exceeds size limit")
        xml_text = data.decode("utf-8-sig").replace(key, "[redacted]")
        return parse_ieee_jats_body(xml_text, number)
    except urllib.error.HTTPError as err:
        return {
            "ok": False,
            "article_number": number,
            "full_text_retrieved": False,
            "error": f"IEEE full-text HTTP {err.code}",
            "access_denied": err.code in {401, 403},
        }
    except Exception as err:
        return {
            "ok": False,
            "article_number": number,
            "full_text_retrieved": False,
            "error": f"IEEE full-text unavailable ({type(err).__name__}: {err})",
        }


def extract_body_excerpts(
    blocks: list[dict[str, Any]],
    keywords: list[str],
    budget: int = 4000,
) -> list[dict[str, Any]]:
    """Scores and extracts source-exact full-text body paragraphs/equations matching keywords."""
    clean_kw = [k.lower().strip() for k in keywords if k and len(k.strip()) >= 2]
    if not clean_kw:
        clean_kw = ["amplifier", "gain", "bias", "offset", "current", "compensation"]
    scored = []
    for idx, b in enumerate(blocks):
        sec_low = str(b.get("section", "")).lower()
        txt_low = str(b.get("text", "")).lower()
        score = sum(
            3 * len(re.findall(re.escape(w), sec_low)) + len(re.findall(re.escape(w), txt_low))
            for w in clean_kw
        )
        if score and b.get("kind") in {"p", "disp-formula", "table-wrap", "fig"}:
            scored.append((-score, idx, b))
    if not scored:
        # Fallback to first substantive body paragraphs
        scored = [(0, idx, b) for idx, b in enumerate(blocks) if b.get("kind") == "p"][:4]
    result: list[dict[str, Any]] = []
    remaining = budget
    for _, _, b in sorted(scored)[:6]:
        if remaining < 100:
            break
        txt = str(b.get("text", ""))
        positions = [txt.lower().find(w) for w in clean_kw if w in txt.lower()]
        start = max(0, min(positions) - 200) if positions else 0
        end = min(len(txt), start + min(1200, remaining))
        result.append({
            "excerpt_id": f"{b.get('id')}:{start}-{end}",
            "block_id": b.get("id"),
            "section": b.get("section"),
            "kind": b.get("kind"),
            "text": txt[start:end],
        })
        remaining -= (end - start)
    return result


class IEEEMCPClient:
    """Queries IEEE literature via an external MCP stdio server or direct academic fallback."""

    def __init__(
        self,
        mcp_command: str | None = None,
        mcp_args: list[str] | None = None,
    ):
        if mcp_command is not None:
            self.mcp_command = mcp_command.strip()
            self.mcp_args = list(mcp_args or [])
        else:
            env_cmd = (os.environ.get("IEEE_MCP_COMMAND") or "").strip()
            if env_cmd:
                self.mcp_command = env_cmd
                raw_args = os.environ.get("IEEE_MCP_ARGS", "").strip()
                self.mcp_args = list(mcp_args) if mcp_args is not None else (shlex.split(raw_args) if raw_args else [])
            elif os.environ.get("IEEE_MCP_ENABLED", "1") == "1" and os.environ.get("IEEE_MCP_SERVER_INTERNAL") != "1":
                # Auto-wire built-in EDAI FastMCP stdio server so IEEE MCP works out of the box
                self.mcp_command = sys.executable
                self.mcp_args = ["-m", "ai_analog_designer.mcp_server"]
            else:
                self.mcp_command = ""
                self.mcp_args = []

    def is_mcp_configured(self) -> bool:
        return bool(self.mcp_command)

    async def _call_mcp_tool_async(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        child_env = dict(os.environ)
        child_env["IEEE_MCP_SERVER_INTERNAL"] = "1"
        server_params = StdioServerParameters(
            command=self.mcp_command,
            args=self.mcp_args,
            env=child_env,
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=arguments)
                for block in result.content:
                    text = getattr(block, "text", None)
                    if text:
                        try:
                            return json.loads(text)
                        except json.JSONDecodeError:
                            return {"ok": True, "raw": text}
        return {"ok": False, "papers": [], "error": "Empty response from IEEE MCP server"}

    def search_papers(
        self,
        query: str,
        max_results: int = 3,
        publication_title: str = "",
    ) -> dict[str, Any]:
        """Searches IEEE papers via configured MCP server, else direct IEEE/OpenAlex searcher."""
        clean_q = query.strip()
        if not clean_q:
            return {"ok": False, "papers": [], "error": "Empty query"}

        if self.is_mcp_configured():
            try:
                args = {"query": clean_q, "max_results": max_results}
                if publication_title:
                    args["publication_title"] = publication_title
                res = asyncio.run(self._call_mcp_tool_async("search_ieee_papers", args))
                if isinstance(res, dict) and res.get("papers") is not None:
                    res.setdefault("provider", "ieee_mcp")
                    return res
            except Exception as exc:
                logger.warning(f"IEEE MCP stdio call failed ({exc}); falling back to direct academic search.")

        # Try WebCircuitReferenceSearcher when IEEE_API_KEY is available
        if os.environ.get("IEEE_API_KEY", "").strip():
            try:
                from ai_analog_designer.hermes_core.web_reference_search import WebCircuitReferenceSearcher
                searcher = WebCircuitReferenceSearcher()
                res = searcher.search_ieee_academic(
                    clean_q,
                    max_results=max_results,
                    publication_title=publication_title,
                )
                if res.get("papers"):
                    return res
            except Exception as exc:
                logger.warning(f"Direct IEEE_API_KEY search failed: {exc}")

        # Keyless OpenAlex IEEE-only fallback for Web Studio interactive browsing
        return self._search_openalex_ieee(clean_q, max_results=max_results)

    def read_paper(self, article_number: str, needed_reason: str) -> dict[str, Any]:
        """Reads official IEEE article full-text JATS XML body via configured MCP server or direct IEEE API."""
        if self.is_mcp_configured():
            try:
                res = asyncio.run(
                    self._call_mcp_tool_async(
                        "read_ieee_paper",
                        {"article_number": str(article_number), "needed_reason": needed_reason},
                    )
                )
                if isinstance(res, dict) and "full_text_retrieved" in res:
                    return res
            except Exception as exc:
                logger.warning(f"IEEE MCP read_ieee_paper stdio call failed ({exc}); falling back to direct full-text API.")
        return fetch_ieee_article_body(str(article_number))

    def _search_openalex_ieee(self, query: str, max_results: int = 3) -> dict[str, Any]:
        encoded_q = urllib.parse.quote(query)
        url = (
            f"https://api.openalex.org/works?search={encoded_q}"
            f"&filter=primary_location.source.host_organization:{IEEE_OPENALEX_HOST_ORG}"
            f"&per-page={max_results}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "AnalogVerifier-EDAI/1.0"})
        papers: list[dict[str, Any]] = []
        try:
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for w in (data.get("results") or [])[:max_results]:
                inv = w.get("abstract_inverted_index") or {}
                abstract = ""
                if inv:
                    words = sorted((pos, word) for word, positions in inv.items() for pos in positions)
                    abstract = " ".join(word for _, word in words)[:1200]
                papers.append({
                    "title": w.get("title") or "Untitled IEEE Paper",
                    "venue": ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or "IEEE",
                    "year": str(w.get("publication_year") or ""),
                    "doi": w.get("doi") or "",
                    "url": w.get("doi") or w.get("id") or "",
                    "abstract": abstract,
                })
            return {"ok": bool(papers), "provider": "openalex_ieee", "papers": papers}
        except Exception as exc:
            return {"ok": False, "provider": "openalex_ieee", "papers": [], "error": str(exc)}
