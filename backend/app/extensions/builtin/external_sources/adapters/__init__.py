"""Adapter registry: catalog provider id -> adapter class (plan 86 A)."""

from __future__ import annotations

from typing import Any

import httpx

from ....errors import ExtensionError
from .anki import AnkiAdapter
from .dropbox import DropboxAdapter
from .google_drive import GoogleDriveAdapter
from .onedrive import OneDriveAdapter
from .webdav import WebDavAdapter
from .zotero import ZoteroAdapter

ADAPTERS: dict[str, type] = {
    "webdav": WebDavAdapter,
    "google-drive": GoogleDriveAdapter,
    "dropbox": DropboxAdapter,
    "onedrive": OneDriveAdapter,
    "zotero": ZoteroAdapter,
    "anki": AnkiAdapter,
}


def build_adapter(provider_id: str, transport: httpx.BaseTransport | None = None) -> Any:
    adapter = ADAPTERS.get(provider_id)
    if adapter is None:
        raise ExtensionError("invalid", f"no adapter registered for provider '{provider_id}'")
    return adapter(transport=transport)


def adapter_provider_ids() -> tuple[str, ...]:
    return tuple(ADAPTERS)
