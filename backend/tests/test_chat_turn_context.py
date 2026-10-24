from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from test_chat_api import NoEmbedder

from app.ai.gateway import LLMGateway
from app.ai.mentions import registry_from_json
from app.domain.models import (
    Activity,
    Answer,
    Attempt,
    ChatSession,
    Course,
    Exercise,
    ExerciseSession,
    ExerciseStep,
    Note,
    Profile,
    Question,
    StepAttempt,
    utcnow,
)
from app.services.knowledge.tree import TreeService
from app.services.platform.chat.service import ChatService


class NoGateway(LLMGateway):
    """The turn-context helpers never touch the gateway; resolve must not fire."""

    def __init__(self) -> None:
        super().__init__(session_factory=None)

    def resolve(self, task: str, course_id: str | None = None) -> Any:
        raise AssertionError("gateway must not be used while assembling turn context")


def build_profile(db_session: Session, owner: Any) -> Profile:
    profile = Profile(user_id=owner.id, name="p")
    db_session.add(profile)
    db_session.flush()
    return profile


def build_course(
    db_session: Session, owner: Any, title: str = "Calculus I"
) -> tuple[Course, Profile]:
    profile = build_profile(db_session, owner)
    course = Course(profile_id=profile.id, title=title)
    db_session.add(course)
    db_session.flush()
    return course, profile


def make_session(db_session: Session, profile: Profile, **kwargs: Any) -> ChatSession:
    session_row = ChatSession(profile_id=profile.id, title="t", **kwargs)
    db_session.add(session_row)
    db_session.flush()
    return session_row


def test_turn_registry_round_trips_through_the_session(db_session: Session, owner: Any) -> None:
    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    registry = service._turn_registry(session_row, [], [])

    assert registry.refs() == []
    assert session_row.mention_registry is not None
    restored = registry_from_json(session_row.mention_registry)
    assert restored.refs() == []


def test_turn_registry_registers_node_materials_and_notes(db_session: Session, owner: Any) -> None:
    course, profile = build_course(db_session, owner)
    tree = TreeService(db_session)
    root = tree.ensure_root(course.id)
    chapter = tree.create_node(course.id, root.id, "Integration", summary="Techniques")
    note = Note(
        profile_id=profile.id,
        course_id=course.id,
        title="Substitution tricks",
        body=[{"type": "text", "md": "remember the parts order"}],
    )
    db_session.add(note)
    db_session.flush()
    session_row = make_session(db_session, profile, course_id=course.id, node_id=chapter.id)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    registry = service._turn_registry(
        session_row,
        [{"id": "mat-1", "title": "intro.md", "summary": "first steps"}],
        [note],
    )

    node_entry = registry.get(f"T{chapter.id}")
    assert node_entry is not None and node_entry.title == "Integration"
    material_entry = registry.get("Mmat-1")
    assert material_entry is not None and material_entry.title == "intro.md"
    note_entry = registry.get(f"N{note.id}")
    assert note_entry is not None and note_entry.title == "Substitution tricks"
    assert session_row.mention_registry


def test_turn_context_without_course_returns_no_chunks(db_session: Session, owner: Any) -> None:
    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile, use_embeddings=False)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    chunks, materials, warning = service._turn_context(session_row, "chain rule")

    assert chunks == []
    assert materials == []
    assert warning is None


def test_turn_context_course_scope_with_no_materials_is_empty(
    db_session: Session, owner: Any
) -> None:
    course, profile = build_course(db_session, owner)
    TreeService(db_session).ensure_root(course.id)
    session_row = make_session(db_session, profile, course_id=course.id, use_embeddings=False)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    chunks, materials, warning = service._turn_context(session_row, "chain rule")

    assert chunks == []
    assert materials == []
    assert warning is None


def test_turn_context_flags_embedding_fallback(db_session: Session, owner: Any) -> None:
    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile, use_embeddings=True)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    _chunks, _materials, warning = service._turn_context(session_row, "chain rule")

    assert warning is not None
    assert "Semantic search is on" in warning


def test_quiz_guard_is_absent_without_binding(db_session: Session, owner: Any) -> None:
    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    assert service._quiz_guard(session_row) is None


