from eic_docs_mcp import cli


def test_first_index(tmp_path, monkeypatch):
    monkeypatch.setenv("EIC_DOCS_SITE", str(tmp_path))
    calls = []
    monkeypatch.setattr(cli, "update", lambda: calls.append("update"))
    monkeypatch.setattr(cli, "build_index", lambda *_: calls.append("index"))
    cli.first_index()
    assert calls == ["update", "index"]
    assert (tmp_path / "index.db").is_file()
    assert not (tmp_path / "index.db.part").exists()


def test_first_index_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("EIC_DOCS_SITE", str(tmp_path))

    def offline():
        raise OSError("no network")

    monkeypatch.setattr(cli, "update", offline)
    cli.first_index()
    assert not (tmp_path / "index.db").exists()
