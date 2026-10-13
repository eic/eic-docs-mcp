from eic_docs_mcp import server
from eic_docs_mcp.server import doc_load, doc_search, normalise_query


def test_search_ranking(indexed):
    result = doc_search("datasets")
    first, *_ = result.split("\n\n")
    assert first.startswith("1. Rucio Usage > Datasets and DIDs")
    assert "path: tutorial-file-access/episodes/02-rucio_usage.md" in first
    assert "url: https://eic.github.io/tutorial-file-access/02-rucio_usage.html" in first
    assert ">>>datasets<<<" in first
    assert "rucio-eic-mcp-server/README.md" in result


def test_source_filter(indexed):
    result = doc_search("rucio", source="rucio-eic-mcp-server")
    assert "path: rucio-eic-mcp-server/README.md" in result
    assert "tutorial-file-access" not in result
    assert doc_search("rucio", source="eic.github.io") == "No results for: rucio"
    assert doc_search("rucio", limit=1).count("\n   path: ") == 1


def test_query_normalisation():
    assert normalise_query("how do I install eic-shell?") == "install* OR eic* OR shell*"
    assert normalise_query("the a") == "the a"
    assert normalise_query('"eic shell"') == '"eic shell"'
    assert normalise_query("rucio AND dataset") == "rucio AND dataset"
    assert normalise_query("rucio NOT xrootd") == "rucio NOT xrootd"


def test_invalid_query(indexed):
    assert doc_search('"unbalanced').startswith("Invalid search query: ")
    assert doc_search('"unbalanced').endswith("Retry with two or three plain words.")


def test_doc_load(indexed):
    content = doc_load("tutorial-file-access/episodes/02-rucio_usage.md")
    assert content.startswith("- How can I use Rucio?\n\n## Getting Started")
    assert doc_load("nowhere.md") == "Document not found: nowhere.md"


def test_missing_index(monkeypatch):
    monkeypatch.setattr(server, "open_database", lambda: None)
    assert doc_search("anything") == server.NO_INDEX
    assert doc_load("x.md") == server.NO_INDEX


def test_refresh_forever_pulls_and_indexes_each_period(monkeypatch):
    from eic_docs_mcp import cli
    calls = []
    monkeypatch.setattr(cli, "update", lambda: calls.append("update"))
    monkeypatch.setattr(cli, "index", lambda: calls.append("index"))
    slept = []

    def fake_sleep(seconds):
        slept.append(seconds)
        if len(slept) == 2:
            raise KeyboardInterrupt
    try:
        cli.refresh_forever(0.5, sleep=fake_sleep)
    except KeyboardInterrupt:
        pass
    assert slept == [1800, 1800] and calls == ["update", "index"]


def test_refresh_route(monkeypatch):
    import asyncio
    from eic_docs_mcp import cli
    from eic_docs_mcp.server import refresh

    class FakeRequest:
        def __init__(self, authorization=None):
            self.headers = {"authorization": authorization} if authorization else {}

    monkeypatch.delenv("EIC_DOCS_REFRESH_TOKEN", raising=False)
    assert asyncio.run(refresh(FakeRequest("Bearer x"))).status_code == 404
    monkeypatch.setenv("EIC_DOCS_REFRESH_TOKEN", "secret")
    assert asyncio.run(refresh(FakeRequest("Bearer wrong"))).status_code == 401
    started = []
    monkeypatch.setattr(cli, "update", lambda: started.append("update"))
    monkeypatch.setattr(cli, "index", lambda: started.append("index"))
    response = asyncio.run(refresh(FakeRequest("Bearer secret")))
    import time
    for _ in range(50):
        if started == ["update", "index"]:
            break
        time.sleep(0.02)
    assert response.status_code == 202 and started == ["update", "index"]
