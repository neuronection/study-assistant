from ...core.vocab import (
    AttemptMode as AttemptMode,
)
from ...core.vocab import (
    CalendarDirection as CalendarDirection,
)
from ...core.vocab import (
    CalendarStatus as CalendarStatus,
)
from ...core.vocab import (
    ExerciseKind as ExerciseKind,
)
from ...core.vocab import (
    ItemFlag as ItemFlag,
)
from ...core.vocab import (
    PlanItemKind as PlanItemKind,
)
from ...core.vocab import (
    PlanItemOrigin as PlanItemOrigin,
)
from ...core.vocab import (
    QuestionType as QuestionType,
)
from ...core.vocab import (
    StudySessionKind as StudySessionKind,
)
from ...core.vocab import (
    StudySessionSource as StudySessionSource,
)
from ..payloads import (
    ActivityConfig,
    ActivityGeneratedFrom,
    AnswerResponse,
    AttemptMeta,
    BlockList,
    CalendarLinkOptions,
    DetectionSpec,
    DistractorMisconceptions,
    ExerciseContextList,
    ExerciseCreatedFrom,
    ExpectedAnswer,
    FeedbackList,
    HelpEventList,
    QuestionAnswer,
    QuestionProvenance,
    QuestionStats,
    RubricDocument,
    StepResponse,
    StepState,
    StringList,
    SympyCheck,
)
from ..schema_contract import vocab_check as vocab_check
from .core import (
    _UUID as _UUID,
)
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
    Date as Date,
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
    date as date,
)
from .core import (
    datetime as datetime,
)
from .core import (
    mapped_column as mapped_column,
)
from .core import (
    new_uuid as new_uuid,
)
from .core import (
    relationship as relationship,
)
from .core import (
    text as text,
)
from .core import (
    utcnow as utcnow,
)


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["node_id", "course_id"],
            ["tree_nodes.id", "tree_nodes.course_id"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    profile_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str | None] = mapped_column(_UUID)
    type: Mapped[str] = mapped_column(String(20), default="quiz")
    title: Mapped[str] = mapped_column(String(300))
    time_limit_sec: Mapped[int | None] = mapped_column(Integer)
    config: Mapped[ActivityConfig | None] = mapped_column(JSON)
    generated_from: Mapped[ActivityGeneratedFrom | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    questions: Mapped[list["Question"]] = relationship(
        back_populates="activity", order_by="Question.id", cascade="all, delete-orphan"
    )
    attempts: Mapped[list["Attempt"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        vocab_check("flag", ItemFlag),
        vocab_check("type", QuestionType),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    activity_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("activities.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[str | None] = mapped_column(
        _UUID, ForeignKey("questions.id", ondelete="CASCADE")
    )
    type: Mapped[str] = mapped_column(String(20))
    stem: Mapped[BlockList] = mapped_column(JSON)
    options: Mapped[BlockList | None] = mapped_column(JSON)
    answer: Mapped[QuestionAnswer] = mapped_column(JSON)
    explanation: Mapped[BlockList | None] = mapped_column(JSON)
    difficulty: Mapped[float | None] = mapped_column(Float)
    bloom: Mapped[str | None] = mapped_column(String(20))
    skill: Mapped[str | None] = mapped_column(String(20))
    concept_ids: Mapped[StringList | None] = mapped_column(JSON)
    expected_time_sec: Mapped[int | None] = mapped_column(Integer)
    curriculum_code: Mapped[str | None] = mapped_column(String(120))
    source_refs: Mapped[StringList | None] = mapped_column(JSON)
    distractor_misconceptions: Mapped[DistractorMisconceptions | None] = mapped_column(JSON)
    sympy_check: Mapped[SympyCheck | None] = mapped_column(JSON)
    input_modes: Mapped[StringList | None] = mapped_column(JSON)
    tags: Mapped[StringList | None] = mapped_column(JSON)
    provenance: Mapped[QuestionProvenance | None] = mapped_column(JSON)
    flag: Mapped[str] = mapped_column(String(10), default="ok")
    stats: Mapped[QuestionStats | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    activity: Mapped[Activity] = relationship(back_populates="questions")


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (vocab_check("mode", AttemptMode),)

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    activity_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("activities.id", ondelete="CASCADE"), index=True
    )
    mode: Mapped[str] = mapped_column(String(10), default="practice")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[float | None] = mapped_column(Float)
    meta: Mapped[AttemptMeta | None] = mapped_column(JSON)

    activity: Mapped[Activity] = relationship(back_populates="attempts")
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    attempt_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("attempts.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    response: Mapped[AnswerResponse | None] = mapped_column(JSON)
    input_mode: Mapped[str | None] = mapped_column(String(10))
    correct: Mapped[bool | None] = mapped_column(Boolean)
    partial_credit: Mapped[float | None] = mapped_column(Float)
    feedback: Mapped[FeedbackList | None] = mapped_column(JSON)
    graded_by: Mapped[str | None] = mapped_column(String(10))
    time_ms: Mapped[int | None] = mapped_column(Integer)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    error_tags: Mapped[StringList | None] = mapped_column(JSON)
    help_events: Mapped[HelpEventList | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    attempt: Mapped[Attempt] = relationship(back_populates="answers")


class Mistake(Base):
    __tablename__ = "mistakes"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    profile_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    concept_ids: Mapped[StringList | None] = mapped_column(JSON)
    error_tags: Mapped[StringList | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Exercise(Base):
    __tablename__ = "exercises"
    __table_args__ = (
        ForeignKeyConstraint(
            ["node_id", "course_id"],
            ["tree_nodes.id", "tree_nodes.course_id"],
            ondelete="CASCADE",
        ),
        vocab_check("kind", ExerciseKind),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    profile_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str | None] = mapped_column(_UUID)
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(30), default="multi_step")
    deck_ref: Mapped[str | None] = mapped_column(String(200))
    external_uid: Mapped[str | None] = mapped_column(String(200), index=True)
    context: Mapped[ExerciseContextList | None] = mapped_column(JSON)
    difficulty: Mapped[float | None] = mapped_column(Float)
    created_from: Mapped[ExerciseCreatedFrom | None] = mapped_column(JSON)
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

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    exercise_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("exercises.id", ondelete="CASCADE"), index=True
    )
    order_idx: Mapped[int] = mapped_column(Integer)
    prompt: Mapped[BlockList] = mapped_column(JSON)
    expected: Mapped[ExpectedAnswer | None] = mapped_column(JSON)
    hints_pregenerated: Mapped[BlockList | None] = mapped_column(JSON)
    rubric: Mapped[RubricDocument | None] = mapped_column(JSON)

    exercise: Mapped[Exercise] = relationship(back_populates="steps")


class ExerciseSession(Base):
    __tablename__ = "exercise_sessions"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    exercise_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("exercises.id", ondelete="CASCADE"), index=True
    )
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

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("exercise_sessions.id", ondelete="CASCADE"), index=True
    )
    step_idx: Mapped[int] = mapped_column(Integer)
    response: Mapped[StepResponse | None] = mapped_column(JSON)
    correct: Mapped[bool | None] = mapped_column(Boolean)
    hint_level_used: Mapped[int | None] = mapped_column(Integer)
    error_class: Mapped[str | None] = mapped_column(String(30))
    feedback: Mapped[FeedbackList | None] = mapped_column(JSON)
    state: Mapped[StepState | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[ExerciseSession] = relationship(back_populates="attempts")


class QuizHelpEvent(Base):
    __tablename__ = "quiz_help_events"
    __table_args__ = (Index("ix_quiz_help_events_attempt_question", "attempt_id", "question_id"),)

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    attempt_id: Mapped[str] = mapped_column(_UUID, ForeignKey("attempts.id", ondelete="CASCADE"))
    question_id: Mapped[str] = mapped_column(_UUID, ForeignKey("questions.id", ondelete="CASCADE"))
    level: Mapped[int] = mapped_column(Integer)
    markdown: Mapped[str] = mapped_column(Text)
    violations: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FsrsState(Base):
    __tablename__ = "fsrs_states"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    card_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("exercises.id", ondelete="CASCADE"), index=True, unique=True
    )
    state: Mapped[str] = mapped_column(String(20), default="new")
    stability: Mapped[float | None] = mapped_column(Float)
    difficulty: Mapped[float | None] = mapped_column(Float)
    reps: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    card: Mapped["Exercise"] = relationship(foreign_keys=[card_id], back_populates="fsrs_state")


class ReviewLog(Base):
    __tablename__ = "review_log"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    card_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("exercises.id", ondelete="CASCADE"), index=True
    )
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

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    key: Mapped[str] = mapped_column(String(80))
    course_type_id: Mapped[str | None] = mapped_column(
        _UUID, ForeignKey("course_types.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    example: Mapped[str | None] = mapped_column(Text)
    detection: Mapped[DetectionSpec | None] = mapped_column(JSON)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    order_idx: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StudySession(Base):
    __tablename__ = "study_sessions"
    __table_args__ = (
        Index("ix_study_sessions_profile_started", "profile_id", "started_at"),
        vocab_check("kind", StudySessionKind),
        vocab_check("source", StudySessionSource),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    profile_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[str | None] = mapped_column(
        _UUID, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str | None] = mapped_column(_UUID)
    kind: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(10))
    entity_ref: Mapped[str | None] = mapped_column(String(120))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_beat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    duration_sec: Mapped[int] = mapped_column(Integer, default=0)


class PlanItem(Base):
    __tablename__ = "plan_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["node_id", "course_id"],
            ["tree_nodes.id", "tree_nodes.course_id"],
            ondelete="CASCADE",
        ),
        Index("ix_plan_items_course_due", "course_id", "due_date"),
        Index("ix_plan_items_profile_due", "profile_id", "due_date"),
        Index(
            "uq_plan_items_course_external_uid",
            "course_id",
            "external_uid",
            unique=True,
            sqlite_where=text("external_uid IS NOT NULL"),
            postgresql_where=text("external_uid IS NOT NULL"),
        ),
        vocab_check("kind", PlanItemKind),
        vocab_check("origin", PlanItemOrigin),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    profile_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str | None] = mapped_column(_UUID)
    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[str | None] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(20), default="study", server_default="study")
    due_date: Mapped[date] = mapped_column(Date)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    origin: Mapped[str] = mapped_column(String(20), default="manual", server_default="manual")
    sort_key: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    external_uid: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CalendarLink(Base):
    """One bound cloud-calendar account for a course (ADR-0052).

    A link is a *credential binding*, not an identity: tokens live only in
    the OS keyring under ``calendar:<id>:<slot>`` and ``secret_ref`` is a
    pointer. The row carries the calendar's location, direction and visible
    sync health; plan-item joins use ``plan_items.external_uid`` (the remote
    event UID), never a token or an email.
    """

    __tablename__ = "calendar_links"
    __table_args__ = (
        Index("ix_calendar_links_profile", "profile_id"),
        Index(
            "uq_calendar_links_course_calendar",
            "course_id",
            "provider",
            "calendar_id",
            unique=True,
        ),
        vocab_check("direction", CalendarDirection),
        vocab_check("status", CalendarStatus),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    profile_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    auth_kind: Mapped[str] = mapped_column(String(20), default="none")
    label: Mapped[str] = mapped_column(String(200))
    account_label: Mapped[str | None] = mapped_column(String(200))
    calendar_id: Mapped[str | None] = mapped_column(String(512))
    calendar_url: Mapped[str | None] = mapped_column(String(2048))
    base_url: Mapped[str | None] = mapped_column(String(2048))
    scopes: Mapped[StringList | None] = mapped_column(JSON)
    secret_ref: Mapped[str | None] = mapped_column(String(200))
    direction: Mapped[str] = mapped_column(String(20), default="push", server_default="push")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    status: Mapped[str] = mapped_column(
        String(20), default="needs-auth", server_default="needs-auth"
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sync_cursor: Mapped[str | None] = mapped_column(String(1024))
    options: Mapped[CalendarLinkOptions | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CalendarEventLink(Base):
    """Remote identity for one local plan item on one calendar link.

    The link row is the join key between a plan item and the provider's event
    (stable UID, remote id, etag) plus a change pin per side: `local_hash`
    and `remote_hash` are the hash of the LOCAL and REMOTE content as last
    reconciled. A single shared hash cannot work — providers normalize on
    write, so one hash reads back as "changed" on every run. It is kept when a
    plan item disappears — that is how the next sync learns the local side was
    deleted instead of re-creating it.
    """

    __tablename__ = "calendar_event_links"
    __table_args__ = (
        Index("uq_calendar_event_links_link_uid", "link_id", "uid", unique=True),
        Index("ix_calendar_event_links_local", "link_id", "local_id"),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True, default=new_uuid)
    link_id: Mapped[str] = mapped_column(
        _UUID, ForeignKey("calendar_links.id", ondelete="CASCADE"), index=True
    )
    local_id: Mapped[str] = mapped_column(String(64))
    uid: Mapped[str] = mapped_column(String(200))
    remote_id: Mapped[str | None] = mapped_column(String(2048))
    etag: Mapped[str | None] = mapped_column(String(256))
    local_hash: Mapped[str | None] = mapped_column(String(64))
    remote_hash: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
