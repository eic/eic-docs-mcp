import shutil
from pathlib import Path

import pytest

from eic_docs_mcp import server
from eic_docs_mcp.database import Database
from eic_docs_mcp.indexer import index_source
from eic_docs_mcp.sources import Source

FIXTURES = Path(__file__).parent / "fixtures" / "repos"
SOURCES = [
    Source("eic.github.io", "https://github.com/eic/eic.github.io", "master", ["_documentation/*.md"]),
    Source("tutorial-file-access", "https://github.com/eic/tutorial-file-access", "main", ["episodes/*.md"]),
    Source("rucio-eic-mcp-server", "https://github.com/eic/rucio-eic-mcp-server", "main", ["README.md"]),
]


def index_all(database: Database, repos: Path) -> dict[str, dict[str, int]]:
    return {source.name: index_source(database, source, repos) for source in SOURCES}


@pytest.fixture
def repos(tmp_path: Path) -> Path:
    """A writable copy of the fixture tree, so tests can change and delete files."""
    return shutil.copytree(FIXTURES, tmp_path / "repos")


@pytest.fixture
def database(request, monkeypatch) -> Database:
    """A shared in-memory database; the server opens fresh connections to the same one."""
    location = f"file:{request.node.name}?mode=memory&cache=shared"
    shared = Database(location)
    monkeypatch.setattr(server, "open_database", lambda: Database(location))
    yield shared
    shared.close()


@pytest.fixture
def indexed(database: Database, repos: Path) -> Database:
    index_all(database, repos)
    return database