def build_quiz_fixture(db_session: Session, owner: Any) -> tuple[ChatSession, Attempt, Question]:
    course, profile = build_course(db_session, owner)
    activity = Activity(profile_id=profile.id, course_id=course.id, title="Quiz 1")
    db_session.add(activity)
    db_session.flush()
    question = Question(
        activity_id=activity.id,
        type="single",
        stem=[{"type": "text", "md": "What is 6 x 7?"}],
        options=[{"type": "text", "md": "42"}, {"type": "text", "md": "48"}],
        answer={"index": 0},
    )
    db_session.add(question)
    db_session.flush()
    attempt = Attempt(activity_id=activity.id)
    db_session.add(attempt)
    db_session.flush()
    session_row = make_session(
        db_session,
        profile,
        context={"quiz_attempt_id": attempt.id, "question_id": question.id},
    )
    return session_row, attempt, question


def test_quiz_guard_hides_option_text_for_open_attempt(db_session: Session, owner: Any) -> None:
    session_row, _attempt, _question = build_quiz_fixture(db_session, owner)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    guard = service._quiz_guard(session_row)

    assert guard is not None
    assert guard["expected"] is None
    assert guard["expected_candidates"] == ["42"]
    assert guard["forbidden_texts"] == ["42"]


def test_quiz_guard_clears_once_answered(db_session: Session, owner: Any) -> None:
    session_row, attempt, question = build_quiz_fixture(db_session, owner)
    db_session.add(Answer(attempt_id=attempt.id, question_id=question.id))
    db_session.flush()
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    assert service._quiz_guard(session_row) is None


def test_quiz_guard_clears_for_finished_attempt(db_session: Session, owner: Any) -> None:
    session_row, attempt, _question = build_quiz_fixture(db_session, owner)
    attempt.finished_at = utcnow()
    db_session.flush()
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    assert service._quiz_guard(session_row) is None


def test_quiz_guard_clears_for_missing_question(db_session: Session, owner: Any) -> None:
    session_row, attempt, question = build_quiz_fixture(db_session, owner)
    session_row.context = {"quiz_attempt_id": attempt.id, "question_id": question.id[:-1]}
    db_session.flush()
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    assert service._quiz_guard(session_row) is None


def build_exercise_fixture(
    db_session: Session, owner: Any
) -> tuple[ChatSession, ExerciseSession, ExerciseStep]:
    course, profile = build_course(db_session, owner)
    exercise = Exercise(profile_id=profile.id, course_id=course.id, title="Derivatives drill")
    db_session.add(exercise)
    db_session.flush()
    step = ExerciseStep(
        exercise_id=exercise.id,
        order_idx=0,
        prompt=[{"type": "text", "md": "Differentiate x^2"}],
        expected={"kind": "math", "value": "2x"},
    )
    db_session.add(step)
    db_session.flush()
    exercise_session = ExerciseSession(exercise_id=exercise.id, current_step_idx=0)
    db_session.add(exercise_session)
    db_session.flush()
    session_row = make_session(
        db_session, profile, context={"exercise_session_id": exercise_session.id}
    )
    return session_row, exercise_session, step


def test_exercise_binding_resolves_active_session(db_session: Session, owner: Any) -> None:
    session_row, exercise_session, step = build_exercise_fixture(db_session, owner)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    binding = service._exercise_binding(session_row)

    assert binding is not None
    assert binding[0].id == exercise_session.id
    assert binding[1].id == step.id


def test_exercise_binding_ignores_finished_session(db_session: Session, owner: Any) -> None:
    session_row, exercise_session, _step = build_exercise_fixture(db_session, owner)
    exercise_session.status = "finished"
    db_session.flush()
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    assert service._exercise_binding(session_row) is None


def test_exercise_binding_ignores_unbound_session(db_session: Session, owner: Any) -> None:
    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    assert service._exercise_binding(session_row) is None


def test_exercise_guard_hides_expected_math(db_session: Session, owner: Any) -> None:
    _session_row, exercise_session, step = build_exercise_fixture(db_session, owner)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    guard = service._exercise_guard(exercise_session, step)

    assert guard == {"expected": "2x", "expected_candidates": [], "forbidden_texts": []}


def test_exercise_guard_clears_once_solved(db_session: Session, owner: Any) -> None:
    _session_row, exercise_session, step = build_exercise_fixture(db_session, owner)
    db_session.add(StepAttempt(session_id=exercise_session.id, step_idx=0, correct=True))
    db_session.flush()
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    assert service._exercise_guard(exercise_session, step) is None


def test_exercise_guard_forbids_text_answers(db_session: Session, owner: Any) -> None:
    _session_row, exercise_session, step = build_exercise_fixture(db_session, owner)
    step.expected = {"kind": "text", "value": "Paris"}
    db_session.flush()
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    guard = service._exercise_guard(exercise_session, step)

    assert guard is not None
    assert guard["expected"] is None
    assert guard["forbidden_texts"] == ["Paris"]


