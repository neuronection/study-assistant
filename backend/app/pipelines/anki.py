import hashlib
import io
import json
import re
import sqlite3
import zipfile
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from ..domain.models import Exercise, FsrsState, utcnow
from ..services.study.cards import card_parts, create_card_exercise

CLOZE_RE = re.compile(r"\{\{c\d+::")

MODEL_ID = 1740000000000
DECK_ID = 1
FIELD_SEPARATOR = "\x1f"


@dataclass(frozen=True)
class AnkiImportResult:
    imported: int
    skipped: int
    deck_name: str


def _guid(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def _field_text(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for block in blocks:
        if block.get("md"):
            parts.append(str(block["md"]))
    return "\n".join(parts)


def export_apkg(cards: list[tuple[Exercise, FsrsState | None]], deck_name: str) -> bytes:
    now_ms = int(utcnow().timestamp() * 1000)
    connection = sqlite3.connect(":memory:")
    cursor = connection.cursor()
    cursor.executescript(
        """
        CREATE TABLE col (
            id integer primary key, crt integer not null, mod integer not null,
            scm integer not null, ver integer not null, dty integer not null,
            usn integer not null, ls integer not null, conf text not null,
        models text not null, decks text not null, dconf text not null, tags text not null);
        CREATE TABLE notes (
            id integer primary key, guid integer not null, mid integer not null,
            mod integer not null, usn integer not null, tags text not null,
            flds text not null, sfld integer not null, csum integer not null,
            flags integer not null, data text not null);
        CREATE TABLE cards (
            id integer primary key, nid integer not null, did integer not null,
            ord integer not null, type integer not null, queue integer not null,
            due integer not null, ivl integer not null, factor integer not null,
            reps integer not null, lapses integer not null, left integer not null,
            odue integer not null, odid integer not null, flags integer not null,
            data text not null, usn integer not null default 0);
        CREATE TABLE revlog (
            id integer primary key, cid integer not null, usn integer not null,
            ease integer not null, ivl integer not null, lastIvl integer not null,
            factor integer not null, time integer not null, type integer not null);
        CREATE TABLE graves (usn integer not null, oid integer not null, type integer not null);
        CREATE INDEX ix_notes_usn on notes (usn);
        CREATE INDEX ix_cards_usn on cards (usn);
        CREATE INDEX ix_revlog_usn on revlog (usn);
        CREATE INDEX ix_cards_nid on cards (nid);
        CREATE INDEX ix_revlog_cid on revlog (cid);
        CREATE INDEX ix_cards_due on cards (did, queue, due);
        """
    )
    model = {
        str(MODEL_ID): {
            "id": MODEL_ID,
            "name": "Study Assistant Basic",
            "type": 0,
            "mod": now_ms,
            "usn": 0,
            "sortf": 0,
            "did": DECK_ID,
            "tmpls": [
                {
                    "name": "Card 1",
                    "ord": 0,
                    "qfmt": "{{Front}}",
                    "afmt": "{{FrontSide}}<hr>{{Back}}",
                    "bqfmt": "",
                    "bafmt": "",
                }
            ],
            "flds": [{"name": "Front", "ord": 0}, {"name": "Back", "ord": 1}],
            "req": [[0, "all", [0]]],
            "tags": [],
            "vers": [],
        }
    }
    decks = {
        "1": {
            "id": DECK_ID,
            "name": deck_name,
            "mod": now_ms,
            "usn": 0,
            "lrn": [],
            "collapsed": False,
            "browserCollapsed": False,
            "desc": "",
            "dyn": 0,
            "conf": 1,
            "extendNew": 0,
            "extendRev": 0,
        }
    }
    conf = {
        "activeDecks": [DECK_ID],
        "curDeck": DECK_ID,
        "newSpread": 0,
        "collapseTime": 1200,
        "timeLim": 0,
        "estTimes": True,
        "dueCounts": True,
        "curModel": str(MODEL_ID),
        "nextPos": 1,
        "sortType": "noteFld",
        "sortBackwards": False,
        "addToCur": True,
    }
    dconf = {
        "1": {
            "id": 1,
            "name": "Default",
            "new": [],
            "rev": [],
            "lrn": [],
            "mod": now_ms,
            "usn": 0,
        }
    }
    cursor.execute(
        "INSERT INTO col VALUES (1, ?, ?, ?, 11, 0, 0, 0, ?, ?, ?, ?, '[]')",
        (
            now_ms // 1000,
            now_ms,
            now_ms,
            json.dumps(conf),
            json.dumps(model),
            json.dumps(decks),
            json.dumps(dconf),
        ),
    )
    for index, (card, _state) in enumerate(cards):
        parts = card_parts(card) or {"front": [], "back": []}
        front = _field_text(parts["front"])
        back = _field_text(parts["back"])
        note_id = index + 1
        card_id = index + 1
        cursor.execute(
            "INSERT INTO notes VALUES (?, ?, ?, ?, 0, '', ?, ?, ?, 0, '')",
            (
                note_id,
                int(_guid(f"{card.id}:{front}"), 16),
                MODEL_ID,
                now_ms,
                f"{front}{FIELD_SEPARATOR}{back}",
                0,
                int(hashlib.sha1(front.encode("utf-8")).hexdigest()[:8], 16),
            ),
        )
        cursor.execute(
            "INSERT INTO cards VALUES (?, ?, ?, 0, 2, 1, 0, 0, 2500, 0, 0, 0, 0, 0, 0, '', 0)",
            (card_id, note_id, DECK_ID),
        )
    package = io.BytesIO()
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("collection.anki2", _connection_bytes(connection))
        archive.writestr("media", "{}")
    return package.getvalue()


def _connection_bytes(connection: sqlite3.Connection) -> bytes:
    connection.commit()
    result = connection.serialize()
    connection.close()
    if isinstance(result, bytes):
        return result
    return bytes(result)


def _deck_name(connection: sqlite3.Connection) -> str:
    try:
        row = connection.execute("SELECT decks FROM col").fetchone()
        if row:
            decks = json.loads(row[0])
            for deck in decks.values():
                if deck.get("id") != 1 and deck.get("name"):
                    return str(deck["name"])
    except (sqlite3.DatabaseError, ValueError, AttributeError):
        return "Imported deck"
    return "Imported deck"


def import_apkg(
    data: bytes, session: Session, profile_id: int, course_id: int
) -> AnkiImportResult:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            db_name = next(
                (name for name in ("collection.anki21", "collection.anki2") if name in names),
                None,
            )
            if db_name is None:
                raise ValueError("not an .apkg file (no collection database)")
            raw = archive.read(db_name)
    except zipfile.BadZipFile as error:
        raise ValueError("not an .apkg file (unreadable zip)") from error
    memory = sqlite3.connect(":memory:")
    memory.deserialize(raw)
    deck_name = "Imported deck"
    try:
        deck_name = _deck_name(memory)
        rows = memory.execute("SELECT flds, tags FROM notes").fetchall()
    except sqlite3.DatabaseError as error:
        raise ValueError("unreadable Anki collection") from error

    imported = 0
    skipped = 0
    for flds, _tags in rows:
        fields = flds.split(FIELD_SEPARATOR)
        if len(fields) < 2:
            skipped += 1
            continue
        front = fields[0].strip()
        back = fields[1].strip()
        if not front or not back:
            skipped += 1
            continue
        kind = "cloze" if CLOZE_RE.search(front) else "basic"
        create_card_exercise(
            session,
            profile_id=profile_id,
            course_id=course_id,
            node_id=None,
            kind=kind,
            front=[{"type": "text", "md": front}],
            back=[{"type": "text", "md": back}],
            source="anki_import",
            source_ref=deck_name,
            deck_ref=deck_name,
        )
        imported += 1
    memory.close()
    if imported:
        session.flush()
    return AnkiImportResult(imported=imported, skipped=skipped, deck_name=deck_name)
