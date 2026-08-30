import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.desktop import DesktopFileAccess


def _install(client: TestClient, folder: Path) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    access = DesktopFileAccess()
    access.register_root(str(folder))
    app.state.desktop_files = access


def test_endpoints_hidden_without_desktop_access(client: TestClient) -> None:
    assert isinstance(client.app, FastAPI)
    assert not hasattr(client.app.state, "desktop_files")
    response = client.get("/api/v1/desktop/folder", params={"path": "/tmp"})
    assert response.status_code == 404
    response = client.get("/api/v1/desktop/file", params={"path": "/tmp/x"})
    assert response.status_code == 404


def test_folder_listing_streams_files(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "docs"
    (root / "sub").mkdir(parents=True)
    (root / "a.pdf").write_bytes(b"AAA")
    (root / "sub" / "b.txt").write_bytes(b"BB")
    (root / ".DS_Store").write_bytes(b"junk")
    _install(client, root)

    response = client.get("/api/v1/desktop/folder", params={"path": str(root)})
    assert response.status_code == 200
    payload = response.json()
    assert payload["path"] == str(root.resolve())
    rels = [entry["rel"] for entry in payload["files"]]
    assert rels == ["docs/.DS_Store", "docs/a.pdf", "docs/sub/b.txt"]
    sizes = {entry["rel"]: entry["size"] for entry in payload["files"]}
    assert sizes["docs/a.pdf"] == 3

    listed = {entry["rel"]: entry["path"] for entry in payload["files"]}
    file_response = client.get(
        "/api/v1/desktop/file", params={"path": listed["docs/sub/b.txt"]}
    )
    assert file_response.status_code == 200
    assert file_response.content == b"BB"


def test_paths_outside_roots_rejected(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_bytes(b"secret")
    _install(client, root)

    assert client.get("/api/v1/desktop/folder", params={"path": str(outside)}).status_code == 404
    assert client.get("/api/v1/desktop/file", params={"path": str(outside)}).status_code == 404
    missing = root / "missing.pdf"
    assert client.get("/api/v1/desktop/file", params={"path": str(missing)}).status_code == 404
    traversal = str(root / ".." / "secret.txt")
    assert client.get("/api/v1/desktop/file", params={"path": traversal}).status_code == 404
    assert (
        client.get("/api/v1/desktop/folder", params={"path": str(root / "a.pdf")}).status_code
        == 422
    )


def test_folder_path_must_be_directory(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    target = root / "file.txt"
    target.write_bytes(b"x")
    _install(client, root)
    assert client.get("/api/v1/desktop/folder", params={"path": str(target)}).status_code == 422


def test_register_root_rejects_non_directory(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_bytes(b"x")
    access = DesktopFileAccess()
    with pytest.raises(NotADirectoryError):
        access.register_root(str(target))


@pytest.mark.skipif(sys.platform == "win32", reason="symlink support")
def test_symlinks_escape_is_contained(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "docs"
    (root / "real").mkdir(parents=True)
    (root / "real" / "in.txt").write_bytes(b"in")
    secret = tmp_path / "secret"
    secret.mkdir()
    (secret / "out.txt").write_bytes(b"out")
    os.symlink(secret / "out.txt", root / "linked.txt")
    os.symlink(secret, root / "linked-dir")
    _install(client, root)

    response = client.get("/api/v1/desktop/folder", params={"path": str(root)})
    assert response.status_code == 200
    rels = [entry["rel"] for entry in response.json()["files"]]
    assert rels == ["docs/real/in.txt"]
