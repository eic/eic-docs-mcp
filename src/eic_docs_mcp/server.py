"""MCP server: doc_search and doc_load over the SQLite index."""

from __future__ import annotations

import os
import re
import sqlite3
import threading
from typing import Optional

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from eic_docs_mcp import remote
from eic_docs_mcp.database import Database
from eic_docs_mcp.sources import index_path, load_sources

INSTRUCTIONS = """\
Full-text search over EIC/ePIC documentation: eic.github.io pages, the software
tutorials (eic-shell, analysis, file access with Rucio and XRootD, simulation,
reconstruction) and the READMEs of the EIC MCP servers.

Tools:
- doc_search(query, source=None, limit=10): ranked sections with path, url and snippet.
- doc_load(path): the full Markdown of one document, by the path from doc_search.
- doc_ask(question): an answer with numbered citations from the EIC smart-search
  service, when the server is configured with EIC_DOCS_API; it also covers the
  BNL wiki, the ePIC internal pages and Zenodo records. doc_search uses the same
  service when configured and falls back to the local index when it is unreachable.

Query rules: use two or three plain words; they are OR-joined with prefix matching
and stop words are dropped. A query containing FTS5 operators ("exact phrase",
AND, OR, NOT, NEAR, *) is passed through verbatim.
"""

NO_INDEX = "No documentation index. Build it with: eic-docs-mcp --update && eic-docs-mcp --index"
NO_REMOTE = "No search service configured. Set EIC_DOCS_API to its base URL, for example https://api.aprozo.com"
FTS5_OPERATORS = re.compile(r'["*]|\b(AND|OR|NOT|NEAR)\b')
STOP_WORDS = set(
    "a an the and or but in on at to for of with by from is it as be was are been do does did "
    "has have had this that these those i my me we our you your how what when where which who "
    "can will about into than then some just also".split()
)

mcp = FastMCP("eic-docs", instructions=INSTRUCTIONS)


def open_database() -> Optional[Database]:
    path = index_path()
    return Database(str(path), read_only=True) if path.is_file() else None


def normalise_query(query: str) -> str:
    """Plain words become `word* OR word*`; FTS5 syntax is left alone."""
    if FTS5_OPERATORS.search(query):
        return query
    words = [word for word in re.findall(r"\w+", query) if len(word) > 1 and word.lower() not in STOP_WORDS]
    return " OR ".join(f"{word}*" for word in words) or query


@mcp.tool()
def doc_search(query: str, source: Optional[str] = None, limit: int = 10) -> str:
    """Search EIC/ePIC documentation. Returns ranked sections with path, url and a snippet;
    pass the path to doc_load for the full text.

    query: two or three plain words, or FTS5 syntax ("exact phrase", AND, NOT, NEAR).
    source: restrict to one source name: a sources.yaml name for the local index, or a service
    source such as "eic_website", "bnl_wiki_epic", "zenodo_epic", "indico_events", "eic_github_org".
    """
    if remote.api_url():
        try:
            return remote.format_citations(remote.query(query, source, limit, generate_answer=False)["citations"]) or f"No results for: {query}"
        except OSError as error:
            remote_failure = f"Search service unreachable ({error}); results from the local index:\n\n"
    else:
        remote_failure = ""
    database = open_database()
    if database is None:
        return remote_failure + NO_INDEX
    try:
        rows = database.search(normalise_query(query), source, limit)
    except sqlite3.OperationalError as error:
        return f"Invalid search query: {error}. Retry with two or three plain words."
    finally:
        database.close()
    if not rows:
        return remote_failure + f"No results for: {query}"
    lines = [remote_failure] if remote_failure else []
    for number, row in enumerate(rows, 1):
        heading = f" > {row['heading']}" if row["heading"] else ""
        lines += [
            f"{number}. {row['title']}{heading}",
            f"   path: {row['path']}",
            f"   url: {row['url']}",
            f"   {row['snippet']}",
            "",
        ]
    return "\n".join(lines)


@mcp.tool()
def doc_load(path: str) -> str:
    """Return the full Markdown of one document; `path` is as shown by doc_search."""
    database = open_database()
    if database is None:
        return NO_INDEX
    content = database.load_document(path)
    database.close()
    return content if content is not None else f"Document not found: {path}"


@mcp.tool()
def doc_ask(question: str, limit: int = 6) -> str:
    """Ask the EIC smart-search service a question in plain language. Returns its answer
    with numbered citations (title, url, snippet). Needs EIC_DOCS_API on the server."""
    if not remote.api_url():
        return NO_REMOTE
    try:
        result = remote.query(question, None, limit, generate_answer=True)
    except OSError as error:
        return f"Search service unreachable: {error}. Retry later, or use doc_search on the local index."
    hint = f"\n{result['expert_hint']}\n" if result.get("expert_hint") else ""
    return f"{result['answer']}\n{hint}\nCitations:\n{remote.format_citations(result['citations'])}"


@mcp.resource("eic-docs://sources")
def sources_resource() -> str:
    """Indexed sources with the commit each was last indexed at."""
    commits = {}
    if database := open_database():
        commits = database.source_commits()
        database.close()
    lines = [f"search service: {remote.api_url() or 'not configured'}"]
    lines += [
        f"{source.name}: {source.url} ({source.branch}) indexed at {commits.get(source.name, 'never')}"
        for source in load_sources()
    ]
    return "\n".join(lines)


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


@mcp.custom_route("/refresh", methods=["POST"])
async def refresh(request: Request) -> PlainTextResponse:
    """Pull the sources and update the index now. A source's publish workflow calls this
    with `Authorization: Bearer $EIC_DOCS_REFRESH_TOKEN`; without the token configured the
    route does not exist."""
    token = os.getenv("EIC_DOCS_REFRESH_TOKEN", "")
    if not token:
        return PlainTextResponse("refresh is not enabled", status_code=404)
    if request.headers.get("authorization") != f"Bearer {token}":
        return PlainTextResponse("unauthorized", status_code=401)
    from eic_docs_mcp import cli

    threading.Thread(target=lambda: (cli.update(), cli.index()), daemon=True).start()
    return PlainTextResponse("refresh started", status_code=202)


def serve(transport: str, host: str, port: int) -> None:
    mcp.settings.host = host
    mcp.settings.port = port
    mcp.run("streamable-http" if transport == "http" else "stdio")
