from eic_docs_mcp import remote, server

CITATIONS = [
    {"title": "Campaigns", "url": "https://eic.github.io/x.html", "snippet": "  YY.MM.Ver  naming\n", "source_name": "eic_website", "score": 0.61},
]


def test_doc_search_uses_the_service(monkeypatch):
    monkeypatch.setenv("EIC_DOCS_API", "https://example.org/")
    seen = {}

    def fake_post(url, body):
        seen["url"], seen["body"] = url, body
        return {"answer": "", "citations": CITATIONS}

    monkeypatch.setattr(remote, "post_json", fake_post)
    text = server.doc_search("campaign naming", source="eic_website", limit=3)
    assert seen["url"] == "https://example.org/query"
    assert seen["body"] == {"query": "campaign naming", "top_k": 9, "generate_answer": False, "client": "eic-docs-mcp"}
    assert "1. Campaigns [eic_website, score 0.61]" in text and "YY.MM.Ver naming" in text


def test_source_restriction_is_applied_by_the_client(monkeypatch):
    monkeypatch.setenv("EIC_DOCS_API", "https://example.org")
    other = dict(CITATIONS[0], title="Elsewhere", source_name="indico_events")
    monkeypatch.setattr(remote, "post_json", lambda url, body: {"answer": "", "citations": [other, CITATIONS[0]]})
    text = server.doc_search("campaign", source="eic_website", limit=1)
    assert "Campaigns" in text and "Elsewhere" not in text


def test_doc_search_falls_back_to_the_index(monkeypatch):
    monkeypatch.setenv("EIC_DOCS_API", "https://example.org")

    def failing_post(url, body):
        raise OSError("connection refused")

    monkeypatch.setattr(remote, "post_json", failing_post)
    monkeypatch.setattr(server, "open_database", lambda: None)
    text = server.doc_search("anything")
    assert text.startswith("Search service unreachable (connection refused)") and server.NO_INDEX in text


def test_doc_ask(monkeypatch):
    monkeypatch.delenv("EIC_DOCS_API", raising=False)
    assert server.doc_ask("how?") == server.NO_REMOTE
    monkeypatch.setenv("EIC_DOCS_API", "https://example.org")
    monkeypatch.setattr(remote, "post_json", lambda url, body: {"answer": "Monthly, YY.MM.Ver.", "citations": CITATIONS})
    text = server.doc_ask("how are campaigns named")
    assert text.startswith("Monthly, YY.MM.Ver.") and "Citations:" in text and "https://eic.github.io/x.html" in text
