from .core import (
    JSON as JSON,
)
from .core import (
    Any as Any,
)
from .core import (
    Base as Base,
)
from .core import (
    Boolean as Boolean,
)
from .core import (
    DateTime as DateTime,
)
from .core import (
    Float as Float,
)
from .core import (
    ForeignKey as ForeignKey,
)
from .core import (
    ForeignKeyConstraint as ForeignKeyConstraint,
)
from .core import (
    Index as Index,
)
from .core import (
    Integer as Integer,
)
from .core import (
    Mapped as Mapped,
)
from .core import (
    String as String,
)
from .core import (
    Text as Text,
)
from .core import (
    datetime as datetime,
)
from .core import (
    mapped_column as mapped_column,
)
from .core import (
    relationship as relationship,
)
from .core import (
    utcnow as utcnow,
)


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["node_id", "course_id"], ["tree_nodes.id", "tree_nodes.course_id"]
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    node_id: Mapped[int | None] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(20), default="quiz")
    title: Mapped[str] = mapped_column(String(300))
    config: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    generated_from: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    questions: Mapped[list["Question"]] = relationship(
        back_populates="activity", order_by="Question.id", cascade="all, delete-orphan"
    )
    attempts: Mapped[list["Attempt"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )

class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id"))
    type: Mapped[str] = mapped_column(String(20))
    stem: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    options: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    answer: Mapped[dict[str, Any]] = mapped_column(JSON)
    explanation: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    difficulty: Mapped[float | None] = mapped_column(Float)
    bloom: Mapped[str | None] = mapped_column(String(20))
    skill: Mapped[str | None] = mapped_column(String(20))
    concept_ids: Mapped[list[int] | None] = mapped_column(JSON)
    expected_time_sec: Mapped[int | None] = mapped_column(Integer)
    curriculum_code: Mapped[str | None] = mapped_column(String(120))
    source_refs: Mapped[list[int] | None] = mapped_column(JSON)
    distractor_misconceptions: Mapped[dict[str, str] | None] = mapped_column(JSON)
    sympy_check: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    input_modes: Mapped[list[str] | None] = mapped_column(JSON)
    tags: Mapped[list[str] | None] = mapped_column(JSON)
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    flag: Mapped[str] = mapped_column(String(10), default="ok")
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    activity: Mapped[Activity] = relationship(back_populates="questions")

class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), index=True)
    mode: Mapped[str] = mapped_column(String(10), default="practice")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[float | None] = mapped_column(Float)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    activity: Mapped[Activity] = relationship(back_populates="attempts")
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )

class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempts.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    input_mode: Mapped[str | None] = mapped_column(String(10))
    correct: Mapped[bool | None] = mapped_column(Boolean)
    partial_credit: Mapped[float | None] = mapped_column(Float)
    feedback: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    graded_by: Mapped[str | None] = mapped_column(String(10))
    time_ms: Mapped[int | None] = mapped_column(Integer)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    error_tags: Mapped[list[str] | None] = mapped_column(JSON)
    help_events: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    attempt: Mapped[Attempt] = relationship(back_populates="answers")

class Mistake(Base):
    __tablename__ = "mistakes"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    concept_ids: Mapped[list[int] | None] = mapped_column(JSON)
    error_tags: Mapped[list[str] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class Exercise(Base):
    __tablename__ = "exercises"
    __table_args__ = (
        ForeignKeyConstraint(
            ["node_id", "course_id"], ["tree_nodes.id", "tree_nodes.course_id"]
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    node_id: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(30), default="multi_step")
    deck_ref: Mapped[str | None] = mapped_column(String(200))
    context: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    difficulty: Mapped[float | None] = mapped_column(Float)
    created_from: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    steps: Mapped[list["ExerciseStep"]] = relationship(
        back_populates="exercise", order_by="ExerciseStep.order_idx", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["ExerciseSession"]] = relationship(
        back_populates="exercise", cascade="all, delete-orphan"
    )
    fsrs_state: Mapped["FsrsState | None"] = relationship(
        foreign_keys="[FsrsState.card_id]",
        back_populates="card",
        cascade="all, delete-orphan",
        uselist=False,
    )

class ExerciseStep(Base):
    __tablename__ = "exercise_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True)
    order_idx: Mapped[int] = mapped_column(Integer)
    prompt: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    expected: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    hints_pregenerated: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    rubric: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    exercise: Mapped[Exercise] = relationship(back_populates="steps")

class ExerciseSession(Base):
    __tablename__ = "exercise_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True)
    current_step_idx: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    socratic: Mapped[bool] = mapped_column(Boolean, default=False)
    independence_score: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    exercise: Mapped[Exercise] = relationship(back_populates="sessions")
    attempts: Mapped[list["StepAttempt"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

class StepAttempt(Base):
    __tablename__ = "step_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exercise_sessions.id"), index=True)
    step_idx: Mapped[int] = mapped_column(Integer)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    correct: Mapped[bool | None] = mapped_column(Boolean)
    hint_level_used: Mapped[int | None] = mapped_column(Integer)
    error_class: Mapped[str | None] = mapped_column(String(30))
    feedback: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[ExerciseSession] = relationship(back_populates="attempts")

class QuizHelpEvent(Base):
    __tablename__ = "quiz_help_events"
    __table_args__ = (
        Index("ix_quiz_help_events_attempt_question", "attempt_id", "question_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempts.id"))
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    level: Mapped[int] = mapped_column(Integer)
    markdown: Mapped[str] = mapped_column(Text)
    violations: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class FsrsState(Base):
    __tablename__ = "fsrs_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id"), index=True, unique=True
    )
    state: Mapped[str] = mapped_column(String(20), default="new")
    stability: Mapped[float | None] = mapped_column(Float)
    difficulty: Mapped[float | None] = mapped_column(Float)
    reps: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    card: Mapped["Exercise"] = relationship(
        foreign_keys=[card_id], back_populates="fsrs_state"
    )

class ReviewLog(Base):
    __tablename__ = "review_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    interval_days: Mapped[float] = mapped_column(Float)
    elapsed_days: Mapped[float] = mapped_column(Float)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ErrorPattern(Base):
    __tablename__ = "error_patterns"
    __table_args__ = (
        Index("uq_error_patterns_key", "key", unique=True),
        Index("ix_error_patterns_course_type", "course_type_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80))
    course_type_id: Mapped[int | None] = mapped_column(ForeignKey("course_types.id"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    example: Mapped[str | None] = mapped_column(Text)
    detection: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    order_idx: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
