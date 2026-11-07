"""Dropbox adapter: list_folder cursor + download/upload (plan 86 D)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from .....core.vocab import AuthKind
from ....errors import ExtensionError
from . import oauth_support
from .base import ChangeSet, RemoteEntry

API_BASE = "https://api.dropboxapi.com/2"
CONTENT_BASE = "https://content.dropboxapi.com/2"
TIMEOUT_SEC = 45.0


class DropboxAdapter:
    provider_id = "dropbox"
    kinds = ("cloud_folder",)
    auth_kind = AuthKind.OAUTH2.value

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def _client(self, source: Any) -> httpx.Client:
        _config, token = oauth_support.access_token(source, self._transport)
        return httpx.Client(
            transport=self._transport,
            headers=oauth_support.bearer_headers(token),
            timeout=TIMEOUT_SEC,
            follow_redirects=True,
        )

    def _path(self, source: Any) -> str:
        options = source.options if isinstance(source.options, dict) else {}
        path = str(options.get("folder_path") or "").strip()
        if path and not path.startswith("/"):
            return f"/{path}"
        return path

    @staticmethod
    def _entry(row: dict[str, Any]) -> RemoteEntry | None:
        if row.get(".tag") != "file":
            return None
        name = str(row.get("name") or "").strip()
        remote_id = str(row.get("id") or row.get("path_lower") or "").strip()
        if not name or not remote_id:
            return None
        return RemoteEntry(
            remote_id=remote_id,
            name=name,
            url=f"dropbox:{remote_id}",
            mime=None,
            size=int(row["size"]) if isinstance(row.get("size"), int) else None,
            mtime=str(row.get("server_modified") or "") or None,
            etag=str(row.get("rev") or row.get("content_hash") or "") or None,
        )

    def list(self, source: Any) -> list[RemoteEntry]:
        with self._client(source) as client:
            try:
                response = client.post(
                    f"{API_BASE}/files/list_folder",
                    json={"path": self._path(source), "recursive": False},
                )
            except httpx.HTTPError as error:
                raise ExtensionError("unreachable", f"Dropbox is unreachable: {error}") from error
        payload = self._payload(response)
        entries: list[RemoteEntry] = []
        for row in payload.get("entries", []):
            if isinstance(row, dict):
                entry = self._entry(row)
                if entry is not None:
                    entries.append(entry)
        return entries

    def changes(self, source: Any, cursor: dict[str, Any]) -> ChangeSet:
        known_raw = cursor.get("known")
        known: dict[str, dict[str, Any]] = known_raw if isinstance(known_raw, dict) else {}
        saved = str(cursor.get("cursor") or "")
        upserted: list[RemoteEntry] = []
        vanished: list[str] = []
        with self._client(source) as client:
            if saved:
                try:
                    response = client.post(
                        f"{API_BASE}/files/list_folder/continue",
                        json={"cursor": saved},
                    )
                except httpx.HTTPError as error:
                    raise ExtensionError(
                        "unreachable", f"Dropbox is unreachable: {error}"
                    ) from error
            else:
                try:
                    response = client.post(
                        f"{API_BASE}/files/list_folder",
                        json={"path": self._path(source), "recursive": False},
                    )
                except httpx.HTTPError as error:
                    raise ExtensionError(
                        "unreachable", f"Dropbox is unreachable: {error}"
                    ) from error
        payload = self._payload(response)
        rows = payload.get("entries", [])
        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get(".tag") == "deleted":
                remote_id = str(row.get("id") or "").strip()
                if remote_id:
                    vanished.append(remote_id)
                continue
            entry = self._entry(row)
            if entry is not None:
                upserted.append(entry)
        next_known = dict(known)
        for entry in upserted:
            next_known[entry.remote_id] = {"fingerprint": entry.fingerprint(), "name": entry.name}
        for remote_id in vanished:
            next_known.pop(remote_id, None)
        next_cursor = {
            "cursor": str(payload.get("cursor") or saved),
            "known": next_known,
            "has_more": bool(payload.get("has_more")),
        }
        return ChangeSet(
            upserted=upserted,
            vanished=vanished,
            cursor=next_cursor,
            not_modified=not upserted and not vanished,
        )

    def fetch(self, source: Any, entry: RemoteEntry) -> bytes:
        with self._client(source) as client:
            try:
                response = client.post(
                    f"{CONTENT_BASE}/files/download",
                    headers={"Dropbox-API-Arg": json.dumps({"path": entry.remote_id})},
                )
            except httpx.HTTPError as error:
                raise ExtensionError("unreachable", f"Dropbox is unreachable: {error}") from error
        if response.status_code == 404:
            raise ExtensionError("not-found", f"Dropbox file vanished: {entry.name}")
        if response.status_code >= 400:
            raise ExtensionError(
                "protocol", f"Dropbox returned {response.status_code}", status=response.status_code
            )
        return response.content

    def put(self, source: Any, name: str, data: bytes) -> str:
        folder = self._path(source)
        path = f"{folder}/{name}" if folder else f"/{name}"
        with self._client(source) as client:
            try:
                response = client.post(
                    f"{CONTENT_BASE}/files/upload",
                    headers={
                        "Dropbox-API-Arg": json.dumps({"path": path, "mode": "overwrite"}),
                        "Content-Type": "application/octet-stream",
                    },
                    content=data,
                )
            except httpx.HTTPError as error:
                raise ExtensionError("unreachable", f"Dropbox is unreachable: {error}") from error
        self._payload(response)
        return path

    def auth_probe(self, source: Any) -> str:
        return oauth_support.probe(source, self._transport)

    @staticmethod
    def _payload(response: httpx.Response) -> dict[str, Any]:
        if response.status_code in (401, 403):
            raise ExtensionError("auth", "Dropbox rejected the stored OAuth token")
        if response.status_code == 429:
            raise ExtensionError("rate-limited", "Dropbox rate limit reached", retry_after_ms=5000)
        if response.status_code >= 400:
            raise ExtensionError(
                "protocol", f"Dropbox returned {response.status_code}", status=response.status_code
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise ExtensionError("protocol", "Dropbox returned non-JSON") from error
        return payload if isinstance(payload, dict) else {}
