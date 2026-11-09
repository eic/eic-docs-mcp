"""Turn Markdown files from the source checkouts into index entries."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Optional

import yaml

from eic_docs_mcp.database import Database
from eic_docs_mcp.sources import Source, document_url, source_commit

log = logging.getLogger(__name__)

FRONT_MATTER = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)
NOISE = [
    re.compile(r"{%.*?%}", re.DOTALL),  # Liquid tags
    re.compile(r"{{.*?}}", re.DOTALL),  # Liquid variables
    re.compile(r"{:[^}\n]*}"),  # kramdown attribute lists
    re.compile(r"^:{3,}.*$", re.MULTILINE),  # Carpentries fences
]
HEADING_1 = re.compile(r"^# +(.+?)\s*$", re.MULTILINE)
HEADING_2 = re.compile(r"^## +(.+?)\s*$", re.MULTILINE)


def split_front_matter(text: str) -> tuple[dict, str]:
    match = FRONT_MATTER.match(text)
    if not match:
        return {}, text
    try:
        metadata = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        metadata = None
    return (metadata if isinstance(metadata, dict) else {}), text[match.end():]


def clean(body: str) -> str:
    for pattern in NOISE:
        body = pattern.sub("", body)
    return re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"


def podio_markdown(text: str, title: str) -> str:
    """A podio data model (YAML) as Markdown: one section per type."""
    model = yaml.safe_load(text) or {}
    lines = [f"# {title}", ""]
    for kind in ("components", "datatypes", "links"):
        for name, spec in (model.get(kind) or {}).items():
            lines.append(f"## {name}")
            if spec.get("Description"):
                lines.append(str(spec["Description"]))
            for key in ("Members", "VectorMembers", "OneToOneRelations", "OneToManyRelations", "From", "To"):
                values = spec.get(key)
                if values:
                    lines.append(f"{key}:")
                    lines += ["- " + " ".join(str(v).split()) for v in (values if isinstance(values, list) else [values])]
            lines.append("")
    return "\n".join(lines)


def title_of(metadata: dict, body: str, relative_path: str) -> str:
    if metadata.get("title"):
        return str(metadata["title"])
    heading = HEADING_1.search(body)
    return heading.group(1) if heading else Path(relative_path).stem


def chunk(body: str) -> list[tuple[Optional[str], str]]:
    """Split on `## ` headings; the text before the first heading has heading None."""
    pieces = HEADING_2.split(body)
    chunks: list[tuple[Optional[str], str]] = []
    if pieces[0].strip():
        chunks.append((None, pieces[0].strip()))
    for heading, content in zip(pieces[1::2], pieces[2::2]):
        chunks.append((heading, content.strip()))
    return chunks


def source_files(source: Source, repos: Path) -> list[Path]:
    checkout = repos / source.name
    return sorted({file for pattern in source.files for file in checkout.glob(pattern) if file.is_file()})


def index_source(database: Database, source: Source, repos: Path) -> dict[str, int]:
    counts = {"indexed": 0, "skipped": 0, "removed": 0}
    seen: set[str] = set()
    for file in source_files(source, repos):
        relative_path = str(file.relative_to(repos / source.name))
        path = f"{source.name}/{relative_path}"
        seen.add(path)
        raw = file.read_bytes()
        file_hash = hashlib.sha256(raw).hexdigest()
        if database.file_hash(path) == file_hash:
            counts["skipped"] += 1
            continue
        text = raw.decode("utf-8", errors="replace")
        if file.suffix == ".yaml":
            metadata, body = {}, podio_markdown(text, f"{source.name} data model")
        else:
            metadata, body = split_front_matter(text)
        body = clean(body)
        database.upsert_document(
            path, source.name, title_of(metadata, body, relative_path), document_url(source, relative_path),
            file_hash, body, chunk(body),
        )
        counts["indexed"] += 1
    for path in database.document_paths():
        if path.startswith(f"{source.name}/") and path not in seen:
            database.remove_document(path)
            counts["removed"] += 1
    return counts


def build_index(database: Database, sources: list[Source], repos: Path) -> None:
    for source in sources:
        if not (repos / source.name).is_dir():
            log.warning("%s: not checked out, run --update first", source.name)
            continue
        counts = index_source(database, source, repos)
        database.record_source(source.name, source_commit(source, repos))
        log.info("%s: %s", source.name, ", ".join(f"{count} {label}" for label, count in counts.items()))
