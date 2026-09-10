from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from test_chat_api import NoEmbedder

from app.ai.gateway import LLMGateway
from app.ai.mentions import MentionRegistry
from app.domain.models import ChatMessage, ChatSession, Course, Profile
from app.services.knowledge.tree import TreeService
from app.services.platform.chat import ChatService


def build_course(db_session: Session, title: str = "Calculus I") -> tuple[Course, Any]:
    profile = Profile(name="p")
    db_session.add(profile)
    db_session.flush()
    course = Course(profile_id=profile.id, title=title)
    db_session.add(course)
    db_session.flush()
    return course, profile


def make_session(
    db_session: Session, profile: Any, course: Course, node_id: int | None
) -> ChatSession:
    session_row = ChatSession(
        profile_id=profile.id,
        course_id=course.id,
        node_id=node_id,
        title="t",
    )
    db_session.add(session_row)
    db_session.flush()
    db_session.add(
        ChatMessage(
            session_id=session_row.id,
            role="user",
            blocks=[{"type": "md", "md": "hello"}],
        )
    )
    db_session.commit()
    return session_row


def test_structure_block_renders_neighborhood(db_session: Session) -> None:
    course, profile = build_course(db_session)
    tree = TreeService(db_session)
    root = tree.ensure_root(course.id)
    chapter = tree.create_node(
        course.id, root.id, "Integration", summary="Techniques of integration"
    )
    sibling_section = tree.create_node(
        course.id, chapter.id, "Substitution", summary="u-substitution"
    )
    section = tree.create_node(course.id, chapter.id, "Parts", summary="Integration by parts")
    child = tree.create_node(course.id, section.id, "Basic cases", summary="Simple products")
    db_session.commit()

    session_row = make_session(db_session, profile, course, section.id)
    service = ChatService(db_session, NoGateway(), NoEmbedder())
    registry = MentionRegistry()
    block = service._structure_block(session_row, registry)

    assert "Location: Calculus I > Integration > Parts" in block
    assert f"Parent: [T{chapter.id}] Integration — Techniques of integration" in block
    assert f"[T{sibling_section.id}] Substitution — u-substitution" in block
    assert "Siblings:" in block
    assert f"[T{child.id}] Basic cases — Simple products" in block
    assert "Children:" in block
    for ref in (f"T{chapter.id}", f"T{sibling_section.id}", f"T{child.id}"):
        assert registry.get(ref) is not None
    base = registry.get(f"T{section.id}")
    assert base is not None and base.summary == "Integration by parts"


def test_structure_block_course_level_lists_chapters(db_session: Session) -> None:
    course, profile = build_course(db_session)
    tree = TreeService(db_session)
    root = tree.ensure_root(course.id)
    chapter = tree.create_node(course.id, root.id, "Limits", summary="Approaching values")
    db_session.commit()

    session_row = make_session(db_session, profile, course, None)
    service = ChatService(db_session, NoGateway(), NoEmbedder())
    registry = MentionRegistry()
    block = service._structure_block(session_row, registry)

    assert "Location: Calculus I (course level)" in block
    assert f"Chapters: [T{chapter.id}] Limits — Approaching values" in block
    assert registry.get(f"T{chapter.id}") is not None


def test_structure_group_cap_trims_with_marker(db_session: Session) -> None:
    course, profile = build_course(db_session)
    tree = TreeService(db_session)
    root = tree.ensure_root(course.id)
    chapter = tree.create_node(course.id, root.id, "Big chapter")
    for index in range(11):
        tree.create_node(course.id, chapter.id, f"Section {index}")
    db_session.commit()

    session_row = make_session(db_session, profile, course, chapter.id)
    service = ChatService(db_session, NoGateway(), NoEmbedder())
    block = service._structure_block(session_row, MentionRegistry())

    children_line = next(line for line in block.splitlines() if line.startswith("Children:"))
    assert children_line.count("[T") == 8
    assert "… +3 more" in children_line


def test_leaf_node_omits_children_group(db_session: Session) -> None:
    course, profile = build_course(db_session)
    tree = TreeService(db_session)
    root = tree.ensure_root(course.id)
    section = tree.create_node(course.id, root.id, "Alone")
    db_session.commit()

    session_row = make_session(db_session, profile, course, section.id)
    service = ChatService(db_session, NoGateway(), NoEmbedder())
    block = service._structure_block(session_row, MentionRegistry())

    assert "Children:" not in block
    assert "Siblings:" not in block
    assert f"Parent: [T{root.id}]" in block


def test_registry_add_enriches_missing_summary() -> None:
    registry = MentionRegistry()
    registry.add("node", 5, "Chapter", 1)
    enriched = registry.add("node", 5, "Chapter", 1, "Techniques")
    assert enriched.summary == "Techniques"
    again = registry.add("node", 5, "Chapter", 1)
    assert again.summary == "Techniques"


def test_prepared_sources_block_starts_with_structure(db_session: Session) -> None:
    course, profile = build_course(db_session)
    tree = TreeService(db_session)
    root = tree.ensure_root(course.id)
    chapter = tree.create_node(course.id, root.id, "Derivatives", summary="Rates of change")
    db_session.commit()

    session_row = make_session(db_session, profile, course, chapter.id)
    user_message = db_session.scalars(
        select(ChatMessage).where(ChatMessage.session_id == session_row.id)
    ).first()
    assert user_message is not None
    service = ChatService(db_session, NoGateway(), NoEmbedder())
    prep = service.prepare_turn_context(session_row, user_message)
    assert prep.sources_block.startswith("Course structure")
    assert "Location: Calculus I > Derivatives" in prep.sources_block
    assert "T2 = Derivatives — Rates of change" in prep.sources_block


class NoGateway(LLMGateway):
    """The structure block never touches the gateway; resolve is never called."""

    def __init__(self) -> None:
        super().__init__(session_factory=None)

    def resolve(self, task: str, course_id: int | None = None) -> Any:
        raise AssertionError("gateway must not be used while building structure context")


def test_read_node_registers_children_and_materials(db_session: Session) -> None:
    from app.domain.models import (
        Material,
        MaterialLink,
    )

    course, profile = build_course(db_session)
    tree = TreeService(db_session)
    root = tree.ensure_root(course.id)
    chapter = tree.create_node(course.id, root.id, "Chapter 1", summary="First chapter")
    child = tree.create_node(course.id, chapter.id, "Section 1.1", summary="First section")
    material = Material(
        profile_id=profile.id,
        course_id=course.id,
        kind="md",
        title="intro.md",
        filename="intro.md",
        status="ready",
    )
    db_session.add(material)
    db_session.flush()
    db_session.add(
        MaterialLink(course_id=course.id, node_id=chapter.id, material_id=material.id)
    )
    db_session.commit()

    make_session(db_session, profile, course, chapter.id)
    service = ChatService(db_session, NoGateway(), NoEmbedder())
    registry = MentionRegistry()
    registry.add("node", chapter.id, chapter.title, course.id, "First chapter")
    content = service._read_handle(f"T{chapter.id}", registry)

    assert "Children:" in content
    assert f"[T{child.id}] Section 1.1 — First section" in content
    assert "Materials:" in content
    assert f"[M{material.id}] intro.md" in content
    assert registry.get(f"T{child.id}") is not None
    assert registry.get(f"M{material.id}") is not None
