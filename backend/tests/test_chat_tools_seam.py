from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.orm import Session
from test_chat_api import NoEmbedder

from app.ai.gateway import LLMGateway
from app.ai.mentions import MentionRegistry
from app.domain.models import ChatMessage, ChatQuizPending, ChatSession, Profile
from app.extensions.registry import extension_registry
from app.extensions.search.provider import SearchError
from app.services.platform.chat.service import ChatService


class NoGateway(LLMGateway):
    """The tools seam never touches the gateway directly; resolve must not fire."""

    def __init__(self) -> None:
        super().__init__(session_factory=None)

    def resolve(self, task: str, course_id: str | None = None) -> Any:
        raise AssertionError("gateway must not be used while running chat tools")


def build_profile(db_session: Session, owner: Any) -> Profile:
    profile = Profile(user_id=owner.id, name="p")
    db_session.add(profile)
    db_session.flush()
    return profile


def make_session(db_session: Session, profile: Profile, **kwargs: Any) -> ChatSession:
    session_row = ChatSession(profile_id=profile.id, title="t", **kwargs)
    db_session.add(session_row)
    db_session.flush()
    return session_row


def deny_capability(*args: str, **kwargs: str) -> bool:
    return False


def allow_capability(*args: str, **kwargs: str) -> bool:
    return True


def test_discover_requires_the_chat_tools_capability(
    db_session: Session, owner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile)
    monkeypatch.setattr(extension_registry, "has_capability", deny_capability)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    result, urls = service._discover("chain rule", session_row)

    assert result == "error: the discovery bundle does not declare chat-tools"
    assert urls == []


def test_discover_here_without_course_is_honest(
    db_session: Session, owner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile)
    monkeypatch.setattr(extension_registry, "has_capability", allow_capability)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    result, urls = service._discover("here", session_row)

    assert "no course context" in result
    assert urls == []


def test_discover_reports_unconfigured_providers(
    db_session: Session, owner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = build_profile(db_session, owner)
    profile.preferences = {"discovery": {"enabled": [], "sites": []}}
    db_session.flush()
    session_row = make_session(db_session, profile)
    monkeypatch.setattr(extension_registry, "has_capability", allow_capability)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    result, urls = service._discover("chain rule", session_row)

    assert "no discovery providers configured" in result
    assert urls == []


def test_discover_lists_dedupes_and_caps_results(
    db_session: Session, owner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile)
    monkeypatch.setattr(extension_registry, "has_capability", allow_capability)
    rows = [
        SimpleNamespace(title="First", url="https://a.example/1"),
        SimpleNamespace(title="First again", url="https://a.example/1"),
        SimpleNamespace(title="Second", url="https://b.example/2"),
    ]
    provider = SimpleNamespace(
        label="Test search",
        search=lambda query, cap, transport: rows,
    )
    monkeypatch.setattr(
        "app.extensions.search.discovery.resolve_providers",
        lambda session, profile_id: [provider],
    )
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    result, urls = service._discover("chain rule", session_row)

    lines = result.splitlines()
    assert len(lines) == 2
    assert lines[0] == "[1] First — https://a.example/1 (Test search)"
    assert lines[1] == "[2] Second — https://b.example/2 (Test search)"
    assert urls == ["https://a.example/1", "https://b.example/2"]


def test_discover_provider_failure_is_reported(
    db_session: Session, owner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile)
    monkeypatch.setattr(extension_registry, "has_capability", allow_capability)

    def boom(query: str, cap: int, transport: Any) -> Any:
        raise RuntimeError("provider down")

    provider = SimpleNamespace(label="Flaky", search=boom)
    monkeypatch.setattr(
        "app.extensions.search.discovery.resolve_providers",
        lambda session, profile_id: [provider],
    )
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    result, urls = service._discover("chain rule", session_row)

    assert result == "error: discovery failed — Flaky: provider down"
    assert urls == []


def test_search_web_without_provider_is_honest(db_session: Session, owner: Any) -> None:
    build_profile(db_session, owner)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    result, urls = service._search_web("chain rule")

    assert "no search provider configured" in result
    assert urls == []


def test_search_web_lists_hits_with_content(
    db_session: Session, owner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_profile(db_session, owner)
    hits = [
        {"title": "Chain rule", "url": "https://a.example/1", "content": "the rule"},
        {"title": "Khan", "url": "https://b.example/2", "content": ""},
    ]
    monkeypatch.setattr(
        "app.services.platform.chat.tools.search_with_fallback",
        lambda session, profile_id, query, transport: hits,
    )
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    result, urls = service._search_web("chain rule")

    assert result == (
        "[1] Chain rule — https://a.example/1\nthe rule\n[2] Khan — https://b.example/2"
    )
    assert urls == ["https://a.example/1", "https://b.example/2"]


def test_search_web_reports_provider_errors(
    db_session: Session, owner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_profile(db_session, owner)

    def boom(session: Any, profile_id: str, query: str, transport: Any) -> Any:
        raise SearchError("protocol", "key rejected")

    monkeypatch.setattr("app.services.platform.chat.tools.search_with_fallback", boom)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    result, urls = service._search_web("chain rule")

    assert result == "error: key rejected"
    assert urls == []


def test_fetch_url_passes_through_content(
    db_session: Session, owner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.platform.chat.tools.perform_fetch",
        lambda url, transport: "<html>page</html>",
    )
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    assert service._fetch_url("https://a.example") == "<html>page</html>"


def test_fetch_url_reports_errors(
    db_session: Session, owner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:

    def boom(url: str, transport: Any) -> Any:
        raise SearchError("unreachable", "blocked by robots")

    monkeypatch.setattr("app.services.platform.chat.tools.perform_fetch", boom)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    assert service._fetch_url("https://a.example") == "error: blocked by robots"


def test_quiz_tool_refuses_when_quizme_is_off(db_session: Session, owner: Any) -> None:
    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile)
    emitted: list[dict[str, Any]] = []
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    result, entry = service._handle_quiz_tool(session_row, "2+2?", "agent", 0.0, 5, emitted.append)

    assert result.startswith("error: quiz-me is off")
    assert entry["status"] == "done"
    assert entry["result"] == result
    assert len(emitted) == 1
    assert emitted[0]["type"] == "tool_call"
    assert emitted[0]["name"] == "QUIZ"
    assert emitted[0]["result"] == result


def test_quiz_tool_stores_the_pending_card(db_session: Session, owner: Any) -> None:
    from app.services.platform.quizme import pending_state

    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile, quizme=True)
    emitted: list[dict[str, Any]] = []
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    result, entry = service._handle_quiz_tool(
        session_row,
        '{"question": "What is 2+2?", "choices": ["3", "4"], "expected_index": 1}',
        "agent",
        0.0,
        5,
        emitted.append,
    )

    assert result.startswith("question presented to the student as an interactive card")
    assert entry["quiz"] == {"question": "What is 2+2?", "choices": ["3", "4"]}
    db_session.flush()
    row = db_session.get(ChatQuizPending, session_row.id)
    assert row is not None
    state = pending_state(row)
    assert state is not None
    assert state["question"] == "What is 2+2?"
    assert state["expected_index"] == 1
    assert state["awaiting_answer"] is True


def test_quiz_tool_reports_invalid_arguments(db_session: Session, owner: Any) -> None:
    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile, quizme=True)
    emitted: list[dict[str, Any]] = []
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    result, entry = service._handle_quiz_tool(
        session_row,
        '{"question": "What is 2+2?", "choices": ["3"]}',
        "agent",
        0.0,
        5,
        emitted.append,
    )

    assert result.startswith("error:")
    assert "choices must be 2-6 options" in result
    assert entry["status"] == "done"
    assert session_row.quiz_pending_row is None


def test_quiz_tool_wraps_plain_prose_questions(db_session: Session, owner: Any) -> None:
    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile, quizme=True)
    emitted: list[dict[str, Any]] = []
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    result, entry = service._handle_quiz_tool(
        session_row,
        "What is the derivative of x^2?",
        "agent",
        0.0,
        5,
        emitted.append,
    )

    assert result.startswith("error:")
    assert entry["status"] == "done"
    assert session_row.quiz_pending_row is None


