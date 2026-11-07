"""Google Drive adapter: changes cursor + Google-native export (plan 86 C)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from .....core.vocab import AuthKind
from ....errors import ExtensionError
from . import oauth_support
from .base import ChangeSet, RemoteEntry

API_BASE = "https://www.googleapis.com/drive/v3"
TIMEOUT_SEC = 45.0
MAX_ITEMS = 100

GOOGLE_NATIVE_EXPORTS = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
    "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
    "application/vnd.google-apps.drawing": ("application/pdf", ".pdf"),
}


def _export_target(mime: str | None) -> tuple[str, str] | None:
    if mime is None:
        return None
    return GOOGLE_NATIVE_EXPORTS.get(mime)


def _entry_from_file(file: dict[str, Any]) -> RemoteEntry | None:
    mime = str(file.get("mimeType") or "") or None
    if mime == "application/vnd.google-apps.folder":
        return None
    name = str(file.get("name") or "").strip()
    file_id = str(file.get("id") or "").strip()
    if not name or not file_id:
        return None
    export = _export_target(mime)
    if export is not None:
        export_mime, suffix = export
        if not name.lower().endswith(suffix):
            name = f"{name}{suffix}"
        return RemoteEntry(
            remote_id=file_id,
            name=name,
            url=f"https://drive.google.com/file/d/{file_id}/view",
            mime=export_mime,
            size=None,
            mtime=str(file.get("modifiedTime") or "") or None,
            etag=str(file.get("version") or "") or None,
            meta={"export_mime": export_mime, "google_native": mime},
        )
    size_raw = file.get("size")
    size = int(size_raw) if isinstance(size_raw, (int, str)) and str(size_raw).isdigit() else None
    return RemoteEntry(
        remote_id=file_id,
        name=name,
        url=f"https://drive.google.com/file/d/{file_id}/view",
        mime=mime,
        size=size,
        mtime=str(file.get("modifiedTime") or "") or None,
        etag=str(file.get("version") or "") or None,
    )


class GoogleDriveAdapter:
    provider_id = "google-drive"
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

    def _folder_query(self, source: Any) -> str:
        options = source.options if isinstance(source.options, dict) else {}
        folder_id = str(options.get("folder_id") or "").strip()
        if folder_id:
            escaped = folder_id.replace("'", "\\'")
            return f"'{escaped}' in parents and trashed = false"
        return "trashed = false"

    def list(self, source: Any) -> list[RemoteEntry]:
        params = {
            "q": self._folder_query(source),
            "pageSize": str(MAX_ITEMS),
            "fields": "files(id,name,mimeType,modifiedTime,size,version)",
        }
        with self._client(source) as client:
            try:
                response = client.get(f"{API_BASE}/files", params=params)
            except httpx.HTTPError as error:
                raise ExtensionError("unreachable", f"Drive is unreachable: {error}") from error
        self._raise_for_status(response)
        payload = response.json()
        entries: list[RemoteEntry] = []
        for file in payload.get("files", []):
            if isinstance(file, dict):
                entry = _entry_from_file(file)
                if entry is not None:
                    entries.append(entry)
        return entries

    def changes(self, source: Any, cursor: dict[str, Any]) -> ChangeSet:
        known_raw = cursor.get("known")
        known: dict[str, dict[str, Any]] = known_raw if isinstance(known_raw, dict) else {}
        page_token = str(cursor.get("page_token") or "")
        with self._client(source) as client:
            if not page_token:
                try:
                    response = client.get(f"{API_BASE}/changes/startPageToken")
                except httpx.HTTPError as error:
                    raise ExtensionError("unreachable", f"Drive is unreachable: {error}") from error
                self._raise_for_status(response)
                start = str(response.json().get("startPageToken") or "")
                if not start:
                    raise ExtensionError("protocol", "Drive returned no start page token")
                initial = self.list(source)
                known_initial = {
                    entry.remote_id: {
                        "name": entry.name,
                        "fingerprint": entry.fingerprint(),
                        "url": entry.url,
                    }
                    for entry in initial
                }
                return ChangeSet(
                    upserted=initial,
                    vanished=[],
                    cursor={"page_token": start, "known": known_initial},
                )
            params = {
                "pageToken": page_token,
                "pageSize": str(MAX_ITEMS),
                "fields": (
                    "nextPageToken,newStartPageToken,"
                    "changes(fileId,removed,file(id,name,mimeType,modifiedTime,size,version))"
                ),
            }
            try:
                response = client.get(f"{API_BASE}/changes", params=params)
            except httpx.HTTPError as error:
                raise ExtensionError("unreachable", f"Drive is unreachable: {error}") from error
        self._raise_for_status(response)
        payload = response.json()
        upserted: list[RemoteEntry] = []
        vanished: list[str] = []
        next_known = dict(known)
        for change in payload.get("changes", []):
            if not isinstance(change, dict):
                continue
            file_id = str(change.get("fileId") or "").strip()
            if not file_id:
                continue
            if change.get("removed"):
                vanished.append(file_id)
                next_known.pop(file_id, None)
                continue
            file = change.get("file")
            if not isinstance(file, dict):
                continue
            entry = _entry_from_file(file)
            if entry is None:
                next_known.pop(file_id, None)
                continue
            upserted.append(entry)
            next_known[file_id] = {
                "name": entry.name,
                "fingerprint": entry.fingerprint(),
                "url": entry.url,
            }
        next_token = str(payload.get("nextPageToken") or payload.get("newStartPageToken") or "")
        next_cursor = {"page_token": next_token or page_token, "known": next_known}
        return ChangeSet(upserted=upserted, vanished=vanished, cursor=next_cursor)

    def fetch(self, source: Any, entry: RemoteEntry) -> bytes:
        export_mime = entry.meta.get("export_mime")
        with self._client(source) as client:
            try:
                if export_mime:
                    response = client.get(
                        f"{API_BASE}/files/{entry.remote_id}/export",
                        params={"mimeType": str(export_mime)},
                    )
                else:
                    response = client.get(
                        f"{API_BASE}/files/{entry.remote_id}",
                        params={"alt": "media"},
                    )
            except httpx.HTTPError as error:
                raise ExtensionError("unreachable", f"Drive is unreachable: {error}") from error
        if response.status_code == 404:
            raise ExtensionError("not-found", f"Drive file vanished: {entry.name}")
        self._raise_for_status(response)
        return response.content

    def put(self, source: Any, name: str, data: bytes) -> str:
        options = source.options if isinstance(source.options, dict) else {}
        folder_id = str(options.get("folder_id") or "").strip()
        metadata: dict[str, Any] = {"name": name}
        if folder_id:
            metadata["parents"] = [folder_id]
        boundary = "sa-backup-boundary"
        body = (
            (
                f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json.dumps(metadata)}\r\n"
                f"--{boundary}\r\nContent-Type: application/zip\r\n\r\n"
            ).encode()
            + data
            + f"\r\n--{boundary}--\r\n".encode()
        )
        with self._client(source) as client:
            try:
                response = client.post(
                    f"{API_BASE}/files",
                    params={"uploadType": "multipart", "fields": "id"},
                    content=body,
                    headers={"Content-Type": f"multipart/related; boundary={boundary}"},
                )
            except httpx.HTTPError as error:
                raise ExtensionError("unreachable", f"Drive is unreachable: {error}") from error
        self._raise_for_status(response)
        return str(response.json().get("id") or name)

    def auth_probe(self, source: Any) -> str:
        return oauth_support.probe(source, self._transport)

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code in (401, 403):
            raise ExtensionError("auth", "Drive rejected the stored OAuth token")
        if response.status_code == 429:
            raise ExtensionError("rate-limited", "Drive rate limit reached", retry_after_ms=5000)
        if response.status_code >= 400:
            raise ExtensionError(
                "protocol", f"Drive returned {response.status_code}", status=response.status_code
            )
