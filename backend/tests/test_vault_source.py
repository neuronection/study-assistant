"""Markdown-vault preset: notes ingest, wikilinks, rescan/versioning, export (plan 85 D)."""

import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient


def _course(client: TestClient) -> str:
    response = client.post("/api/v1/courses", json={"title": "Calculus"})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _vault(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "Linear Algebra.md").write_text(
        "---\ntitle: Linear Algebra\ntags: [math, algebra]\n---\n\n"
        "Vectors and matrices. See [[Eigenvalues]].\n",
        encoding="utf-8",
    )
    (root / "Eigenvalues.md").write_text(
        "# Eigenvalues\n\n"
        "An eigenvector satisfies $Av = \\lambda v$. Back to "
        "[[Linear Algebra|the course note]] and [[Missing Note]].\n",
        encoding="utf-8",
    )
    (root / "ignored.txt").write_text("not a note", encoding="utf-8")


def _source(client: TestClient, course_id: str, root: Path) -> str:
    response = client.post(
        "/api/v1/sources",
        json={
            "label": "Course vault",
            "path": str(root),
            "course_id": course_id,
            "preset": "vault",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_vault_scan_creates_notes_and_resolves_wikilinks(
    client: TestClient, tmp_path: Path
) -> None:
    root = tmp_path / "vault"
    _vault(root)
    with client:
        course_id = _course(client)
        source_id = _source(client, course_id, root)
        scan = client.post(f"/api/v1/sources/{source_id}/scan")
        assert scan.status_code == 200, scan.text
        assert scan.json()["stats"]["new"] == 2

        notes = client.get(f"/api/v1/notes?course_id={course_id}").json()["items"]
        by_title = {note["title"]: note for note in notes}
        assert set(by_title) == {"Linear Algebra", "Eigenvalues"}
        assert by_title["Linear Algebra"]["tags"] == ["math", "algebra"]

        outbound = client.get(f"/api/v1/notes/{by_title['Linear Algebra']['id']}/links").json()
        assert outbound["outbound"][0]["target"] == "Eigenvalues"
        assert outbound["outbound"][0]["note_id"] == by_title["Eigenvalues"]["id"]
        assert outbound["outbound"][0]["broken"] is False

        backlinks = client.get(f"/api/v1/notes/{by_title['Eigenvalues']['id']}/links").json()
        assert backlinks["outbound"][0]["target"] == "Linear Algebra"
        assert backlinks["outbound"][1]["target"] == "Missing Note"
        assert backlinks["outbound"][1]["broken"] is True
        assert backlinks["backlinks"][0]["note_id"] == by_title["Linear Algebra"]["id"]

        folders = client.get(f"/api/v1/folders?course_id={course_id}").json()
        assert folders == []


def test_vault_rescan_versions_an_edited_file(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "vault"
    _vault(root)
    with client:
        course_id = _course(client)
        source_id = _source(client, course_id, root)
        client.post(f"/api/v1/sources/{source_id}/scan")
        unchanged = client.post(f"/api/v1/sources/{source_id}/scan").json()
        assert unchanged["stats"]["unchanged"] == 2

        target = root / "Eigenvalues.md"
        target.write_text("# Eigenvalues\n\nRevised: $Av = \\lambda v$.\n", encoding="utf-8")
        updated = client.post(f"/api/v1/sources/{source_id}/scan").json()
        assert updated["stats"]["updated"] == 1

        notes = client.get(f"/api/v1/notes?course_id={course_id}").json()["items"]
        note = next(entry for entry in notes if entry["title"] == "Eigenvalues")
        versions = client.get(f"/api/v1/notes/{note['id']}/versions").json()
        assert len(versions) == 1
        assert versions[0]["cause"] == "source"


def test_vault_export_writes_markdown_with_frontmatter(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "vault"
    _vault(root)
    with client:
        course_id = _course(client)
        source_id = _source(client, course_id, root)
        client.post(f"/api/v1/sources/{source_id}/scan")
        exported = client.get(f"/api/v1/notes/vault.zip?course_id={course_id}")
        assert exported.status_code == 200, exported.text
        assert exported.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            names = set(archive.namelist())
            assert names == {"Linear Algebra.md", "Eigenvalues.md"}
            linear = archive.read("Linear Algebra.md").decode()
            assert linear.startswith("---\ntitle: Linear Algebra\ntags: [math, algebra]")
            assert "[[Eigenvalues]]" in linear


def test_deleting_a_vault_source_keeps_the_notes(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "vault"
    _vault(root)
    with client:
        course_id = _course(client)
        source_id = _source(client, course_id, root)
        client.post(f"/api/v1/sources/{source_id}/scan")
        assert client.delete(f"/api/v1/sources/{source_id}").status_code == 204
        notes = client.get(f"/api/v1/notes?course_id={course_id}").json()["items"]
        assert len(notes) == 2
