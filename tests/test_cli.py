from eic_docs_mcp import cli


def test_first_index(tmp_path, monkeypatch):
    monkeypatch.setenv("EIC_DOCS_SITE", str(tmp_path))
    monkeypatch.setenv("EIC_DOCS_INDEX_URL", "")
    calls = []
    monkeypatch.setattr(cli, "update", lambda: calls.append("update"))
    monkeypatch.setattr(cli, "build_index", lambda *_: calls.append("index"))
    cli.first_index()
    assert calls == ["update", "index"]
    assert (tmp_path / "index.db").is_file()
    assert not (tmp_path / "index.db.part").exists()


def test_first_index_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("EIC_DOCS_SITE", str(tmp_path))
    monkeypatch.setenv("EIC_DOCS_INDEX_URL", "")

    def offline():
        raise OSError("no network")

    monkeypatch.setattr(cli, "update", offline)
    cli.first_index()
    assert not (tmp_path / "index.db").exists()


def test_refresh_waits_for_first_index(monkeypatch):
    import threading
    calls = []
    monkeypatch.setattr(cli, "update", lambda: calls.append("update"))
    monkeypatch.setattr(cli, "index", lambda *_: calls.append("index"))
    with cli.REFRESH_LOCK:
        worker = threading.Thread(target=cli.refresh)
        worker.start()
        worker.join(0.2)
        assert calls == []
    worker.join(2)
    assert calls == ["update", "index"]


def published(tmp_path, data, checksum=None):
    import hashlib
    release = tmp_path / "release"
    release.mkdir()
    (release / "index.db").write_bytes(data)
    (release / "index.db.sha256").write_text(f"{checksum or hashlib.sha256(data).hexdigest()}  index.db\n")
    return (release / "index.db").as_uri()


def test_first_index_download(tmp_path, monkeypatch):
    monkeypatch.setenv("EIC_DOCS_SITE", str(tmp_path / "site"))
    monkeypatch.setenv("EIC_DOCS_INDEX_URL", published(tmp_path, b"prebuilt"))

    def no_build():
        raise AssertionError("built although the download worked")

    monkeypatch.setattr(cli, "update", no_build)
    cli.first_index()
    assert (tmp_path / "site" / "index.db").read_bytes() == b"prebuilt"


def test_first_index_bad_checksum(tmp_path, monkeypatch):
    monkeypatch.setenv("EIC_DOCS_SITE", str(tmp_path / "site"))
    monkeypatch.setenv("EIC_DOCS_INDEX_URL", published(tmp_path, b"prebuilt", checksum="0" * 64))
    calls = []
    monkeypatch.setattr(cli, "update", lambda: calls.append("update"))
    monkeypatch.setattr(cli, "build_index", lambda *_: calls.append("index"))
    cli.first_index()
    assert calls == ["update", "index"]
