import asyncio
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from nx_auth.cookies import cookie_names
from nx_auth.deps import authenticate_session
from nx_auth.principal import Principal
from sqlalchemy.orm import Session

from ..core.events import EventBus
from ..domain.models import (
    ChatSession,
    Course,
    Job,
    Material,
    MaterialDrawing,
    MaterialImage,
    Note,
    Profile,
)

router = APIRouter(tags=["system"])


def _origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    if origin is None:
        return True
    host = websocket.headers.get("host")
    if host is not None and urlparse(origin).netloc == host:
        return True
    settings = websocket.app.state.settings
    allowed = {raw.strip().rstrip("/") for raw in settings.cors_origins.split(",") if raw.strip()}
    return origin.rstrip("/") in allowed


def _session_principal(websocket: WebSocket) -> Principal | None:
    kit = websocket.app.state.auth
    token = websocket.cookies.get(cookie_names(kit.config).access)
    if token is None:
        return None
    return authenticate_session(kit, token)


def _profile_owner_id(db: Session, profile_id: str | None) -> str | None:
    if profile_id is None:
        return None
    profile = db.get(Profile, profile_id)
    return profile.user_id if profile is not None else None


def _topic_owner_id(db: Session, topic: str, editor_ai: Any) -> str | None:
    """The user id that owns the topic's resource; ``None`` when the
    topic cannot be resolved to an owned resource (fail closed at the
    call site — identity-auth §10: topics are re-scoped to the
    session's owned resources).

    ``jobs:`` resources are owned through their payload reference chain
    (profile/material/chat session/note/drawing/image/course), because
    the job rows themselves carry no owner column.
    """
    kind, _, raw = topic.partition(":")
    if not raw.isdigit():
        return None
    ident = int(raw)
    if kind == "chat":
        chat = db.get(ChatSession, ident)
        return _profile_owner_id(db, chat.profile_id) if chat is not None else None
    if kind == "note":
        note = db.get(Note, ident)
        return _profile_owner_id(db, note.profile_id) if note is not None else None
    if kind == "material":
        material = db.get(Material, ident)
        return _profile_owner_id(db, material.profile_id) if material is not None else None
    if kind == "ai-editor":
        job = editor_ai.get_job(ident) if editor_ai is not None else None
        return job.user_id if job is not None else None
    if kind == "jobs":
        job = db.get(Job, ident)
        if job is None:
            return None
        payload = job.payload or {}
        if "profile_id" in payload:
            return _profile_owner_id(db, str(payload["profile_id"]))
        if "chat_session_id" in payload:
            chat = db.get(ChatSession, int(payload["chat_session_id"]))
            return _profile_owner_id(db, chat.profile_id) if chat is not None else None
        if "material_id" in payload:
            material = db.get(Material, int(payload["material_id"]))
            return _profile_owner_id(db, material.profile_id) if material is not None else None
        if "note_id" in payload:
            note = db.get(Note, int(payload["note_id"]))
            return _profile_owner_id(db, note.profile_id) if note is not None else None
        if "drawing_id" in payload:
            drawing = db.get(MaterialDrawing, int(payload["drawing_id"]))
            if drawing is None:
                return None
            material = db.get(Material, drawing.material_id)
            return _profile_owner_id(db, material.profile_id) if material is not None else None
        if "image_id" in payload:
            image = db.get(MaterialImage, int(payload["image_id"]))
            if image is None:
                return None
            material = db.get(Material, image.material_id)
            return _profile_owner_id(db, material.profile_id) if material is not None else None
        if "course_id" in payload:
            course = db.get(Course, int(payload["course_id"]))
            return _profile_owner_id(db, course.profile_id) if course is not None else None
        return None
    return None


def _topic_allowed(db: Session, principal: Principal, topic: str, editor_ai: Any) -> bool:
    owner_id = _topic_owner_id(db, topic, editor_ai)
    if owner_id is None:
        return False
    return str(owner_id) == str(principal.user_id) or principal.is_admin


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    # Origin first (cross-site hijack), then the session cookie — the
    # same verification path as the HTTP middleware (identity-auth §10).
    if not _origin_allowed(websocket):
        await websocket.close(code=1008)
        return
    principal = _session_principal(websocket)
    if principal is None:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    bus: EventBus = websocket.app.state.bus
    editor_ai = getattr(websocket.app.state, "editor_ai", None)
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    subscribed: set[str] = set()

    async def sender() -> None:
        while True:
            event = await queue.get()
            await websocket.send_json(event)

    sender_task = asyncio.create_task(sender())
    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")
            topic = message.get("topic")
            if msg_type == "subscribe" and isinstance(topic, str):
                # Owner-scoped subscriptions only (§10): a topic must
                # resolve to a resource the principal owns (admins may
                # observe any resolvable resource) — unresolvable or
                # foreign topics are refused, never forwarded.
                with websocket.app.state.session_factory() as db:
                    allowed = _topic_allowed(db, principal, topic, editor_ai)
                if not allowed:
                    queue.put_nowait({"type": "error", "error": "topic_forbidden"})
                    continue
                bus.subscribe(topic, queue)
                subscribed.add(topic)
                queue.put_nowait({"type": "subscribed", "topic": topic})
            elif msg_type == "unsubscribe" and isinstance(topic, str):
                bus.unsubscribe(topic, queue)
                subscribed.discard(topic)
                queue.put_nowait({"type": "unsubscribed", "topic": topic})
            elif msg_type == "publish":
                # Server-published events only: client-side publishing
                # would let any session inject forged events into other
                # users' topics. The product never sends it.
                queue.put_nowait({"type": "error", "error": "publish_not_supported"})
            elif msg_type == "ping":
                queue.put_nowait({"type": "pong"})
            else:
                queue.put_nowait({"type": "error", "error": "unknown_message"})
    except WebSocketDisconnect:
        pass
    finally:
        sender_task.cancel()
        for topic in subscribed:
            bus.unsubscribe(topic, queue)
