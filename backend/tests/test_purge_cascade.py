"""Purge-cascade sweep (plan 81 E, ADR-201).

Create one row in every course-scoped table under one course, purge the
course, and assert every mapped table is back to its pre-course baseline.
Profile-level aggregates (daily rollups, study goals) are not course-scoped
and are deliberately not created here; operational/instance tables (jobs,
AI telemetry, audit, blobs, trash snapshots) have no user-course rows in
this fixture either, so the comparison is literal for all 65 tables.
"""

from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import (
    Activity,
    Answer,
    Attempt,
    ChatMessage,
    ChatProposal,
    ChatProposalAnchor,
    ChatQuizPending,
    ChatSession,
    Chunk,
    Concept,
    ConceptLink,
    ConceptSkillRating,
    ConceptSkillStat,
    Course,
    CourseDefaultTaskAssignment,
    CourseTaskAssignment,
    Exercise,
    ExerciseSession,
    ExerciseStep,
    ExternalSource,
    Extraction,
    FsrsState,
    ItemStat,
    Material,
    MaterialDrawing,
    MaterialFolder,
    MaterialFolderLink,
    MaterialImage,
    MaterialIndexCard,
    MaterialLink,
    MaterialSource,
    MaterialStudyState,
    MaterialSuggestion,
    Mistake,
    NodeConcept,
    Note,
    NoteDrawing,
    NoteVersion,
    PlanItem,
    Question,
    QuizHelpEvent,
    QuizmeAnswer,
    ReviewLog,
    StepAttempt,
    StudySession,
    utcnow,
)
from app.services.knowledge.courses import purge_course
from app.services.knowledge.tree import TreeService
from app.storage.db import Base

BLOCK = [{"type": "text", "md": "sweep"}]
STROKES = [{"points": [[0, 0], [1, 1]], "width": 2}]


def _baseline(session: Session) -> dict[str, int]:
    return {
        table.name: int(session.execute(select(func.count()).select_from(table)).scalar_one())
        for table in Base.metadata.tables.values()
    }


