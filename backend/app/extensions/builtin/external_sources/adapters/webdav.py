"""WebDAV (Nextcloud-first) adapter: PROPFIND/ETag reconciliation (plan 86 C)."""

from __future__ import annotations

import posixpath
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from .....core import secrets as secret_store
from .....core.vocab import AuthKind
from ....errors import ExtensionError
from .base import ChangeSet, RemoteEntry

PROPFIND_BODY = b"""<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:">
  <d:prop>
    <d:displayname/>
    <d:getcontenttype/>
    <d:getcontentlength/>
    <d:getlastmodified/>
    <d:getetag/>
  </d:prop>
</d:propfind>"""

TIMEOUT_SEC = 30.0


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _prop_node(node: ET.Element) -> ET.Element | None:
    for child in node:
        if _localname(child.tag) != "propstat":
            continue
        for prop in child:
            if _localname(prop.tag) == "prop":
                return prop
    return None


def _direct_text(node: ET.Element, name: str) -> str | None:
    for child in node:
        if _localname(child.tag) == name:
            return (child.text or "").strip() or None
    return None


def _child_text(node: ET.Element, name: str) -> str | None:
    prop = _prop_node(node)
    if prop is None:
        return None
    for child in prop:
        if _localname(child.tag) == name:
            return (child.text or "").strip() or None
    return None


def _is_collection(node: ET.Element) -> bool:
    prop = _prop_node(node)
    if prop is None:
        return False
    for child in prop:
        if _localname(child.tag) == "resourcetype":
            return any(_localname(grand.tag) == "collection" for grand in child)
    return False


def _split_href(href: str) -> tuple[str, str, str] | None:
    parsed = urlparse(href)
    path = unquote(parsed.path or "")
    if not path:
        return None
    cleaned = path.rstrip("/")
    if not cleaned:
        return None
    name = posixpath.basename(cleaned)
    parent = posixpath.dirname(cleaned)
    return name, parent, cleaned


class WebDavAdapter:
    provider_id = "webdav"
    kinds = ("webdav_folder",)
    auth_kind = AuthKind.TOKEN.value

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def _base_url(self, source: Any) -> str:
        raw = (source.url or "").strip()
        parsed = urlparse(raw)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ExtensionError("invalid", "WebDAV expects an http(s) folder URL")
        return raw if raw.endswith("/") else f"{raw}/"

    def _auth(self, source: Any) -> tuple[str, str]:
        options = source.options if isinstance(source.options, dict) else {}
        username = str(options.get("username") or "").strip()
        password = secret_store.get_secret(f"source:{source.id}:password")
        if not username or not password:
            raise ExtensionError(
                "needs-secret",
                "WebDAV needs a username and an app password stored in the keyring",
            )
        return username, password

    def _client(self, source: Any) -> httpx.Client:
        username, password = self._auth(source)
        return httpx.Client(
            transport=self._transport,
            auth=(username, password),
            timeout=TIMEOUT_SEC,
            follow_redirects=True,
        )

    def _propfind(self, source: Any) -> list[RemoteEntry]:
        base = self._base_url(source)
        with self._client(source) as client:
            try:
                response = client.request(
                    "PROPFIND",
                    base,
                    content=PROPFIND_BODY,
                    headers={"Depth": "1", "Content-Type": "application/xml"},
                )
            except httpx.HTTPError as error:
                raise ExtensionError("unreachable", f"WebDAV is unreachable: {error}") from error
        if response.status_code in (401, 403):
            raise ExtensionError("auth", "WebDAV rejected the stored credentials")
        if response.status_code >= 400:
            raise ExtensionError(
                "protocol", f"PROPFIND returned {response.status_code}", status=response.status_code
            )
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as error:
            raise ExtensionError("protocol", "WebDAV returned malformed XML") from error
        parsed_base = urlparse(base)
        base_path = unquote(parsed_base.path or "").rstrip("/")
        entries: list[RemoteEntry] = []
        for node in root:
            if _localname(node.tag) != "response":
                continue
            href = _direct_text(node, "href")
            if not href:
                continue
            parts = _split_href(href)
            if parts is None:
                continue
            name, parent, path = parts
            if path == base_path:
                continue
            if parent != base_path:
                continue
            content_type = _child_text(node, "getcontenttype")
            if _is_collection(node) or (
                content_type and content_type.lower().startswith("httpd/unix-directory")
            ):
                continue
            length_raw = _child_text(node, "getcontentlength")
            size = int(length_raw) if length_raw and length_raw.isdigit() else None
            remote_id = f"{parsed_base.scheme}://{parsed_base.netloc}{path}"
            entries.append(
                RemoteEntry(
                    remote_id=remote_id,
                    name=name,
                    url=remote_id,
                    mime=content_type,
                    size=size,
                    mtime=_child_text(node, "getlastmodified"),
                    etag=_child_text(node, "getetag"),
                )
            )
        return entries

    def list(self, source: Any) -> list[RemoteEntry]:
        return self._propfind(source)

    def changes(self, source: Any, cursor: dict[str, Any]) -> ChangeSet:
        known_raw = cursor.get("entries")
        known: dict[str, dict[str, Any]] = known_raw if isinstance(known_raw, dict) else {}
        current = {entry.remote_id: entry for entry in self._propfind(source)}
        upserted: list[RemoteEntry] = []
        for remote_id, entry in current.items():
            prior = known.get(remote_id)
            if prior is None or prior.get("fingerprint") != entry.fingerprint():
                upserted.append(entry)
        vanished = [remote_id for remote_id in known if remote_id not in current]
        next_cursor = {
            "entries": {
                remote_id: {"fingerprint": entry.fingerprint(), "name": entry.name}
                for remote_id, entry in current.items()
            }
        }
        return ChangeSet(
            upserted=upserted,
            vanished=vanished,
            cursor=next_cursor,
            not_modified=False,
        )

    def fetch(self, source: Any, entry: RemoteEntry) -> bytes:
        with self._client(source) as client:
            try:
                response = client.get(entry.url)
            except httpx.HTTPError as error:
                raise ExtensionError("unreachable", f"WebDAV is unreachable: {error}") from error
        if response.status_code == 404:
            raise ExtensionError("not-found", f"WebDAV entry vanished: {entry.name}")
        if response.status_code >= 400:
            raise ExtensionError(
                "protocol", f"GET returned {response.status_code}", status=response.status_code
            )
        return response.content

    def put(self, source: Any, name: str, data: bytes) -> str:
        base = self._base_url(source)
        target = f"{base}{posixpath.basename(name)}"
        with self._client(source) as client:
            try:
                response = client.put(
                    target,
                    content=data,
                    headers={"Content-Type": "application/zip"},
                )
            except httpx.HTTPError as error:
                raise ExtensionError("unreachable", f"WebDAV is unreachable: {error}") from error
        if response.status_code >= 400:
            raise ExtensionError(
                "protocol", f"PUT returned {response.status_code}", status=response.status_code
            )
        return target

    def auth_probe(self, source: Any) -> str:
        try:
            self._auth(source)
        except ExtensionError:
            return "needs-config"
        try:
            with self._client(source) as client:
                response = client.request(
                    "PROPFIND",
                    self._base_url(source),
                    content=PROPFIND_BODY,
                    headers={"Depth": "0", "Content-Type": "application/xml"},
                )
        except (httpx.HTTPError, ExtensionError):
            return "needs-config"
        if response.status_code in (401, 403):
            return "expired"
        return "ok"
