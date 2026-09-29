"""WS contract: owner-scoped subscriptions only (identity-auth §10).

Topics must resolve to a resource the caller owns; foreign or
unresolvable topics are refused and never forwarded. Client-side
publishing is not part of the protocol (server-published events only).
"""

from typing import Any, cast

from conftest import AnonymousTestClient
from fastapi.testclient import TestClient


def _chat_session(client: Any) -> int:
    return int(client.post("/api/v1/chat/sessions", json={}).json()["id"])


def _mint(app: Any, email: str, is_admin: bool = False) -> tuple[str, str, str]:
    """(cookie_header, csrf, profile_id) for an arbitrary user — same
    mechanism as conftest.mint_session, with a controllable role."""
    import secrets

    from conftest import _fixture_password_hash
    from nx_auth.cookies import cookie_names
    from nx_auth.tokens import AuthMode, TokenKind, mint_token

    from app.auth.stores import StudyUserStore
    from app.services.platform.profiles import get_or_create_default

    factory = app.state.session_factory
    users = StudyUserStore(factory)
    user = users.get_by_email(email) or users.create(
        email=email, password_hash=_fixture_password_hash(), is_admin=is_admin
    )
    with factory() as session:
        profile_id = str(get_or_create_default(session, user.id).id)
    kit = app.state.auth
    token = mint_token(
        kit.ring,
        kit.config,
        kind=TokenKind.SESSION,
        sub=user.id,
        ver=user.token_version,
        auth_mode=AuthMode.PASSWORD,
    )
    csrf = secrets.token_urlsafe(32)
    return f"{cookie_names(kit.config).access}={token}; nx_csrf={csrf}", csrf, profile_id


def test_ws_ping_pong(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_ws_subscribe_owned_chat_session(client: TestClient) -> None:
    session_id = _chat_session(client)
    topic = f"chat:{session_id}"
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "subscribe", "topic": topic})
        assert ws.receive_json() == {"type": "subscribed", "topic": topic}
        ws.send_json({"type": "unsubscribe", "topic": topic})
        assert ws.receive_json() == {"type": "unsubscribed", "topic": topic}


def test_ws_rejects_foreign_chat_session(client: TestClient) -> None:
    session_id = _chat_session(client)
    cookie, _csrf, profile_id = _mint(client.app, "other-ws@study.local", is_admin=False)
    foreign = AnonymousTestClient(
        client.app,
        headers={"Cookie": cookie, "X-Profile-Id": profile_id},
    )
    with foreign.websocket_connect("/ws", headers={"Cookie": cookie}) as ws:
        ws.send_json({"type": "subscribe", "topic": f"chat:{session_id}"})
        assert ws.receive_json() == {"type": "error", "error": "topic_forbidden"}


def test_ws_rejects_unresolvable_topics(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        for topic in ("jobs:424242", "backups", "chat:not-a-number", "nonsense:1"):
            ws.send_json({"type": "subscribe", "topic": topic})
            assert ws.receive_json() == {"type": "error", "error": "topic_forbidden"}


def test_ws_jobs_topic_is_owned_through_the_payload(client: TestClient) -> None:
    from app.domain.models import ChatSession, Job

    # The subscriber is a plain user (the fixture client is an admin and
    # admins may observe any resolvable resource).
    cookie, csrf, profile_id = _mint(client.app, "jobs-sub@study.local", is_admin=False)
    sub = AnonymousTestClient(
        client.app,
        headers={"Cookie": cookie, "X-Profile-Id": profile_id, "X-CSRF-Token": csrf},
    )
    own_session_id = _chat_session(sub)
    factory = cast(Any, client.app).state.session_factory
    with factory() as db:
        owned = Job(type="chat_turn", payload={"chat_session_id": own_session_id}, status="failed")
        foreign_chat = ChatSession(
            profile_id=_mint(client.app, "other-jobs@study.local")[2], title="foreign"
        )
        db.add_all([owned, foreign_chat])
        db.flush()
        foreign = Job(
            type="chat_turn",
            payload={"chat_session_id": foreign_chat.id},
            status="failed",
        )
        db.add(foreign)
        db.commit()
        owned_id, foreign_id = owned.id, foreign.id

    with sub.websocket_connect("/ws", headers={"Cookie": cookie}) as ws:
        ws.send_json({"type": "subscribe", "topic": f"jobs:{owned_id}"})
        assert ws.receive_json() == {"type": "subscribed", "topic": f"jobs:{owned_id}"}
        ws.send_json({"type": "subscribe", "topic": f"jobs:{foreign_id}"})
        assert ws.receive_json() == {"type": "error", "error": "topic_forbidden"}


def test_ws_rejects_client_publish(client: TestClient) -> None:
    session_id = _chat_session(client)
    topic = f"chat:{session_id}"
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "subscribe", "topic": topic})
        assert ws.receive_json() == {"type": "subscribed", "topic": topic}
        ws.send_json({"type": "publish", "topic": topic, "payload": {"forged": True}})
        assert ws.receive_json() == {"type": "error", "error": "publish_not_supported"}
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
