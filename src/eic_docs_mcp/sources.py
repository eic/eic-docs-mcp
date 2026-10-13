"""Documentation sources (sources.yaml), the site directory and git checkouts."""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

# The wheel carries a copy of sources.yaml inside the package; a development
# checkout reads the file at the repository root.
SOURCES_FILE = next(
    path
    for path in (Path(__file__).with_name("sources.yaml"), Path(__file__).parents[2] / "sources.yaml")
    if path.exists()
)


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    branch: str
    files: list[str]
    pages: str = ""   # base URL of the published site, when every file maps to <pages>/<path>.html


def load_sources(sources_file: Path = SOURCES_FILE) -> list[Source]:
    with open(sources_file) as stream:
        return [Source(**entry) for entry in yaml.safe_load(stream)]


def site_directory() -> Path:
    return Path(os.environ.get("EIC_DOCS_SITE", "~/.local/share/eic-docs-mcp")).expanduser()


def index_path() -> Path:
    return site_directory() / "index.db"


def repos_directory() -> Path:
    return site_directory() / "repos"


def git(*arguments: str) -> str:
    return subprocess.run(["git", *arguments], check=True, capture_output=True, text=True).stdout.strip()


def update_source(source: Source, repos: Path) -> None:
    """Clone the source on first use, otherwise fast-forward it."""
    checkout = repos / source.name
    if checkout.is_dir():
        log.info("Updating %s", source.name)
        git("-C", str(checkout), "pull", "--quiet", "--ff-only", "origin", source.branch)
    else:
        log.info("Cloning %s", source.name)
        repos.mkdir(parents=True, exist_ok=True)
        git("clone", "--quiet", "--depth", "1", "--branch", source.branch, source.url, str(checkout))


def source_commit(source: Source, repos: Path) -> str:
    return git("-C", str(repos / source.name), "rev-parse", "--short", "HEAD")


def document_url(source: Source, relative_path: str) -> str:
    """Public page for a file where it can be derived, otherwise the GitHub blob."""
    parts = Path(relative_path).parts
    stem = Path(relative_path).stem
    if source.pages:
        return f"{source.pages}/{Path(relative_path).with_suffix('.html')}"
    if source.name == "eic.github.io" and parts[0].startswith("_"):
        return f"https://eic.github.io/{parts[0][1:]}/{stem}.html"
    if source.name.startswith("tutorial-"):
        page = f"{stem}/index.html" if parts[0] == "_episodes" else f"{stem}.html"
        return f"https://eic.github.io/{source.name}/{page}"
    return f"{source.url}/blob/{source.branch}/{relative_path}"
