import base64
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import DateTime, delete, select
from sqlalchemy.orm import Session

from ...domain.models import (
    Activity,
    Answer,
    Attempt,
    ChatMessage,
    ChatProposal,
    ChatProposalAnchor,
    ChatSession,
    Chunk,
    DeletedItem,
    Exercise,
    ExerciseSession,
    ExerciseStep,
    Extraction,
    FsrsState,
    ItemStat,
    Material,
    MaterialDrawing,
    MaterialImage,
    MaterialIndexCard,
    MaterialLink,
    MaterialStudyState,
    Mistake,
    Note,
    NoteDrawing,
    NoteVersion,
    Question,
    QuizHelpEvent,
    ReviewLog,
    StepAttempt,
    TreeNode,
    utcnow,
)
from ...services.retrieval.chunk_profile import chunk_texts_for_space
from ...storage.fts import sync_material_fts

TRASH_TTL_DAYS = 7


class TrashError(Exception):
    pass


def _spec(entity_type: str) -> dict[str, Any] | None:
    specs = {
        "note": {
            "tables": [
                (Note.__table__, "id", None),
                (NoteDrawing.__table__, "note_id", None),
                (NoteVersion.__table__, "note_id", None),
            ],
            "root": Note.__table__,
        },
        "quiz": {
            "tables": [
                (Activity.__table__, "id", None),
                (Question.__table__, "activity_id", None),
                (Attempt.__table__, "activity_id", None),
                (Answer.__table__, "attempt_id", "attempts"),
                (QuizHelpEvent.__table__, "attempt_id", "attempts"),
                (Mistake.__table__, "question_id", "questions"),
                (ItemStat.__table__, "question_id", "questions"),
            ],
            "root": Activity.__table__,
        },
        "exercise": {
            "tables": [
                (Exercise.__table__, "id", None),
                (ExerciseStep.__table__, "exercise_id", None),
                (ExerciseSession.__table__, "exercise_id", None),
                (StepAttempt.__table__, "session_id", "exercise_sessions"),
                (FsrsState.__table__, "card_id", None),
                (ReviewLog.__table__, "card_id", None),
            ],
            "root": Exercise.__table__,
        },
        "chat": {
            "tables": [
                (ChatSession.__table__, "id", None),
                (ChatMessage.__table__, "session_id", None),
                (ChatProposal.__table__, "message_id", "chat_messages"),
                (ChatProposalAnchor.__table__, "proposal_id", "chat_proposals"),
            ],
            "root": ChatSession.__table__,
        },
        "material": {
            "tables": [
                (Material.__table__, "id", None),
                (Extraction.__table__, "material_id", None),
                (MaterialLink.__table__, "material_id", None),
                (MaterialStudyState.__table__, "material_id", None),
                (MaterialImage.__table__, "material_id", None),
                (MaterialDrawing.__table__, "material_id", None),
                (MaterialIndexCard.__table__, "material_id", None),
            ],
            "root": Material.__table__,
        },
    }
    return specs.get(entity_type)


ENTITY_TYPES = ("note", "quiz", "exercise", "chat", "material", "node")


