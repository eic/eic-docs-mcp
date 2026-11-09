from pathlib import Path

from conftest import SOURCES, index_all
from eic_docs_mcp.indexer import chunk, clean, index_source, podio_markdown, split_front_matter, title_of
from eic_docs_mcp.sources import document_url


def chunks_of(database, path):
    return database.connection.execute(
        "SELECT chunks.heading, chunks.content FROM chunks JOIN documents ON documents.id = chunks.document_id"
        " WHERE documents.path = ? ORDER BY chunks.id", (path,)
    ).fetchall()


def test_chunking(indexed):
    chunks = chunks_of(indexed, "tutorial-file-access/episodes/02-rucio_usage.md")
    assert [heading for heading, _ in chunks] == [None, "Getting Started", "Datasets and DIDs"]
    assert chunks[0]["content"] == "- How can I use Rucio?"
    assert "::::" not in chunks[2]["content"]
    assert "### Warning" in chunks[2]["content"]


def test_jekyll_cleanup(indexed):
    content = indexed.load_document("eic.github.io/_documentation/getstarted.md")
    assert "{%" not in content and "{{" not in content and "{:" not in content
    assert "![emailicon](../assets/images/site/icons/email.png)" in content
    assert content.startswith("Welcome to the **Get Started** section.")


def test_title_precedence(indexed):
    titles = dict(indexed.connection.execute("SELECT path, title FROM documents"))
    assert titles["eic.github.io/_documentation/getstarted.md"] == "Get Started"
    assert titles["rucio-eic-mcp-server/README.md"] == "Rucio EIC MCP server"
    assert title_of({"title": "From front matter"}, "# From heading\n", "file.md") == "From front matter"
    assert title_of({}, "no headings here\n", "03-use_cases.md") == "03-use_cases"


def test_front_matter_and_chunk_helpers():
    metadata, body = split_front_matter("---\ntitle: T\n---\n# H\n\ntext\n")
    assert metadata == {"title": "T"} and body == "# H\n\ntext\n"
    assert split_front_matter("plain\n") == ({}, "plain\n")
    assert split_front_matter("---\ntitle: T\n---") == ({"title": "T"}, "")
    assert chunk("## Only\n\nbody\n") == [("Only", "body")]
    assert clean("a\n\n\n\n{% x %}b\n") == "a\n\nb\n"


def test_incremental_skip(database, repos):
    first = index_all(database, repos)
    assert {name: counts["indexed"] for name, counts in first.items()} == {name: 1 for name in first}
    second = index_all(database, repos)
    assert all(counts == {"indexed": 0, "skipped": 1, "removed": 0} for counts in second.values())
    (repos / "rucio-eic-mcp-server" / "README.md").write_text("# Changed\n")
    assert index_source(database, SOURCES[2], repos)["indexed"] == 1


def test_pruning(database, repos):
    index_all(database, repos)
    (repos / "rucio-eic-mcp-server" / "README.md").unlink()
    assert index_source(database, SOURCES[2], repos)["removed"] == 1
    assert "rucio-eic-mcp-server/README.md" not in database.document_paths()
    assert len(database.document_paths()) == 2
    assert database.connection.execute("SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH 'uvx'").fetchone()[0] == 0


def test_document_url():
    assert document_url(SOURCES[0], "_documentation/getstarted.md") == "https://eic.github.io/documentation/getstarted.html"
    assert document_url(SOURCES[1], "episodes/02-rucio_usage.md") == "https://eic.github.io/tutorial-file-access/02-rucio_usage.html"
    assert document_url(SOURCES[1], "_episodes/01-introduction.md") == "https://eic.github.io/tutorial-file-access/01-introduction/index.html"
    assert document_url(SOURCES[2], "README.md") == "https://github.com/eic/rucio-eic-mcp-server/blob/main/README.md"


def test_document_url_with_a_pages_base():
    from eic_docs_mcp.sources import Source, document_url
    source = Source(name="guide", url="https://github.com/x/y", branch="main", files=[], pages="https://aprozo.com/eic")
    assert document_url(source, "docs/eicrecon/algorithms/hexplit.md") == "https://aprozo.com/eic/docs/eicrecon/algorithms/hexplit.html"


def test_podio_markdown():
    model = """
components:
  edm4hep::Vector3f:
    Members:
      - float x
datatypes:
  edm4eic::ReconstructedParticle:
    Description: "Reconstructed particle"
    Members:
      - float             energy            // [GeV] energy
    OneToManyRelations:
      - edm4eic::Track tracks // tracks used
links:
  edm4eic::MCRecoParticleLink:
    Description: "Reco to MC"
    From: edm4eic::ReconstructedParticle
    To: edm4hep::MCParticle
"""
    body = podio_markdown(model, "EDM4eic data model")
    assert body.startswith("# EDM4eic data model\n")
    assert "## edm4eic::ReconstructedParticle\nReconstructed particle\nMembers:\n- float energy // [GeV] energy" in body
    assert "OneToManyRelations:\n- edm4eic::Track tracks // tracks used" in body
    assert "## edm4eic::MCRecoParticleLink" in body and "To:\n- edm4hep::MCParticle" in body
