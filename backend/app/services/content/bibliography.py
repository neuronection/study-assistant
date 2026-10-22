"""Content-keyed bibliography parsing (plan 85 B, ADR-212).

BibTeX and RIS are content formats, not URLs: the parser registry's URL
matching never sees them. Detection is content-first (a `.bib` filename alone
is not trusted), malformed input raises a typed error instead of importing a
partial bibliography, and every record normalizes to the same shape the
citation columns store.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ...core.vocab import BibliographyFormat, CitationKind

MAX_ENTRIES = 500


class BibliographyError(ValueError):
    pass


@dataclass(frozen=True)
class CitationRecord:
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    doi: str = ""
    container: str = ""
    kind: str = CitationKind.ARTICLE.value
    url: str = ""
    key: str = ""


BIBTEX_TYPES = {
    "article": CitationKind.ARTICLE,
    "book": CitationKind.BOOK,
    "inbook": CitationKind.CHAPTER,
    "incollection": CitationKind.CHAPTER,
    "inproceedings": CitationKind.CONFERENCE,
    "conference": CitationKind.CONFERENCE,
    "proceedings": CitationKind.CONFERENCE,
    "phdthesis": CitationKind.THESIS,
    "mastersthesis": CitationKind.THESIS,
    "techreport": CitationKind.REPORT,
    "dataset": CitationKind.DATASET,
    "online": CitationKind.OTHER,
    "misc": CitationKind.OTHER,
}

RIS_TYPES = {
    "JOUR": CitationKind.ARTICLE,
    "BOOK": CitationKind.BOOK,
    "CHAP": CitationKind.CHAPTER,
    "CONF": CitationKind.CONFERENCE,
    "THES": CitationKind.THESIS,
    "RPRT": CitationKind.REPORT,
    "DATA": CitationKind.DATASET,
    "ELEC": CitationKind.OTHER,
    "GEN": CitationKind.OTHER,
}

RIS_TAG = re.compile(r"^([A-Z][A-Z0-9])  - (.*)$")


def detect_format(filename: str, text: str) -> BibliographyFormat:
    lowered = (filename or "").lower()
    stripped = text.lstrip("\ufeff \t\r\n")
    if stripped.startswith("@") or re.search(r"^@\w+\s*[{(]", text, re.MULTILINE):
        return BibliographyFormat.BIBTEX
    if re.search(r"^TY  - ", text, re.MULTILINE):
        return BibliographyFormat.RIS
    if lowered.endswith(".bib"):
        return BibliographyFormat.BIBTEX
    if lowered.endswith(".ris"):
        return BibliographyFormat.RIS
    raise BibliographyError("unrecognized bibliography format (expected BibTeX or RIS)")


def _clean(value: str) -> str:
    text = value.replace("\u00a0", " ")
    text = re.sub(r"\\([&%$#_])", r"\1", text)
    text = text.replace("{", "").replace("}", "")
    return " ".join(text.split())


def _doi(value: str) -> str:
    text = _clean(value)
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.lower().startswith(prefix):
            return text[len(prefix) :].strip()
    return text


def _year(value: str) -> int | None:
    match = re.search(r"\d{4}", _clean(value))
    return int(match.group(0)) if match else None


def _split_authors(value: str) -> list[str]:
    parts = re.split(r"\s+and\s+", value)
    authors: list[str] = []
    for part in parts:
        name = _clean(part)
        if not name:
            continue
        if "," in name:
            last, _comma, rest = name.partition(",")
            name = f"{rest.strip()} {last.strip()}".strip()
        authors.append(name)
    return authors


def _bibtex_blocks(text: str) -> list[tuple[str, str, str]]:
    blocks: list[tuple[str, str, str]] = []
    index = 0
    while True:
        match = re.search(r"@(\w+)\s*([{(])", text[index:])
        if match is None:
            break
        entry_type = match.group(1).lower()
        open_at = index + match.end() - 1
        opener = text[open_at]
        closer = "}" if opener == "{" else ")"
        depth = 0
        cursor = open_at
        while cursor < len(text):
            char = text[cursor]
            if char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        if depth != 0:
            raise BibliographyError(f"unterminated @{entry_type} entry")
        body = text[open_at + 1 : cursor]
        index = cursor + 1
        if entry_type in ("comment", "preamble", "string"):
            continue
        key, _comma, fields = body.partition(",")
        blocks.append((entry_type, key.strip(), fields))
    return blocks


def _bibtex_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    index = 0
    length = len(body)
    while index < length:
        while index < length and body[index] in " \t\r\n,":
            index += 1
        if index >= length:
            break
        name_start = index
        while index < length and body[index] not in "=, \t\r\n":
            index += 1
        name = body[name_start:index].strip().lower()
        while index < length and body[index] in " \t\r\n":
            index += 1
        if index >= length or body[index] != "=":
            raise BibliographyError(f"malformed BibTeX field '{name or '<unnamed>'}'")
        index += 1
        while index < length and body[index] in " \t\r\n":
            index += 1
        if index >= length:
            raise BibliographyError(f"BibTeX field '{name}' has no value")
        opener = body[index]
        if opener == "{":
            depth = 0
            start = index
            while index < length:
                if body[index] == "{":
                    depth += 1
                elif body[index] == "}":
                    depth -= 1
                    if depth == 0:
                        index += 1
                        break
                index += 1
            if depth != 0:
                raise BibliographyError(f"unterminated value for BibTeX field '{name}'")
            value = body[start + 1 : index - 1]
        elif opener == '"':
            start = index + 1
            index += 1
            while index < length and body[index] != '"':
                index += 1
            if index >= length:
                raise BibliographyError(f"unterminated value for BibTeX field '{name}'")
            value = body[start:index]
            index += 1
        else:
            start = index
            while index < length and body[index] != ",":
                index += 1
            value = body[start:index]
        fields[name] = value
    return fields


def parse_bibtex(text: str) -> list[CitationRecord]:
    records: list[CitationRecord] = []
    for entry_type, key, body in _bibtex_blocks(text):
        fields = _bibtex_fields(body)
        title = _clean(fields.get("title", ""))
        if not title:
            raise BibliographyError(f"BibTeX entry '{key or entry_type}' has no title")
        kind = BIBTEX_TYPES.get(entry_type, CitationKind.OTHER)
        records.append(
            CitationRecord(
                title=title,
                authors=_split_authors(fields.get("author", "")),
                year=_year(fields.get("year", "") or fields.get("date", "")),
                doi=_doi(fields.get("doi", "")),
                container=_clean(
                    fields.get("journal", "")
                    or fields.get("booktitle", "")
                    or fields.get("publisher", "")
                ),
                kind=kind.value,
                url=_clean(fields.get("url", "")),
                key=key,
            )
        )
        if len(records) > MAX_ENTRIES:
            raise BibliographyError(f"bibliography exceeds {MAX_ENTRIES} entries")
    if not records:
        raise BibliographyError("no BibTeX entries found")
    return records


def parse_ris(text: str) -> list[CitationRecord]:
    records: list[CitationRecord] = []
    current: dict[str, list[str]] | None = None
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        match = RIS_TAG.match(line)
        if match is None:
            if current is not None and line.strip():
                current.setdefault("_continuation", []).append(line.strip())
            continue
        tag, value = match.group(1), match.group(2).strip()
        if tag == "TY":
            if current is not None:
                records.append(_ris_record(current))
            current = {"TY": [value]}
            continue
        if current is None:
            continue
        if tag == "ER":
            records.append(_ris_record(current))
            current = None
            continue
        current.setdefault(tag, []).append(value)
    if current is not None:
        records.append(_ris_record(current))
    if not records:
        raise BibliographyError("no RIS records found")
    if len(records) > MAX_ENTRIES:
        raise BibliographyError(f"bibliography exceeds {MAX_ENTRIES} entries")
    return records


def _ris_first(record: dict[str, list[str]], *tags: str) -> str:
    for tag in tags:
        values = record.get(tag)
        if values:
            return values[0]
    return ""


def _ris_record(record: dict[str, list[str]]) -> CitationRecord:
    title = _clean(_ris_first(record, "T1", "TI"))
    if not title:
        raise BibliographyError("RIS record has no title")
    ris_type = _ris_first(record, "TY").upper()
    kind = RIS_TYPES.get(ris_type, CitationKind.OTHER)
    return CitationRecord(
        title=title,
        authors=[_clean(name) for name in record.get("AU", []) if _clean(name)],
        year=_year(_ris_first(record, "PY", "Y1")),
        doi=_doi(_ris_first(record, "DO")),
        container=_clean(_ris_first(record, "JO", "JF", "T2", "BT")),
        kind=kind.value,
        url=_clean(_ris_first(record, "UR")),
    )


def parse_bibliography(text: str, fmt: BibliographyFormat) -> list[CitationRecord]:
    if not text.strip():
        raise BibliographyError("bibliography file is empty")
    if fmt is BibliographyFormat.BIBTEX:
        return parse_bibtex(text)
    return parse_ris(text)
