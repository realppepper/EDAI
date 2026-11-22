"""
IEEE MCP Client Adapter.
Bridges AnalogVerifier's HermesAgent and Web Studio with an external IEEE MCP server
(e.g. `ai_analog_designer.mcp_server` or dahun's `ref_01_ieee_server.py`) via stdio,
with graceful fallback to `WebCircuitReferenceSearcher.search_ieee_academic` or OpenAlex.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import sys
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger("IEEEMCPClient")

IEEE_OPENALEX_HOST_ORG = "https://openalex.org/P4310319808"


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
                res = searcher.search_ieee_academic(clean_q, max_results=max_results)
                if res.get("papers"):
                    return res
            except Exception as exc:
                logger.warning(f"Direct IEEE_API_KEY search failed: {exc}")

        # Keyless OpenAlex IEEE-only fallback for Web Studio interactive browsing
        return self._search_openalex_ieee(clean_q, max_results=max_results)

    def read_paper(self, article_number: str, needed_reason: str) -> dict[str, Any]:
        """Reads official IEEE article body via configured MCP server if available."""
        if not self.is_mcp_configured():
            return {"ok": False, "full_text_retrieved": False, "error": "IEEE_MCP_COMMAND is not configured."}
        try:
            return asyncio.run(
                self._call_mcp_tool_async(
                    "read_ieee_paper",
                    {"article_number": article_number, "needed_reason": needed_reason},
                )
            )
        except Exception as exc:
            return {"ok": False, "full_text_retrieved": False, "error": str(exc)}

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
