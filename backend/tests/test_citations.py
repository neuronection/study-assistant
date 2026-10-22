"""Bibliography parsing, import/dedupe, export and citation rendering (plan 85 B)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.services.content.bibliography import (
    BibliographyError,
    detect_format,
    parse_bibtex,
    parse_ris,
)

BIBTEX = """
@article{lovelace2024,
  author = {Lovelace, Ada and Turing, Alan},
  title = {Gradient descent convergence under interpolation},
  journal = {Journal of Optimization},
  year = {2024},
  doi = {10.1000/abc.123},
  url = {https://example.org/paper}
}

@book{hopper2022,
  author = {Grace Hopper},
  title = {Compilers and Control},
  publisher = {Navy Press},
  year = {2022},
  doi = {10.1000/book.9}
}
"""

RIS = """
TY  - JOUR
AU  - Ada Lovelace
AU  - Alan Turing
T1  - Gradient descent convergence
PY  - 2024
DO  - 10.1000/ris.1
JO  - Optimization Letters
UR  - https://example.org/ris
ER  -
"""


def _course(client: TestClient) -> str:
    response = client.post("/api/v1/courses", json={"title": "Calculus"})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _import(client: TestClient, course_id: str, text: str, filename: str) -> Any:
    return client.post(
        f"/api/v1/materials/import-bibliography?course_id={course_id}",
        files={"file": (filename, text.encode(), "text/plain")},
    )


def test_detect_format_is_content_first() -> None:
    assert detect_format("notes.txt", BIBTEX).value == "bibtex"
    assert detect_format("notes.bib", RIS).value == "ris"
    with pytest.raises(BibliographyError, match="unrecognized"):
        detect_format("notes.txt", "plain text")


def test_parse_bibtex_normalizes_fields() -> None:
    records = parse_bibtex(BIBTEX)
    assert len(records) == 2
    first = records[0]
    assert first.title == "Gradient descent convergence under interpolation"
    assert first.authors == ["Ada Lovelace", "Alan Turing"]
    assert first.year == 2024
    assert first.doi == "10.1000/abc.123"
    assert first.container == "Journal of Optimization"
    assert first.kind == "article"
    assert records[1].kind == "book"
    assert records[1].container == "Navy Press"


def test_parse_ris_normalizes_fields() -> None:
    records = parse_ris(RIS)
    assert len(records) == 1
    assert records[0].title == "Gradient descent convergence"
    assert records[0].authors == ["Ada Lovelace", "Alan Turing"]
    assert records[0].doi == "10.1000/ris.1"
    assert records[0].container == "Optimization Letters"


def test_malformed_bibliography_is_a_typed_error() -> None:
    with pytest.raises(BibliographyError, match="unterminated"):
        parse_bibtex("@article{x, title = {never closed")
    with pytest.raises(BibliographyError, match="no title"):
        parse_bibtex("@article{x, author = {A. Author}}")
    with pytest.raises(BibliographyError, match="no RIS"):
        parse_ris("not a ris file")


def test_import_creates_dedupes_and_round_trips(client: TestClient) -> None:
    with client:
        course_id = _course(client)
        first = _import(client, course_id, BIBTEX, "library.bib")
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["created"] == 2
        assert body["deduped"] == 0
        assert len(body["materials"]) == 2
        paper = next(row for row in body["materials"] if "gradient" in row["title"].lower())
        assert paper["citation_doi"] == "10.1000/abc.123"
        assert paper["citation_year"] == 2024
        assert paper["citation_authors"][0]["name"] == "Ada Lovelace"
        assert (
            paper["citation_text"]
            == "Lovelace & Turing (2024) — Gradient descent convergence under interpolation"
        )

        again = _import(client, course_id, BIBTEX, "library.bib").json()
        assert again["created"] == 0
        assert again["deduped"] == 2

        ids = [row["id"] for row in body["materials"]]
        exported = client.get(
            "/api/v1/materials/bibliography.bib",
            params=[("ids", material_id) for material_id in ids],
        )
        assert exported.status_code == 200, exported.text
        assert exported.headers["content-type"].startswith("application/x-bibtex")
        records = parse_bibtex(exported.text)
        assert {record.doi for record in records} == {"10.1000/abc.123", "10.1000/book.9"}


def test_import_rejects_malformed_and_empty_files(client: TestClient) -> None:
    with client:
        course_id = _course(client)
        malformed = _import(client, course_id, "@article{x, title = {broken", "bad.bib")
        assert malformed.status_code == 422
        assert "unterminated" in malformed.json()["detail"]
        empty = _import(client, course_id, "", "empty.bib")
        assert empty.status_code == 422


def test_thirty_entry_bibliography_imports_and_exports(client: TestClient) -> None:
    entries = []
    for index in range(30):
        entries.append(
            "@article{paper"
            f"{index}, author = {{Author {index}}}, title = {{Study {index}}}, "
            f"journal = {{Journal {index}}}, year = {{2020}}, "
            f"doi = {{10.5555/paper.{index}}}}}"
        )
    text = "\n\n".join(entries)
    with client:
        course_id = _course(client)
        response = _import(client, course_id, text, "thirty.bib")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["created"] == 30
        assert len(body["materials"]) == 30
        exported = client.get(
            "/api/v1/materials/bibliography.bib",
            params=[("ids", row["id"]) for row in body["materials"]],
        )
        records = parse_bibtex(exported.text)
        assert len(records) == 30
        assert len({record.doi for record in records}) == 30


def test_doi_dedupe_wins_over_a_different_url(client: TestClient) -> None:
    with client:
        course_id = _course(client)
        first = _import(client, course_id, BIBTEX, "library.bib").json()
        assert first["created"] == 2
        changed = BIBTEX.replace("https://example.org/paper", "https://mirror.example/x")
        second = _import(client, course_id, changed, "library.bib").json()
        assert second["created"] == 0
        assert second["deduped"] == 2


def test_saved_scholar_suggestion_fills_link_citation(client: TestClient) -> None:
    with client:
        course_id = _course(client)
        saved = client.post(
            "/api/v1/discovery/suggestions",
            json={
                "provider": "openalex",
                "url": "https://doi.org/10.1000/scholar.1",
                "title": "A discovered paper",
                "kind": "paper",
                "meta": {
                    "doi": "10.1000/scholar.1",
                    "authors": ["Ada Lovelace"],
                    "year": 2024,
                    "container": "Optimization Letters",
                    "citation_kind": "article",
                },
            },
        )
        assert saved.status_code == 200, saved.text
        created = client.post(
            "/api/v1/materials/link",
            json={
                "course_id": course_id,
                "url": "https://doi.org/10.1000/scholar.1",
                "title": "A discovered paper",
            },
        )
        assert created.status_code == 200, created.text
        material = created.json()["material"]
        assert material["citation_doi"] == "10.1000/scholar.1"
        assert material["citation_year"] == 2024
        assert material["citation_text"] == "Lovelace (2024) — A discovered paper"