def test_resource_tool_rejects_unknown_keywords(db_session: Session, owner: Any) -> None:
    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    result = service._run_resource_tool("NOPE", "", session_row, MentionRegistry())

    assert result == "error: unknown resource tool 'NOPE'"


def test_resource_tool_node_argument_needs_a_handle(db_session: Session, owner: Any) -> None:
    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    result = service._run_resource_tool("NODE_MATERIALS", "", session_row, MentionRegistry())

    assert result.startswith("error: need a node handle (T#)")


def test_resource_tool_course_argument_needs_a_course(db_session: Session, owner: Any) -> None:
    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    result = service._run_resource_tool("MISTAKES", "", session_row, MentionRegistry())

    assert result == "error: this tool needs a course-scoped chat session"


def test_resource_tool_runs_without_arguments(db_session: Session, owner: Any) -> None:
    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    result = service._run_resource_tool("COURSES", "", session_row, MentionRegistry())

    assert result == '{"courses": []}'


def test_resolve_node_arg_prefers_the_session_node(db_session: Session, owner: Any) -> None:
    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    assert service._resolve_node_arg("", session_row, MentionRegistry()) is None
    assert service._resolve_node_arg("here", session_row, MentionRegistry()) is None
    assert service._resolve_node_arg("T99", session_row, MentionRegistry()) is None
    session_row.node_id = "node-1"
    assert service._resolve_node_arg("here", session_row, MentionRegistry()) == "node-1"
    assert service._resolve_node_arg("current", session_row, MentionRegistry()) == "node-1"


def test_read_widget_state_scans_the_conversation_state(db_session: Session, owner: Any) -> None:
    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile)
    first = ChatMessage(
        session_id=session_row.id,
        role="assistant",
        blocks=[{"type": "text", "md": "a"}],
        state={"w1": {"checked": [1]}},
    )
    db_session.add(first)
    db_session.flush()
    second = ChatMessage(
        session_id=session_row.id,
        role="assistant",
        blocks=[{"type": "text", "md": "b"}],
        state={"w2": {"value": 3}},
        parent_id=first.id,
    )
    first.active_child_id = second.id
    db_session.add_all([second])
    db_session.flush()
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    assert service._read_widget_state(session_row, "w1") == '{"checked": [1]}'
    assert service._read_widget_state(session_row, "w2") == '{"value": 3}'
    assert "no state recorded" in service._read_widget_state(session_row, "w9")
