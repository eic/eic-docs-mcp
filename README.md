# eic-docs-mcp

An MCP server that gives AI agents full-text search over EIC/ePIC documentation:
the [eic.github.io](https://eic.github.io) pages, the software tutorials
(environment setup, analysis, file access, simulation, reconstruction, MCP) and
the READMEs of the EIC MCP servers. The sources are Markdown files in git
repositories, listed in [`sources.yaml`](sources.yaml); they are cloned, cleaned
and indexed into a local SQLite FTS5 database.

## Tools

- `doc_search(query, source=None, limit=10)`: BM25-ranked sections matching the
  query, each with title, heading, path, url and a snippet. `source` restricts
  the search to one entry of `sources.yaml` (for example `tutorial-file-access`).
- `doc_load(path)`: the full cleaned Markdown of one document, by the path shown
  in `doc_search` results.

Query rules: two or three plain words work best. Plain words are OR-joined with
prefix matching and stop words are dropped. A query that contains FTS5 syntax
(`"exact phrase"`, `AND`, `OR`, `NOT`, `NEAR`, `*`) is passed through verbatim.

The resource `eic-docs://sources` lists the sources and the commit each was last
indexed at.

## The EIC smart-search service as backend

With `EIC_DOCS_API` set to the base URL of an
[eic_smart_search](https://github.com/eic/eic_smart_search) instance, `doc_search`
queries that service instead of the local index, and a third tool `doc_ask` returns its
generated answer with numbered citations. The service also covers the BNL wiki, the ePIC
internal pages and Zenodo records. When it is unreachable, `doc_search` falls back to the
local index and says so.

```bash
EIC_DOCS_API=https://api.aprozo.com eic-docs-mcp --transport http
```

## Hosted server

The hosted instance serves streamable HTTP at one URL, with no credentials:

```
https://<host>/mcp
```

### Claude Code (`.mcp.json`)

```json
{
  "mcpServers": {
    "eic-docs": { "type": "http", "url": "https://<host>/mcp" }
  }
}
```

### opencode (`opencode.json`)

```json
{
  "mcp": {
    "eic-docs": { "type": "remote", "url": "https://<host>/mcp" }
  }
}
```

### Codex (`~/.codex/config.toml`)

```toml
[mcp_servers.eic-docs]
url = "https://<host>/mcp"
```

### Gemini CLI (`~/.gemini/settings.json`)

```json
{
  "mcpServers": {
    "eic-docs": { "httpUrl": "https://<host>/mcp" }
  }
}
```

## Running locally

Requirements: Python 3.10 or newer, `git`, and [uv](https://docs.astral.sh/uv/).

```bash
export EIC_DOCS_SITE=~/.local/share/eic-docs-mcp   # default; holds repos/ and index.db
uvx git+https://github.com/eic/eic-docs-mcp --update   # clone or pull the sources
uvx git+https://github.com/eic/eic-docs-mcp --index    # build or update the index
uvx git+https://github.com/eic/eic-docs-mcp            # serve over stdio
```

Re-running `--index` only reprocesses files whose content changed and removes
documents whose file disappeared. Diagnostics go to stderr; stdout is the MCP
channel.

## When the index is updated

Only when asked: `--update` pulls the sources and `--index` rebuilds what changed.
A long-running server refreshes itself with `--refresh-hours N`; the Docker image
does this every 24 hours (`EIC_DOCS_REFRESH_HOURS`) and also on every start. With
`EIC_DOCS_REFRESH_TOKEN` set, `POST /refresh` with `Authorization: Bearer <token>` starts
a refresh at once; a documentation repository's publish workflow can call it, so a
merged page is searchable minutes later. A
stdio server started by a client reads the index as it is; refresh it from time
to time, or point the client at `EIC_DOCS_API` and let the service do it.

Claude Code configuration for the local stdio server:

```json
{
  "mcpServers": {
    "eic-docs": {
      "command": "uvx",
      "args": ["git+https://github.com/eic/eic-docs-mcp"]
    }
  }
}
```

To serve over HTTP instead:

```bash
eic-docs-mcp --transport http --host 0.0.0.0 --port 8000   # endpoint /mcp, health check /healthz
```

### Docker

The image updates the sources and rebuilds the index on every start, then
serves HTTP on port 8000:

```bash
docker build -t eic-docs-mcp .
docker run -p 8000:8000 eic-docs-mcp
```

## Adding a source

Append an entry to `sources.yaml`:

```yaml
- name: my-tutorial                      # first path component of its documents
  url: https://github.com/eic/my-tutorial
  branch: main
  files:                                 # globs relative to the checkout
    - episodes/*.md
    - index.md
```

Then run `--update` and `--index`. Page URLs are derived for `eic.github.io`
collections and for `tutorial-*` repositories published on eic.github.io; a
source with `pages: https://host/base` maps every file to `<pages>/<path>.html`;
other files link to their GitHub blob. The indexer strips YAML front matter, Jekyll
and Liquid tags, kramdown attribute lists and Carpentries `::::` fence lines,
and splits each document into chunks on `## ` headings.

## Development

```bash
uv sync
uv run pytest -q
```

## License

MIT
