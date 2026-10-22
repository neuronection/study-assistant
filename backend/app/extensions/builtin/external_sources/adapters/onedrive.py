"""OneDrive (Microsoft Graph) adapter: delta cursor + download/upload (plan 86 D)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from .....core.vocab import AuthKind
from ....errors import ExtensionError
from . import oauth_support
from .base import ChangeSet, RemoteEntry

API_BASE = "https://graph.microsoft.com/v1.0"
TIMEOUT_SEC = 45.0


class OneDriveAdapter:
    provider_id = "onedrive"
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

    def _folder(self, source: Any) -> str:
        options = source.options if isinstance(source.options, dict) else {}
        return str(options.get("folder_path") or "").strip().strip("/")

    def _delta_url(self, source: Any) -> str:
        folder = self._folder(source)
        if folder:
            return f"{API_BASE}/me/drive/root:/{quote(folder)}:/delta"
        return f"{API_BASE}/me/drive/root/delta"

    @staticmethod
    def _entry(row: dict[str, Any]) -> RemoteEntry | None:
        if not isinstance(row.get("file"), dict):
            return None
        name = str(row.get("name") or "").strip()
        remote_id = str(row.get("id") or "").strip()
        if not name or not remote_id:
            return None
        size_raw = row.get("size")
        size = int(size_raw) if isinstance(size_raw, int) else None
        raw_file = row.get("file")
        file_info: dict[str, Any] = raw_file if isinstance(raw_file, dict) else {}
        return RemoteEntry(
            remote_id=remote_id,
            name=name,
            url=str(row.get("@microsoft.graph.downloadUrl") or f"onedrive:{remote_id}"),
            mime=str(file_info.get("mimeType") or "") or None,
            size=size,
            mtime=str(row.get("lastModifiedDateTime") or "") or None,
            etag=str(row.get("eTag") or row.get("cTag") or "") or None,
        )

    def _delta(self, source: Any, url: str) -> dict[str, Any]:
        with self._client(source) as client:
            try:
                response = client.get(url)
            except httpx.HTTPError as error:
                raise ExtensionError("unreachable", f"OneDrive is unreachable: {error}") from error
        if response.status_code in (401, 403):
            raise ExtensionError("auth", "OneDrive rejected the stored OAuth token")
        if response.status_code == 410:
            raise ExtensionError("protocol", "OneDrive delta cursor expired; rescan")
        if response.status_code >= 400:
            raise ExtensionError(
                "protocol", f"OneDrive returned {response.status_code}", status=response.status_code
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise ExtensionError("protocol", "OneDrive returned non-JSON") from error
        return payload if isinstance(payload, dict) else {}

    def list(self, source: Any) -> list[RemoteEntry]:
        payload = self._delta(source, self._delta_url(source))
        entries: list[RemoteEntry] = []
        for row in payload.get("value", []):
            if isinstance(row, dict):
                entry = self._entry(row)
                if entry is not None:
                    entries.append(entry)
        return entries

    def changes(self, source: Any, cursor: dict[str, Any]) -> ChangeSet:
        known_raw = cursor.get("known")
        known: dict[str, dict[str, Any]] = known_raw if isinstance(known_raw, dict) else {}
        url = str(cursor.get("delta_link") or "") or self._delta_url(source)
        payload = self._delta(source, url)
        upserted: list[RemoteEntry] = []
        vanished: list[str] = []
        next_known = dict(known)
        for row in payload.get("value", []):
            if not isinstance(row, dict):
                continue
            remote_id = str(row.get("id") or "").strip()
            if row.get("deleted") is not None:
                if remote_id:
                    vanished.append(remote_id)
                    next_known.pop(remote_id, None)
                continue
            entry = self._entry(row)
            if entry is None:
                continue
            upserted.append(entry)
            next_known[remote_id] = {"fingerprint": entry.fingerprint(), "name": entry.name}
        next_cursor = {
            "delta_link": str(payload.get("@odata.deltaLink") or url),
            "known": next_known,
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
                response = client.get(f"{API_BASE}/me/drive/items/{entry.remote_id}/content")
            except httpx.HTTPError as error:
                raise ExtensionError("unreachable", f"OneDrive is unreachable: {error}") from error
        if response.status_code == 404:
            raise ExtensionError("not-found", f"OneDrive file vanished: {entry.name}")
        if response.status_code >= 400:
            raise ExtensionError(
                "protocol", f"OneDrive returned {response.status_code}", status=response.status_code
            )
        return response.content

    def put(self, source: Any, name: str, data: bytes) -> str:
        folder = self._folder(source)
        path = f"{folder}/{name}" if folder else name
        with self._client(source) as client:
            try:
                response = client.put(
                    f"{API_BASE}/me/drive/root:/{quote(path)}:/content",
                    content=data,
                    headers={"Content-Type": "application/zip"},
                )
            except httpx.HTTPError as error:
                raise ExtensionError("unreachable", f"OneDrive is unreachable: {error}") from error
        if response.status_code >= 400:
            raise ExtensionError(
                "protocol", f"OneDrive returned {response.status_code}", status=response.status_code
            )
        return path

    def auth_probe(self, source: Any) -> str:
        return oauth_support.probe(source, self._transport)
