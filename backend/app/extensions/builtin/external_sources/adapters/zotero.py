"""Zotero local-API adapter: collections -> citation-bearing suggestions (plan 86 E)."""

from __future__ import annotations

import mimetypes
import re
from typing import Any

import httpx

from .....core.vocab import AuthKind, CitationKind, DiscoveryKind
from ....errors import ExtensionError
from .base import ChangeSet, RemoteEntry

API_BASE = "http://127.0.0.1:23119"
TIMEOUT_SEC = 15.0
PAGE_LIMIT = 100

CITATION_KIND_BY_ITEM = {
    "journalArticle": CitationKind.ARTICLE,
    "book": CitationKind.BOOK,
    "bookSection": CitationKind.CHAPTER,
    "conferencePaper": CitationKind.CONFERENCE,
    "preprint": CitationKind.PREPRINT,
    "thesis": CitationKind.THESIS,
    "report": CitationKind.REPORT,
    "dataset": CitationKind.DATASET,
}
ATTACHMENT_TYPES = {"attachment", "note", "annotation"}


def _authors(data: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for creator in data.get("creators") or []:
        if not isinstance(creator, dict):
            continue
        name = str(creator.get("name") or "").strip()
        if not name:
            parts = [
                str(creator.get("firstName") or "").strip(),
                str(creator.get("lastName") or "").strip(),
            ]
            name = " ".join(part for part in parts if part)
        if name:
            names.append(name)
    return names


def _year(date: Any) -> int | None:
    match = re.search(r"(19|20)\d{2}", str(date or ""))
    return int(match.group(0)) if match else None


def _citation_kind(item_type: str) -> str:
    return CITATION_KIND_BY_ITEM.get(item_type, CitationKind.OTHER).value


def _attachment_url(item: dict[str, Any]) -> str | None:
    links = item.get("links")
    if isinstance(links, dict):
        attachment = links.get("attachment")
        if isinstance(attachment, dict):
            href = str(attachment.get("href") or "").strip()
            if href:
                return href
    data = item.get("data")
    if isinstance(data, dict):
        raw = str(data.get("url") or "").strip()
        if raw.startswith(("http://", "https://")):
            return raw
    return None


def _entry_from_item(item: dict[str, Any]) -> RemoteEntry | None:
    data = item.get("data")
    if not isinstance(data, dict):
        return None
    item_type = str(data.get("itemType") or "")
    if item_type in ATTACHMENT_TYPES:
        return None
    key = str(item.get("key") or "").strip()
    if not key:
        return None
    title = str(data.get("title") or "").strip() or key
    doi = str(data.get("DOI") or "").strip() or None
    url = str(data.get("url") or "").strip()
    if doi:
        target = f"https://doi.org/{doi}"
    elif url.startswith(("http://", "https://")):
        target = url
    else:
        target = f"{API_BASE}/api/users/0/items/{key}"
    meta: dict[str, Any] = {
        "remote_id": key,
        "citation_kind": _citation_kind(item_type),
        "authors": _authors(data),
        "material_kind": "link",
    }
    year = _year(data.get("date"))
    if year is not None:
        meta["year"] = year
    if doi:
        meta["doi"] = doi
    container = str(data.get("publicationTitle") or data.get("bookTitle") or "").strip()
    if container:
        meta["container"] = container
    attachment = _attachment_url(item)
    entry_mime = "text/html"
    if attachment:
        meta["attachment_url"] = attachment
        from .base import material_kind_for

        attachment_name = attachment.rsplit("/", 1)[-1].split("?")[0]
        detected = material_kind_for(attachment_name, None)
        if detected:
            meta["material_kind"] = detected
        entry_mime = mimetypes.guess_type(attachment_name)[0] or "application/octet-stream"
    return RemoteEntry(
        remote_id=key,
        name=title,
        url=target,
        mime=entry_mime,
        mtime=None,
        etag=str(item.get("version") or "") or None,
        title=title,
        kind=DiscoveryKind.PAPER.value,
        meta=meta,
    )


class ZoteroAdapter:
    provider_id = "zotero"
    kinds = ("zotero_collection",)
    auth_kind = AuthKind.NONE.value

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(transport=self._transport, timeout=TIMEOUT_SEC)

    def _items(self, source: Any) -> list[dict[str, Any]]:
        options = source.options if isinstance(source.options, dict) else {}
        collection = str(options.get("collection") or "").strip()
        if collection:
            path = f"/api/users/0/collections/{collection}/items"
        else:
            path = "/api/users/0/items"
        with self._client() as client:
            try:
                response = client.get(
                    f"{API_BASE}{path}",
                    params={"limit": str(PAGE_LIMIT), "format": "json"},
                )
            except httpx.HTTPError as error:
                raise ExtensionError(
                    "not-ready", f"Zotero is not reachable on {API_BASE}: {error}"
                ) from error
        if response.status_code >= 400:
            raise ExtensionError(
                "protocol", f"Zotero returned {response.status_code}", status=response.status_code
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise ExtensionError("protocol", "Zotero returned non-JSON") from error
        return (
            [item for item in payload if isinstance(item, dict)]
            if isinstance(payload, list)
            else []
        )

    def list(self, source: Any) -> list[RemoteEntry]:
        entries: list[RemoteEntry] = []
        for item in self._items(source):
            entry = _entry_from_item(item)
            if entry is not None:
                entries.append(entry)
        return entries

    def changes(self, source: Any, cursor: dict[str, Any]) -> ChangeSet:
        known_raw = cursor.get("known")
        known: dict[str, dict[str, Any]] = known_raw if isinstance(known_raw, dict) else {}
        current = {entry.remote_id: entry for entry in self.list(source)}
        upserted = [
            entry
            for remote_id, entry in current.items()
            if known.get(remote_id, {}).get("fingerprint") != entry.fingerprint()
        ]
        vanished = [remote_id for remote_id in known if remote_id not in current]
        next_cursor = {
            "known": {
                remote_id: {
                    "fingerprint": entry.fingerprint(),
                    "title": entry.title,
                    "url": entry.url,
                }
                for remote_id, entry in current.items()
            }
        }
        return ChangeSet(upserted=upserted, vanished=vanished, cursor=next_cursor)

    def fetch(self, source: Any, entry: RemoteEntry) -> bytes:
        attachment = str(entry.meta.get("attachment_url") or "").strip()
        if not attachment:
            raise ExtensionError("not-found", f"Zotero item has no attachment: {entry.name}")
        with self._client() as client:
            try:
                response = client.get(attachment)
            except httpx.HTTPError as error:
                raise ExtensionError("unreachable", f"Zotero attachment failed: {error}") from error
        if response.status_code >= 400:
            raise ExtensionError("not-found", f"Zotero attachment unavailable: {entry.name}")
        return response.content

    def auth_probe(self, source: Any) -> str:
        with self._client() as client:
            try:
                response = client.get(f"{API_BASE}/api/users/0/collections")
            except httpx.HTTPError:
                return "needs-config"
        return "ok" if response.status_code < 500 else "expired"