def _jsonify(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _serialize(session: Session, entity_type: str, root_id: str) -> dict[str, Any]:
    spec = _spec(entity_type)
    if spec is None:
        raise TrashError(f"unknown entity type {entity_type}")
    payload: dict[str, Any] = {"tables": {}, "blobs": {}}
    for table, column, parent in spec["tables"]:
        if parent is None:
            statement = select(table).where(table.c[column] == root_id)
        else:
            parent_ids = [row["id"] for row in payload["tables"].get(parent, [])]
            statement = select(table).where(table.c[column].in_(parent_ids))
        rows = list(session.execute(statement).mappings())
        payload["tables"][table.name] = [
            {key: _jsonify(value) for key, value in row.items()} for row in rows
        ]
    return payload


def _collect_note_blobs(session: Session, payload: dict[str, Any], blobs_store: Any) -> None:
    for row in payload["tables"].get("note_drawings", []):
        sha = row.get("png_sha")
        if sha is None or sha in payload["blobs"]:
            continue
        data = blobs_store.get(sha)
        if data is not None:
            payload["blobs"][sha] = base64.b64encode(data).decode()


def persist(
    session: Session,
    entity_type: str,
    title: str,
    profile_id: str,
    payload: dict[str, Any],
) -> str:
    item = DeletedItem(
        profile_id=profile_id,
        entity_type=entity_type,
        title=title[:300],
        payload=payload,
        deleted_at=utcnow(),
        purge_after=utcnow() + timedelta(days=TRASH_TTL_DAYS),
    )
    session.add(item)
    session.flush()
    return item.id


def snapshot(
    session: Session,
    entity_type: str,
    root_id: str,
    title: str,
    profile_id: str,
    blobs_store: Any = None,
) -> str:
    payload = _serialize(session, entity_type, root_id)
    if blobs_store is not None and entity_type == "note":
        _collect_note_blobs(session, payload, blobs_store)
    return persist(session, entity_type, title, profile_id, payload)


def _parse_value(table: Any, column_name: str, value: Any) -> Any:
    column = table.c[column_name]
    if isinstance(column.type, DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


def _restore_rows(session: Session, payload: dict[str, Any]) -> dict[str, dict[str, int]]:
    remapped: dict[str, dict[str, int]] = {}
    for table_name, rows in payload["tables"].items():
        model = _model_for(table_name)
        table = model.__table__
        for row in rows:
            values = dict(row)
            pk = values.get("id")
            for fk in table.foreign_keys:
                parent_remap = remapped.get(fk.column.table.name)
                if parent_remap is not None and values.get(fk.parent.name) is not None:
                    values[fk.parent.name] = parent_remap.get(
                        values[fk.parent.name], values[fk.parent.name]
                    )
            if pk is not None and session.get(model, pk) is not None:
                del values["id"]
            for key, value in list(values.items()):
                values[key] = _parse_value(table, key, value)
            result = session.execute(table.insert().values(**values))
            inserted = getattr(result, "inserted_primary_key", None)
            new_pk = inserted[0] if inserted else None
            if pk is not None and new_pk is not None and new_pk != pk:
                remapped.setdefault(table_name, {})[pk] = int(new_pk)
    return remapped


_TABLE_REGISTRY: dict[str, Any] = {
    "notes": Note,
    "note_drawings": NoteDrawing,
    "note_versions": NoteVersion,
    "activities": Activity,
    "questions": Question,
    "attempts": Attempt,
    "answers": Answer,
    "quiz_help_events": QuizHelpEvent,
    "mistakes": Mistake,
    "item_stats": ItemStat,
    "exercises": Exercise,
    "exercise_steps": ExerciseStep,
    "exercise_sessions": ExerciseSession,
    "step_attempts": StepAttempt,
    "fsrs_states": FsrsState,
    "review_log": ReviewLog,
    "chat_sessions": ChatSession,
    "chat_messages": ChatMessage,
    "chat_proposals": ChatProposal,
    "chat_proposal_anchors": ChatProposalAnchor,
    "materials": Material,
    "extractions": Extraction,
    "material_links": MaterialLink,
    "material_study_state": MaterialStudyState,
    "material_images": MaterialImage,
    "material_drawings": MaterialDrawing,
    "material_index_cards": MaterialIndexCard,
}


def _model_for(table_name: str) -> Any:
    model = _TABLE_REGISTRY.get(table_name)
    if model is None:
        raise TrashError(f"cannot restore table {table_name}")
    return model


def restore_material(session: Session, item: DeletedItem) -> tuple[str, str | None]:
    payload = item.payload
    material_rows = payload["tables"].get("materials", [])
    if not material_rows:
        raise TrashError("material snapshot is empty")
    row = material_rows[0]
    course_id = row["course_id"]
    content_hash = row.get("content_hash")
    existing = None
    if content_hash:
        existing = session.scalars(
            select(Material).where(
                Material.profile_id == item.profile_id,
                Material.course_id == course_id,
                Material.content_hash == content_hash,
                Material.status != "failed",
            )
        ).first()
    if existing is not None:
        attached = 0
        for link in payload["tables"].get("material_links", []):
            node = session.get(TreeNode, link["node_id"])
            if node is None:
                continue
            duplicate = session.scalars(
                select(MaterialLink).where(
                    MaterialLink.node_id == link["node_id"],
                    MaterialLink.material_id == existing.id,
                )
            ).first()
            if duplicate is not None:
                continue
            session.add(
                MaterialLink(
                    node_id=link["node_id"],
                    material_id=existing.id,
                    rationale=link.get("rationale"),
                    auto_assigned=link.get("auto_assigned", False),
                    confidence=link.get("confidence"),
                )
            )
            attached += 1
        session.delete(item)
        session.flush()
        return ("merged", existing.id) if attached else ("deduped", existing.id)

    node_ids = set(session.scalars(select(TreeNode.id)).all())
    payload["tables"]["material_links"] = [
        link
        for link in payload["tables"].get("material_links", [])
        if link.get("node_id") in node_ids
    ]
    remapped = _restore_rows(session, payload)
    new_id = remapped.get("materials", {}).get(row["id"], row["id"])
    restored = session.get(Material, new_id)
    if restored is not None and restored.folder_id is not None:
        from ...domain.models import MaterialFolder

        if session.get(MaterialFolder, restored.folder_id) is None:
            restored.folder_id = None

    if restored is not None:
        latest = session.scalars(
            select(Extraction)
            .where(Extraction.material_id == new_id)
            .order_by(Extraction.version.desc())
        ).first()
        if latest is not None:
            ocr_parts = [
                drawing.ocr_markdown for drawing in restored.drawings if drawing.ocr_markdown
            ] + [image.ocr_markdown for image in restored.images if image.ocr_markdown]
            ocr = "\n".join(part for part in ocr_parts if part)
            chunk_source = f"{latest.markdown}\n\n{ocr}" if ocr else latest.markdown
            for ordinal, (chunk_text, chunk_tokens) in enumerate(
                chunk_texts_for_space(session, chunk_source)
            ):
                session.add(
                    Chunk(
                        extraction_id=latest.id,
                        ordinal=ordinal,
                        text=chunk_text,
                        token_count=chunk_tokens,
                    )
                )
            sync_material_fts(session, restored, latest.markdown, ocr)

    session.delete(item)
    session.flush()
    return ("restored", new_id)


def restore(session: Session, item: DeletedItem, blobs_store: Any = None) -> str:
    if item.entity_type in ("material", "node"):
        raise TrashError("use the dedicated restore path")
    if item.entity_type not in ENTITY_TYPES:
        raise TrashError("unknown entity type")
    payload = item.payload
    if blobs_store is not None:
        for encoded in payload.get("blobs", {}).values():
            blobs_store.put(base64.b64decode(encoded), mime="image/png", session=session)
    _restore_rows(session, payload)
    session.delete(item)
    session.flush()
    return item.entity_type


def list_items(session: Session, profile_id: str) -> list[dict[str, Any]]:
    purge_expired(session)
    rows = list(
        session.scalars(
            select(DeletedItem)
            .where(DeletedItem.profile_id == profile_id)
            .order_by(DeletedItem.deleted_at.desc(), DeletedItem.id.desc())
            .limit(200)
        )
    )
    return [
        {
            "id": item.id,
            "entity_type": item.entity_type,
            "title": item.title,
            "deleted_at": item.deleted_at.isoformat(),
            "purge_after": item.purge_after.isoformat(),
        }
        for item in rows
    ]


def purge_expired(session: Session) -> int:
    result = session.execute(delete(DeletedItem).where(DeletedItem.purge_after < utcnow()))
    session.commit()
    return int(result.rowcount if hasattr(result, "rowcount") else 0)


def purge_one(session: Session, item: DeletedItem) -> None:
    session.delete(item)
    session.commit()
