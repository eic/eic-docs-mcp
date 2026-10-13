"""SQLite FTS5 index of documentation chunks."""

from __future__ import annotations

import sqlite3
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    title TEXT NOT NULL,
    heading TEXT,
    content TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_document ON chunks(document_id);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    title, heading, content,
    content='chunks', content_rowid='id',
    tokenize='porter unicode61 remove_diacritics 1'
);
CREATE TRIGGER IF NOT EXISTS chunks_insert AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, title, heading, content)
    VALUES (new.id, new.title, new.heading, new.content);
END;
CREATE TRIGGER IF NOT EXISTS chunks_delete AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, title, heading, content)
    VALUES ('delete', old.id, old.title, old.heading, old.content);
END;
CREATE TABLE IF NOT EXISTS sources (
    name TEXT PRIMARY KEY,
    commit_hash TEXT NOT NULL,
    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

SEARCH = """
SELECT documents.path, documents.title, chunks.heading, documents.url,
       snippet(chunks_fts, 2, '>>>', '<<<', ' ... ', 40) AS snippet
FROM chunks_fts
JOIN chunks ON chunks.id = chunks_fts.rowid
JOIN documents ON documents.id = chunks.document_id
WHERE chunks_fts MATCH ? AND (? IS NULL OR documents.source = ?)
ORDER BY bm25(chunks_fts, 10.0, 5.0, 1.0)
LIMIT ?
"""


class Database:
    """One connection; `location` is a file path or a sqlite URI."""

    def __init__(self, location: str, read_only: bool = False) -> None:
        if read_only:
            location = f"file:{location}?mode=ro"
        self.connection = sqlite3.connect(location, uri=True)
        self.connection.row_factory = sqlite3.Row
        if not read_only:
            self.connection.executescript(SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def file_hash(self, path: str) -> Optional[str]:
        row = self.connection.execute("SELECT file_hash FROM documents WHERE path = ?", (path,)).fetchone()
        return row["file_hash"] if row else None

    def document_paths(self) -> set[str]:
        return {row["path"] for row in self.connection.execute("SELECT path FROM documents")}

    def remove_document(self, path: str) -> None:
        self.connection.execute(
            "DELETE FROM chunks WHERE document_id IN (SELECT id FROM documents WHERE path = ?)", (path,)
        )
        self.connection.execute("DELETE FROM documents WHERE path = ?", (path,))

    def upsert_document(
        self, path: str, source: str, title: str, url: str, file_hash: str, content: str,
        chunks: list[tuple[Optional[str], str]],
    ) -> None:
        self.remove_document(path)
        cursor = self.connection.execute(
            "INSERT INTO documents (path, source, title, url, file_hash, content) VALUES (?, ?, ?, ?, ?, ?)",
            (path, source, title, url, file_hash, content),
        )
        self.connection.executemany(
            "INSERT INTO chunks (document_id, title, heading, content) VALUES (?, ?, ?, ?)",
            [(cursor.lastrowid, title, heading, chunk_content) for heading, chunk_content in chunks],
        )
        self.connection.commit()

    def search(self, query: str, source: Optional[str], limit: int) -> list[sqlite3.Row]:
        return self.connection.execute(SEARCH, (query, source, source, limit)).fetchall()

    def load_document(self, path: str) -> Optional[str]:
        row = self.connection.execute("SELECT content FROM documents WHERE path = ?", (path,)).fetchone()
        return row["content"] if row else None

    def record_source(self, name: str, commit_hash: str) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO sources (name, commit_hash) VALUES (?, ?)", (name, commit_hash)
        )
        self.connection.commit()

    def source_commits(self) -> dict[str, str]:
        return {row["name"]: row["commit_hash"] for row in self.connection.execute("SELECT * FROM sources")}
