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


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str | None] = mapped_column(String(120))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(30))
    base_url: Mapped[str] = mapped_column(String(300))
    keyring_ref: Mapped[str] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class AiModel(Base):
    __tablename__ = "models"
    __table_args__ = (
        Index("uq_models_provider_external", "provider_id", "external_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(200))
    label: Mapped[str] = mapped_column(String(200))
    caps: Mapped[list[str]] = mapped_column(JSON)
    ctx_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_in: Mapped[float | None] = mapped_column(Float)
    cost_out: Mapped[float | None] = mapped_column(Float)
    reasoning_effort: Mapped[str | None] = mapped_column(String(20))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    missing: Mapped[bool] = mapped_column(Boolean, default=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class TaskAssignment(Base):
    __tablename__ = "task_assignments"

    task: Mapped[str] = mapped_column(String(40), primary_key=True)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id"))
    fallback_model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id"))
    params: Mapped[dict[str, Any] | None] = mapped_column(JSON)

class DefaultTaskAssignment(Base):
    __tablename__ = "default_task_assignments"

    requires: Mapped[str] = mapped_column(String(40), primary_key=True)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id"))
    fallback_model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id"))

class CourseTaskAssignment(Base):
    __tablename__ = "course_task_assignments"

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id"), primary_key=True
    )
    task: Mapped[str] = mapped_column(String(40), primary_key=True)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id"))
    fallback_model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id"))

class CourseDefaultTaskAssignment(Base):
    __tablename__ = "course_default_task_assignments"

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id"), primary_key=True
    )
    requires: Mapped[str] = mapped_column(String(40), primary_key=True)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id"))
    fallback_model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id"))

class DeletedItem(Base):
    __tablename__ = "deleted_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    purge_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class ConceptSkillStat(Base):
    __tablename__ = "concept_skill_stats"
    __table_args__ = (
        Index("uq_concept_skill_stats", "profile_id", "concept", "skill", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))
    concept: Mapped[str] = mapped_column(String(200))
    concept_id: Mapped[int | None] = mapped_column(Integer)
    skill: Mapped[str] = mapped_column(String(20))
    n: Mapped[int] = mapped_column(Integer)
    accuracy: Mapped[float] = mapped_column(Float)
    avg_time_ratio: Mapped[float | None] = mapped_column(Float)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    weakness_score: Mapped[float] = mapped_column(Float)

class DailyRollup(Base):
    __tablename__ = "daily_rollups"
    __table_args__ = (Index("uq_daily_rollups", "profile_id", "day", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))
    day: Mapped[str] = mapped_column(String(10))
    answers_n: Mapped[int] = mapped_column(Integer)
    correct_n: Mapped[int] = mapped_column(Integer)
    cards_reviewed: Mapped[int] = mapped_column(Integer)
    minutes: Mapped[float] = mapped_column(Float)
    xp: Mapped[int] = mapped_column(Integer)

class ItemStat(Base):
    __tablename__ = "item_stats"
    __table_args__ = (Index("uq_item_stats", "question_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    n_attempts: Mapped[int] = mapped_column(Integer)
    p_correct: Mapped[float] = mapped_column(Float)
    avg_time_ms: Mapped[float | None] = mapped_column(Float)
    avg_time_ratio: Mapped[float | None] = mapped_column(Float)
    distractor_selection: Mapped[dict[str, int] | None] = mapped_column(JSON)
    flag: Mapped[str] = mapped_column(String(10), default="ok")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class StudyGoal(Base):
    __tablename__ = "study_goals"

    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id"), primary_key=True
    )
    answers_per_day: Mapped[int] = mapped_column(Integer, default=20)

class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (Index("uq_skills_key", "key", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task: Mapped[str] = mapped_column(String(40))
    key: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    versions: Mapped[list["SkillVersion"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )

class SkillVersion(Base):
    __tablename__ = "skill_versions"
    __table_args__ = (
        Index(
            "uq_skill_versions",
            "skill_id",
            "scope_type",
            "scope_ref",
            "version",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"))
    scope_type: Mapped[str] = mapped_column(String(20))
    scope_ref: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer)
    system_template: Mapped[str] = mapped_column(Text)
    user_template: Mapped[str] = mapped_column(Text)
    params: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    contract: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    skill: Mapped[Skill] = relationship(back_populates="versions")

class AiInteraction(Base):
    __tablename__ = "ai_interactions"
    __table_args__ = (
        Index("ix_ai_interactions_context", "context_type", "context_id"),
        Index("ix_ai_interactions_task", "task"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    context_type: Mapped[str] = mapped_column(String(30))
    context_id: Mapped[int | None] = mapped_column(Integer)
    direction: Mapped[str | None] = mapped_column(Text)
    task: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(200))
    skill_version_id: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