def _seed_everything(session: Session, profile_id: str, course_id: str, root_id: str) -> None:
    activity = Activity(
        profile_id=profile_id,
        course_id=course_id,
        node_id=root_id,
        type="quiz",
        title="Sweep quiz",
    )
    session.add(activity)
    session.flush()

    question = Question(
        activity_id=activity.id,
        type="single",
        stem=BLOCK,
        options=BLOCK,
        answer={"index": 0},
    )
    session.add(question)
    session.flush()

    attempt = Attempt(activity_id=activity.id, mode="practice")
    session.add(attempt)
    session.flush()
    session.add(Answer(attempt_id=attempt.id, question_id=question.id, correct=True))
    session.add(Mistake(profile_id=profile_id, question_id=question.id))
    session.add(ItemStat(question_id=question.id, n_attempts=1, p_correct=1.0))
    session.add(
        QuizHelpEvent(attempt_id=attempt.id, question_id=question.id, level=1, markdown="hint")
    )

    exercise = Exercise(profile_id=profile_id, course_id=course_id, title="Sweep exercise")
    session.add(exercise)
    session.flush()
    session.add(ExerciseStep(exercise_id=exercise.id, order_idx=0, prompt=BLOCK))
    exercise_session = ExerciseSession(exercise_id=exercise.id)
    session.add(exercise_session)
    session.flush()
    session.add(StepAttempt(session_id=exercise_session.id, step_idx=0))
    session.add(FsrsState(card_id=exercise.id, due_at=utcnow()))
    session.add(ReviewLog(card_id=exercise.id, rating=3, interval_days=1.0, elapsed_days=0.0))

    note = Note(profile_id=profile_id, course_id=course_id, title="Sweep note", body=BLOCK)
    session.add(note)
    session.flush()
    session.add(
        NoteVersion(
            note_id=note.id,
            profile_id=profile_id,
            title=note.title,
            body=BLOCK,
            cause="sweep",
        )
    )
    session.add(NoteDrawing(note_id=note.id, strokes=STROKES))

    material = Material(
        profile_id=profile_id,
        course_id=course_id,
        kind="md",
        title="Sweep material",
        filename="sweep.md",
        status="ready",
    )
    session.add(material)
    session.flush()
    extraction = Extraction(
        material_id=material.id,
        extractor="sweep",
        blocks=BLOCK,
        markdown="sweep",
    )
    session.add(extraction)
    session.flush()
    session.add(Chunk(extraction_id=extraction.id, ordinal=0, text="sweep"))
    session.add(MaterialIndexCard(material_id=material.id))
    session.add(MaterialStudyState(material_id=material.id, profile_id=profile_id))
    session.add(MaterialDrawing(material_id=material.id, strokes=STROKES))
    session.add(MaterialImage(material_id=material.id))
    session.add(MaterialLink(course_id=course_id, node_id=root_id, material_id=material.id))

    folder = MaterialFolder(
        profile_id=profile_id,
        course_id=course_id,
        name="Sweep",
        path="/Sweep",
    )
    session.add(folder)
    session.flush()
    session.add(MaterialFolderLink(course_id=course_id, node_id=root_id, folder_id=folder.id))
    source = MaterialSource(
        profile_id=profile_id,
        label="Sweep source",
        path="/tmp/sweep",
        course_id=course_id,
    )
    session.add(source)
    session.flush()
    session.add(
        ExternalSource(
            profile_id=profile_id,
            course_id=course_id,
            kind="rss",
            url="https://example.test/feed",
        )
    )
    session.add(
        MaterialSuggestion(
            profile_id=profile_id,
            course_id=course_id,
            provider="sweep",
            url="https://example.test/item",
            url_norm="https://example.test/item",
            title="Sweep suggestion",
        )
    )

    concept_a = Concept(course_id=course_id, name="A")
    concept_b = Concept(course_id=course_id, name="B")
    session.add_all([concept_a, concept_b])
    session.flush()
    session.add(
        ConceptLink(
            course_id=course_id,
            from_concept_id=concept_a.id,
            to_concept_id=concept_b.id,
            relation="related-to",
        )
    )
    session.add(NodeConcept(node_id=root_id, concept_id=concept_a.id))
    session.add(
        ConceptSkillStat(
            profile_id=profile_id,
            concept="A",
            skill="recall",
            n=1,
            accuracy=1.0,
            weakness_score=0.0,
        )
    )
    session.add(ConceptSkillRating(profile_id=profile_id, concept="A", skill="recall", rating=1.0))

    session.add(
        PlanItem(
            profile_id=profile_id,
            course_id=course_id,
            title="Sweep plan item",
            due_date=date.today(),
        )
    )
    session.add(
        StudySession(
            profile_id=profile_id,
            course_id=course_id,
            kind="quiz",
            source="manual",
        )
    )
    session.add(CourseTaskAssignment(course_id=course_id, task="quiz"))
    session.add(CourseDefaultTaskAssignment(course_id=course_id, requires="text"))

    chat = ChatSession(profile_id=profile_id, course_id=course_id, node_id=root_id)
    session.add(chat)
    session.flush()
    message = ChatMessage(session_id=chat.id, role="user", blocks=BLOCK)
    session.add(message)
    session.flush()
    proposal = ChatProposal(
        message_id=message.id,
        action="create_note",
        payload={"title": "Sweep proposal", "body_md": "sweep"},
    )
    session.add(proposal)
    session.flush()
    session.add(ChatProposalAnchor(proposal_id=proposal.id, position=0, op="append", text="x"))
    session.add(ChatQuizPending(session_id=chat.id, question="1+1?"))
    session.add(QuizmeAnswer(profile_id=profile_id, session_id=chat.id, correct=True))


def test_course_purge_returns_every_table_to_baseline(client: TestClient) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    factory = app.state.session_factory
    profile_id = str(client.get("/api/v1/profiles").json()[0]["id"])

    with factory() as session:
        baseline = _baseline(session)

    with factory() as session:
        course = Course(profile_id=profile_id, title="Sweep course")
        session.add(course)
        session.flush()
        root = TreeService(session).ensure_root(course.id)
        _seed_everything(session, profile_id, course.id, root.id)
        session.commit()
        course_id = str(course.id)

    with factory() as session:
        populated = _baseline(session)
        grown = {table: count for table, count in populated.items() if count > baseline[table]}
        assert len(grown) >= 25, f"fixture did not exercise enough tables: {sorted(grown)}"

        course_row = session.get(Course, course_id)
        assert course_row is not None
        purge_course(session, course_row)
        session.commit()

    with factory() as session:
        after = _baseline(session)
        drift = {
            table: (baseline[table], after[table])
            for table in after
            if after[table] != baseline[table]
        }
        assert not drift, f"purge left rows behind (table: before -> after): {drift}"

    assert client.get("/api/v1/courses").json() == []