def test_exercise_context_block_renders_step_and_pending_answer(
    db_session: Session, owner: Any
) -> None:
    course, profile = build_course(db_session, owner)
    exercise = Exercise(profile_id=profile.id, course_id=course.id, title="Derivatives drill")
    db_session.add(exercise)
    db_session.flush()
    db_session.add(
        ExerciseStep(
            exercise_id=exercise.id,
            order_idx=0,
            prompt=[{"type": "text", "md": "Differentiate x^2"}],
        )
    )
    db_session.add(
        ExerciseStep(
            exercise_id=exercise.id,
            order_idx=1,
            prompt=[{"type": "text", "md": "Differentiate x^3"}],
        )
    )
    db_session.flush()
    exercise_session = ExerciseSession(exercise_id=exercise.id, current_step_idx=1)
    db_session.add(exercise_session)
    db_session.flush()
    db_session.add(
        StepAttempt(
            session_id=exercise_session.id,
            step_idx=1,
            correct=False,
            error_class="sign",
        )
    )
    db_session.flush()
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    step = db_session.scalars(
        select(ExerciseStep).where(
            ExerciseStep.exercise_id == exercise.id,
            ExerciseStep.order_idx == exercise_session.current_step_idx,
        )
    ).one()
    block = service._exercise_context_block(exercise_session, step, "3x^2")

    assert "Derivatives drill — step 2 of 2" in block
    assert "Differentiate x^3" in block
    assert "$$3x^2$$" in block
    assert "Submitted attempts on this step: 1 (latest: not yet correct (sign))" in block


def test_latest_notes_preview_pins_first_then_recency(db_session: Session, owner: Any) -> None:
    course, profile = build_course(db_session, owner)
    now = utcnow()
    pinned_old = Note(
        profile_id=profile.id,
        course_id=course.id,
        title="Pinned formula sheet",
        body=[{"type": "text", "md": "chain rule"}],
        pinned=True,
        updated_at=now - timedelta(days=6),
    )
    recent = Note(
        profile_id=profile.id,
        course_id=course.id,
        title="Yesterday",
        body=[{"type": "text", "md": "substitution"}],
        updated_at=now - timedelta(days=1),
    )
    older = Note(
        profile_id=profile.id,
        course_id=course.id,
        title="Last week",
        body=[{"type": "text", "md": "parts"}],
        updated_at=now - timedelta(days=5),
    )
    other_course_note = Note(
        profile_id=profile.id,
        course_id=course.id,
        title="Unpinned oldest",
        body=[{"type": "text", "md": "limits"}],
        updated_at=now - timedelta(days=9),
    )
    db_session.add_all([pinned_old, recent, older, other_course_note])
    db_session.flush()
    session_row = make_session(db_session, profile, course_id=course.id)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    notes = service.latest_notes_preview(session_row)

    assert [note.title for note in notes] == ["Pinned formula sheet", "Yesterday", "Last week"]
    assert service._latest_notes(session_row) == notes


def test_latest_notes_preview_without_course_spans_courses(db_session: Session, owner: Any) -> None:
    course, profile = build_course(db_session, owner)
    db_session.add(
        Note(
            profile_id=profile.id,
            course_id=course.id,
            title="Only note",
            body=[{"type": "text", "md": "hello"}],
        )
    )
    db_session.flush()
    session_row = make_session(db_session, profile)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    notes = service.latest_notes_preview(session_row)

    assert [note.title for note in notes] == ["Only note"]


def test_latest_notes_block_renders_excerpts(db_session: Session, owner: Any) -> None:
    course, profile = build_course(db_session, owner)
    db_session.add(
        Note(
            profile_id=profile.id,
            course_id=course.id,
            title="Substitution",
            body=[{"type": "text", "md": "remember the parts order"}],
        )
    )
    db_session.flush()
    session_row = make_session(db_session, profile, course_id=course.id)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    block = service._latest_notes_block(session_row)

    assert block.startswith("The student's latest notes")
    assert "### Substitution" in block
    assert "remember the parts order" in block
    assert "do NOT cite these with [n] numbers" in block


def test_latest_notes_block_is_empty_without_notes(db_session: Session, owner: Any) -> None:
    profile = build_profile(db_session, owner)
    session_row = make_session(db_session, profile)
    service = ChatService(db_session, NoGateway(), NoEmbedder())

    assert service._latest_notes_block(session_row) == ""
