"""AnkiConnect adapter: localhost deck reviews for a deterministic union merge (plan 86 E)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from .....core.vocab import AuthKind
from ....errors import ExtensionError
from .base import ChangeSet, RemoteEntry

API_BASE = "http://127.0.0.1:8765"
TIMEOUT_SEC = 15.0
VERSION = 6


def _escape_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


class AnkiAdapter:
    provider_id = "anki"
    kinds = ("anki_deck",)
    auth_kind = AuthKind.NONE.value

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def _call(self, action: str, **params: Any) -> Any:
        body = {"action": action, "version": VERSION, "params": params}
        with httpx.Client(transport=self._transport, timeout=TIMEOUT_SEC) as client:
            try:
                response = client.post(API_BASE, json=body)
            except httpx.HTTPError as error:
                raise ExtensionError(
                    "not-ready", f"AnkiConnect is not reachable on {API_BASE}: {error}"
                ) from error
        if response.status_code >= 400:
            raise ExtensionError(
                "protocol",
                f"AnkiConnect returned {response.status_code}",
                status=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise ExtensionError("protocol", "AnkiConnect returned non-JSON") from error
        if isinstance(payload, dict) and payload.get("error"):
            raise ExtensionError("protocol", str(payload["error"])[:400])
        return payload.get("result") if isinstance(payload, dict) else None

    def decks(self, source: Any) -> list[str]:
        result = self._call("deckNames")
        return [str(deck) for deck in result] if isinstance(result, list) else []

    def configured_decks(self, source: Any) -> list[str]:
        options = source.options if isinstance(source.options, dict) else {}
        raw = options.get("decks")
        if isinstance(raw, list):
            return [str(deck).strip() for deck in raw if str(deck).strip()]
        if isinstance(raw, str) and raw.strip():
            return [part.strip() for part in raw.split(",") if part.strip()]
        return []

    def reviews(self, source: Any) -> list[dict[str, Any]]:
        decks = self.configured_decks(source)
        if not decks:
            raise ExtensionError("needs-config", "select at least one Anki deck")
        options = source.options if isinstance(source.options, dict) else {}
        max_items = int(options.get("max_items") or 200)
        events: list[dict[str, Any]] = []
        for deck in decks:
            card_ids = self._call("findCards", query=f'deck:"{_escape_query(deck)}"')
            if not isinstance(card_ids, list) or not card_ids:
                continue
            ids = card_ids[:max_items]
            payload = self._call("getReviewsOfCards", cards=ids)
            if not isinstance(payload, dict):
                continue
            for card_id, reviews in payload.items():
                if not isinstance(reviews, list):
                    continue
                for review in reviews:
                    if not isinstance(review, dict):
                        continue
                    events.append(
                        {
                            "remote_card_id": str(card_id),
                            "reviewed_at": _reviewed_at(review.get("time")),
                            "rating": _rating(review.get("ease")),
                            "interval_days": float(review.get("ivl") or 0),
                            "elapsed_days": float(review.get("lastIvl") or 0),
                        }
                    )
        events.sort(key=lambda row: (row["reviewed_at"], row["remote_card_id"]))
        return events

    def list(self, source: Any) -> list[RemoteEntry]:
        return []

    def changes(self, source: Any, cursor: dict[str, Any]) -> ChangeSet:
        decks = self.decks(source)
        return ChangeSet(upserted=[], vanished=[], cursor={"decks": decks})

    def fetch(self, source: Any, entry: RemoteEntry) -> bytes:
        raise ExtensionError("unsupported", "Anki decks are review sources, not file sources")

    def auth_probe(self, source: Any) -> str:
        try:
            self._call("version")
        except ExtensionError:
            return "needs-config"
        return "ok"


def _reviewed_at(raw: Any) -> str:
    if isinstance(raw, (int, float)) and raw > 0:
        return datetime.fromtimestamp(float(raw) / 1000.0, tz=UTC).isoformat()
    return datetime.now(UTC).isoformat()


def _rating(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 3
    return value if value in (1, 2, 3, 4) else 3
