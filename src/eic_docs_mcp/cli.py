"""Command line entry point: --update, --index, or serve."""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

from eic_docs_mcp.database import Database
from eic_docs_mcp.indexer import build_index
from eic_docs_mcp.sources import index_path, load_sources, repos_directory, update_source


def main() -> None:
    parser = argparse.ArgumentParser(prog="eic-docs-mcp", description="EIC documentation search MCP server")
    parser.add_argument("--update", action="store_true", help="clone or pull every source, then exit")
    parser.add_argument("--index", action="store_true", help="build or update the search index, then exit")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--refresh-hours", type=float, default=0,
        help="while serving, pull the sources and update the index every N hours (0: never)",
    )
    arguments = parser.parse_args()
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(message)s", force=True)

    if arguments.update:
        update()
    if arguments.index:
        index()
    if arguments.update or arguments.index:
        return

    from eic_docs_mcp.server import serve

    if not index_path().is_file():
        threading.Thread(target=first_index, daemon=True).start()
    if arguments.refresh_hours > 0:
        threading.Thread(target=refresh_forever, args=(arguments.refresh_hours,), daemon=True).start()
    serve(arguments.transport, arguments.host, arguments.port)


def update() -> None:
    for source in load_sources():
        update_source(source, repos_directory())


def index(path: Path | None = None) -> None:
    path = path or index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    database = Database(str(path))
    build_index(database, load_sources(), repos_directory())
    database.close()


REFRESH_LOCK = threading.Lock()
INDEX_URL = "https://github.com/eic/eic-docs-mcp/releases/download/index/index.db"


def refresh() -> None:
    """Pull and re-index; a failure is logged and tried again next time."""
    try:
        with REFRESH_LOCK:
            update()
            index()
    except Exception as error:  # a network or git failure must not stop the server
        logging.getLogger(__name__).warning("refresh failed: %s", error)


def first_index() -> None:
    """Build into index.db.part and rename, so searches never see a partial index."""
    target = index_path()
    partial = target.with_name(target.name + ".part")
    try:
        with REFRESH_LOCK:
            partial.unlink(missing_ok=True)
            if not download_index(partial):
                update()
                index(partial)
            partial.replace(target)
    except Exception as error:  # no network or git: keep serving
        logging.getLogger(__name__).warning("first index failed: %s", error)


def fetch(url: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": "eic-docs-mcp"}), timeout=60) as response:
        return response.read()


def download_index(path: Path) -> bool:
    """Download the prebuilt index. False if it is unreachable or fails the sha256 check."""
    url = os.getenv("EIC_DOCS_INDEX_URL", INDEX_URL)
    if not url:
        return False
    try:
        data = fetch(url)
        expected = fetch(url + ".sha256").split()[0].decode()
    except (OSError, IndexError, UnicodeDecodeError) as error:
        logging.getLogger(__name__).warning("no prebuilt index: %s", error)
        return False
    if hashlib.sha256(data).hexdigest() != expected:
        logging.getLogger(__name__).warning("prebuilt index failed its checksum")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def refresh_forever(hours: float, sleep=time.sleep) -> None:
    """Pull and re-index every `hours`."""
    while True:
        sleep(hours * 3600)
        refresh()
