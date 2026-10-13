"""The EIC smart-search service as a search backend (POST /query)."""

from __future__ import annotations

import json
import os
from typing import Optional
from urllib.request import Request, urlopen

REQUEST_TIMEOUT_SECONDS = 60   # an answer that consults Indico live can take 25 s
CLIENT_NAME = "eic-docs-mcp"    # echoed by the service and kept apart from human traffic in its analytics
SNIPPET_LIMIT = 300


def api_url() -> str:
    return os.getenv("EIC_DOCS_API", "").rstrip("/")


def post_json(url: str, body: dict) -> dict:
    headers = {"Content-Type": "application/json", "User-Agent": "eic-docs-mcp"}
    request = Request(url, data=json.dumps(body).encode(), headers=headers)
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.load(response)


def query(question: str, source: Optional[str], limit: int, generate_answer: bool) -> dict:
    """The service has no source filter, so a restricted search asks for more hits and keeps
    the ones from that source."""
    top_k = min(3 * limit, 30) if source else limit
    body = {"query": question, "top_k": max(1, top_k), "generate_answer": generate_answer, "client": CLIENT_NAME}
    result = post_json(f"{api_url()}/query", body)
    if source:
        result["citations"] = [c for c in result["citations"] if c["source_name"] == source][:limit]
    return result


def format_citations(citations: list[dict]) -> str:
    lines = []
    for number, citation in enumerate(citations, 1):
        snippet = " ".join(citation.get("snippet", "").split())[:SNIPPET_LIMIT]
        lines += [
            f"{number}. {citation['title']} [{citation['source_name']}, score {citation['score']:.2f}]",
            f"   url: {citation['url']}",
            f"   {snippet}",
            "",
        ]
    return "\n".join(lines)
