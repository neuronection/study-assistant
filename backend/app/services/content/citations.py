"""Citation import/export and deterministic formatting (plan 85 B, ADR-212).

A bibliography entry lands as a link material: the URL is the DOI resolver
when a DOI exists, otherwise the entry's own URL. Dedupe is DOI-first, then
normalized URL, both scoped to the course. Export is the inverse of the same
columns — one style, no CSL engine.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from typing import Any, cast
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.urls import normalize_url
from ...core.vocab import BibliographyFormat, CitationKind, MaterialKind
from ...domain.models import Course, Material, MaterialLink, MaterialSuggestion
from ...domain.payloads import AuthorList, CitationAuthor
from ...parsers.base import build_content_registry, resolve_content_parser
from ..knowledge.tree import TreeError, TreeService
from .bibliography import BibliographyError, CitationRecord, detect_format
from .materials import MaterialsService


class CitationError(ValueError):
    pass


@dataclass
class BibliographyImportReport:
    created: int = 0
    deduped: int = 0
    skipped: list[str] = field(default_factory=list)
    material_ids: list[str] = field(default_factory=list)


def doi_url(doi: str) -> str:
    return f"https://doi.org/{quote(doi, safe='/')}" if doi else ""


def citation_fields(record: CitationRecord) -> dict[str, Any]:
    return {
        "citation_title": record.title[:500],
        "citation_authors": cast(
            AuthorList,
            [cast(CitationAuthor, {"name": name[:200]}) for name in record.authors[:50] if name],
        ),
        "citation_year": record.year,
        "citation_doi": record.doi[:255] or None,
        "citation_container": record.container[:300] or None,
        "citation_kind": record.kind,
    }


def citation_fields_from_meta(meta: Any) -> dict[str, Any]:
    if not isinstance(meta, dict):
        return {}
    fields: dict[str, Any] = {}
    doi = str(meta.get("doi") or "").strip()
    if doi:
        fields["citation_doi"] = doi[:255]
    authors = meta.get("authors")
    if isinstance(authors, list):
        cleaned = [str(name).strip() for name in authors if str(name).strip()]
        if cleaned:
            fields["citation_authors"] = cast(
                AuthorList,
                [cast(CitationAuthor, {"name": name[:200]}) for name in cleaned[:50]],
            )
    year = meta.get("year")
    if isinstance(year, int) and 1000 <= year <= 3000:
        fields["citation_year"] = year
    container = str(meta.get("container") or "").strip()
    if container:
        fields["citation_container"] = container[:300]
    kind = str(meta.get("citation_kind") or "").strip()
    if kind:
        with contextlib.suppress(ValueError):
            fields["citation_kind"] = CitationKind(kind).value
    return fields


def apply_citation(material: Material, fields: dict[str, Any]) -> None:
    for key, value in fields.items():
        setattr(material, key, value)


def _author_last(name: str) -> str:
    cleaned = name.strip()
    if "," in cleaned:
        return cleaned.split(",", 1)[0].strip()
    return cleaned.split()[-1] if cleaned.split() else cleaned


def citation_text(material: Material) -> str | None:
    title = (material.citation_title or "").strip()
    if not title:
        return None
    authors = material.citation_authors or []
    names = [_author_last(str(entry.get("name", ""))) for entry in authors if entry.get("name")]
    names = [name for name in names if name]
    if len(names) == 1:
        author = names[0]
    elif len(names) == 2:
        author = f"{names[0]} & {names[1]}"
    elif len(names) > 2:
        author = f"{names[0]} et al."
    else:
        author = ""
    year = str(material.citation_year) if material.citation_year else "n.d."
    if author:
        return f"{author} ({year}) — {title}"
    return f"{title} ({year})"


def _lookup_existing(
    session: Session, profile_id: str, course_id: str, doi: str, url_norm: str
) -> Material | None:
    if doi:
        row = session.scalars(
            select(Material).where(
                Material.profile_id == profile_id,
                Material.course_id == course_id,
                Material.citation_doi == doi,
            )
        ).first()
        if row is not None:
            return row
    if url_norm:
        return session.scalars(
            select(Material).where(
                Material.profile_id == profile_id,
                Material.course_id == course_id,
                Material.kind == MaterialKind.LINK.value,
                Material.source_url_norm == url_norm,
            )
        ).first()
    return None


def import_bibliography(
    session: Session,
    service: MaterialsService,
    *,
    profile_id: str,
    course_id: str,
    filename: str,
    data: bytes,
    node_id: str | None = None,
) -> BibliographyImportReport:
    course = session.get(Course, course_id)
    if course is None or course.profile_id != profile_id:
        raise CitationError("course not found")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise BibliographyError("bibliography must be UTF-8 text") from error
    fmt: BibliographyFormat = detect_format(filename, text)
    parser = resolve_content_parser(build_content_registry(), filename, text)
    if parser is None:
        raise BibliographyError("unrecognized bibliography format (expected BibTeX or RIS)")
    records = cast(list[CitationRecord], parser.parse(text))
    placement = None
    if node_id is not None:
        try:
            placement = TreeService(session).placement_node(course_id, node_id)
        except TreeError as error:
            raise CitationError(str(error)) from error
    report = BibliographyImportReport()
    for record in records:
        url = doi_url(record.doi) or record.url
        if not url:
            report.skipped.append(f"{record.title}: no DOI or URL")
            continue
        url_norm = normalize_url(url)
        existing = _lookup_existing(session, profile_id, course_id, record.doi, url_norm)
        fields = citation_fields(record)
        if existing is not None:
            apply_citation(existing, fields)
            report.deduped += 1
            report.material_ids.append(existing.id)
            continue
        material, _deduped = service.create_link(
            profile_id=profile_id,
            course_id=course_id,
            url=url,
            title=record.title,
        )
        apply_citation(material, fields)
        provenance = dict(material.provenance or {})
        provenance.update({"source": fmt.value, "citation_key": record.key})
        material.provenance = cast(Any, provenance)
        if placement is not None:
            session.add(
                MaterialLink(
                    course_id=course_id,
                    node_id=placement,
                    material_id=material.id,
                    rationale=f"{fmt.value} import",
                )
            )
        report.created += 1
        report.material_ids.append(material.id)
    session.flush()
    return report


def attach_suggestion_citation(
    session: Session, profile_id: str, material: Material, url_norm: str
) -> None:
    suggestion = session.scalars(
        select(MaterialSuggestion).where(
            MaterialSuggestion.profile_id == profile_id,
            MaterialSuggestion.url_norm == url_norm,
        )
    ).first()
    if suggestion is None:
        return
    fields = citation_fields_from_meta(suggestion.meta)
    if not fields:
        return
    apply_citation(material, fields)
    if material.citation_title is None:
        material.citation_title = material.title[:500]


BIBTEX_TYPES = {
    CitationKind.ARTICLE: "article",
    CitationKind.BOOK: "book",
    CitationKind.CHAPTER: "incollection",
    CitationKind.CONFERENCE: "inproceedings",
    CitationKind.PREPRINT: "misc",
    CitationKind.THESIS: "phdthesis",
    CitationKind.REPORT: "techreport",
    CitationKind.DATASET: "misc",
    CitationKind.OTHER: "misc",
}


def _bib_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _bib_key(material: Material, used: set[str]) -> str:
    authors = material.citation_authors or []
    first = _author_last(str(authors[0].get("name", ""))) if authors else ""
    title_word = ""
    title = (material.citation_title or material.title or "").strip()
    for word in re.findall(r"[A-Za-z0-9]+", title):
        title_word = word
        break
    base = re.sub(r"[^a-z0-9]", "", f"{first}{material.citation_year or ''}{title_word}".lower())
    key = base or "citation"
    suffix = 1
    while key in used:
        suffix += 1
        key = f"{base or 'citation'}{suffix}"
    used.add(key)
    return key


def export_bibtex(materials: list[Material]) -> str:
    used: set[str] = set()
    lines: list[str] = []
    for material in materials:
        title = (material.citation_title or material.title or "").strip()
        if not title:
            continue
        kind = CitationKind(material.citation_kind or CitationKind.OTHER.value)
        entry_type = BIBTEX_TYPES.get(kind, "misc")
        key = _bib_key(material, used)
        authors = [str(entry.get("name", "")).strip() for entry in material.citation_authors or []]
        authors = [name for name in authors if name]
        fields: list[tuple[str, str]] = [("title", title)]
        if authors:
            fields.insert(0, ("author", " and ".join(authors)))
        if material.citation_year:
            fields.append(("year", str(material.citation_year)))
        if material.citation_container:
            field = "journal" if kind is CitationKind.ARTICLE else "booktitle"
            fields.append((field, material.citation_container))
        if material.citation_doi:
            fields.append(("doi", material.citation_doi))
        if material.source_url:
            fields.append(("url", material.source_url))
        body = ",\n".join(f"  {name} = {{{_bib_escape(value)}}}" for name, value in fields)
        lines.append(f"@{entry_type}{{{key},\n{body}\n}}\n")
    return "\n".join(lines)
