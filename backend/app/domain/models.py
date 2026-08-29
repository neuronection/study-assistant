from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..storage.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    color: Mapped[str | None] = mapped_column(String(16))
    preferences: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(String(120))
    level: Mapped[str | None] = mapped_column(String(120))
    goals: Mapped[list[str] | None] = mapped_column(JSON)
    tags: Mapped[list[str] | None] = mapped_column(JSON)
    color: Mapped[str | None] = mapped_column(String(16))
    exam_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    course_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_types.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Blob(Base):
    __tablename__ = "blobs"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    rel_path: Mapped[str] = mapped_column(String(500))
    size: Mapped[int] = mapped_column(Integer)
    mime: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MaterialGroup(Base):
    __tablename__ = "material_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(30), default="image-set")
    order_idx: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TreeNode(Base):
    __tablename__ = "tree_nodes"
    __table_args__ = (
        Index("ix_tree_nodes_course_parent", "course_id", "parent_id"),
        Index("uq_tree_nodes_path", "path", unique=True),
        UniqueConstraint("id", "course_id", name="uq_tree_nodes_id_course"),
        Index("uq_tree_nodes_root", "course_id", unique=True, sqlite_where=text("is_root = 1")),
        ForeignKeyConstraint(
            ["parent_id", "course_id"], ["tree_nodes.id", "tree_nodes.course_id"]
        ),
        CheckConstraint("depth >= 0 AND depth <= 4", name="ck_tree_nodes_depth"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str | None] = mapped_column(Text)
    objectives: Mapped[list[str] | None] = mapped_column(JSON)
    ai_hint: Mapped[str | None] = mapped_column(Text)
    order_idx: Mapped[int] = mapped_column(Integer, default=0)
    depth: Mapped[int] = mapped_column(Integer, default=1)
    path: Mapped[str] = mapped_column(String(500), default="/")
    sort_path: Mapped[str] = mapped_column(String(1000), default="/")
    is_root: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Concept(Base):
    __tablename__ = "concepts"
    __table_args__ = (
        Index("uq_concepts_course_name", "course_id", "name", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    aliases: Mapped[list[str] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


CONCEPT_RELATIONS = ("prereq-of", "part-of", "related-to")


class ConceptLink(Base):
    __tablename__ = "concept_links"
    __table_args__ = (
        Index(
            "uq_concept_links_triple",
            "from_concept_id",
            "to_concept_id",
            "relation",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    from_concept_id: Mapped[int] = mapped_column(ForeignKey("concepts.id"))
    to_concept_id: Mapped[int] = mapped_column(ForeignKey("concepts.id"))
    relation: Mapped[str] = mapped_column(String(30))

    from_concept: Mapped[Concept] = relationship(foreign_keys=[from_concept_id])
    to_concept: Mapped[Concept] = relationship(foreign_keys=[to_concept_id])


class NodeConcept(Base):
    __tablename__ = "node_concepts"
    __table_args__ = (Index("uq_node_concepts", "node_id", "concept_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("tree_nodes.id"), index=True)
    concept_id: Mapped[int] = mapped_column(ForeignKey("concepts.id"))
    weight: Mapped[float | None] = mapped_column(Float)


class MaterialLink(Base):
    __tablename__ = "material_links"
    __table_args__ = (
        Index("uq_material_links_node", "node_id", "material_id", unique=True),
        Index("ix_material_links_node", "node_id"),
        ForeignKeyConstraint(
            ["node_id", "course_id"], ["tree_nodes.id", "tree_nodes.course_id"]
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    node_id: Mapped[int] = mapped_column(Integer)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    extraction_id: Mapped[int | None] = mapped_column(ForeignKey("extractions.id"))
    rationale: Mapped[str | None] = mapped_column(Text)
    auto_assigned: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    material: Mapped["Material"] = relationship()


class MaterialFolderLink(Base):
    __tablename__ = "material_folder_links"
    __table_args__ = (
        Index(
            "uq_material_folder_links_node", "node_id", "folder_id", unique=True
        ),
        Index("ix_material_folder_links_node", "node_id"),
        ForeignKeyConstraint(
            ["node_id", "course_id"], ["tree_nodes.id", "tree_nodes.course_id"]
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    node_id: Mapped[int] = mapped_column(Integer)
    folder_id: Mapped[int] = mapped_column(
        ForeignKey("material_folders.id"), index=True
    )
    rationale: Mapped[str | None] = mapped_column(Text)
    auto_assigned: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    folder: Mapped["MaterialFolder"] = relationship()


class MaterialStudyState(Base):
    __tablename__ = "material_study_state"
    __table_args__ = (
        Index("uq_material_study_state", "material_id", "profile_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="unread")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MaterialFolder(Base):
    __tablename__ = "material_folders"
    __table_args__ = (
        Index(
            "uq_material_folders_profile_course_path",
            "profile_id",
            "course_id",
            "path",
            unique=True,
        ),
        Index("uq_material_folders_source_id", "source_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("material_folders.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    path: Mapped[str] = mapped_column(String(1000))
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_sources.id"), unique=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Material(Base):
    __tablename__ = "materials"
    __table_args__ = (Index("ix_materials_course_status", "course_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("material_groups.id"), index=True)
    folder_id: Mapped[int | None] = mapped_column(ForeignKey("material_folders.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(300))
    blob_sha: Mapped[str | None] = mapped_column(ForeignKey("blobs.sha256"))
    filename: Mapped[str] = mapped_column(String(500))
    mime: Mapped[str | None] = mapped_column(String(120))
    pages: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    phash: Mapped[str | None] = mapped_column(String(24))
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source_id: Mapped[int | None] = mapped_column(Integer)
    external_path: Mapped[str | None] = mapped_column(String(1000))
    file_mtime: Mapped[float | None] = mapped_column(Float)
    file_size: Mapped[int | None] = mapped_column(Integer)

    extractions: Mapped[list["Extraction"]] = relationship(
        back_populates="material",
        order_by="Extraction.version",
        passive_deletes=True,
    )
    drawings: Mapped[list["MaterialDrawing"]] = relationship(
        back_populates="material", cascade="all, delete-orphan"
    )


class Extraction(Base):
    __tablename__ = "extractions"

    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    extractor: Mapped[str] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(120))
    blocks: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    markdown: Mapped[str] = mapped_column(Text)
    confidence: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    language: Mapped[str | None] = mapped_column(String(10))
    token_in: Mapped[int | None] = mapped_column(Integer)
    token_out: Mapped[int | None] = mapped_column(Integer)
    cost: Mapped[float | None] = mapped_column(Float)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    edited_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    material: Mapped[Material] = relationship(back_populates="extractions")
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="extraction", order_by="Chunk.ordinal"
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    extraction_id: Mapped[int] = mapped_column(ForeignKey("extractions.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int | None] = mapped_column(Integer)

    extraction: Mapped[Extraction] = relationship(back_populates="chunks")


class MaterialDrawing(Base):
    __tablename__ = "material_drawings"

    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    strokes: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    png_sha: Mapped[str | None] = mapped_column(ForeignKey("blobs.sha256"))
    view: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    ocr_version: Mapped[int] = mapped_column(Integer, default=0)
    ocr_blocks: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    ocr_markdown: Mapped[str | None] = mapped_column(Text)
    ocr_job_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    material: Mapped[Material] = relationship(back_populates="drawings")


class MaterialIndexCard(Base):
    __tablename__ = "material_index_cards"

    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.id"), primary_key=True
    )
    summary: Mapped[str | None] = mapped_column(Text)
    topics: Mapped[list[str] | None] = mapped_column(JSON)
    key_terms: Mapped[list[str] | None] = mapped_column(JSON)
    reading_minutes: Mapped[int | None] = mapped_column(Integer)
    difficulty: Mapped[int | None] = mapped_column(Integer)


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


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["node_id", "course_id"], ["tree_nodes.id", "tree_nodes.course_id"]
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), index=True)
    node_id: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300), default="New chat")
    use_embeddings: Mapped[bool | None] = mapped_column(Boolean)
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=lambda: str(uuid4())
    )
    context: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    mention_registry: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    active_root_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, index=True)
    active_child_id: Mapped[int | None] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(20))
    blocks: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    mentions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    reads: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    grounded: Mapped[bool | None] = mapped_column(Boolean)
    state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    warnings: Mapped[list[str] | None] = mapped_column(JSON)
    trace: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatProposal(Base):
    __tablename__ = "chat_proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("chat_messages.id"), index=True
    )
    action: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (
        Index("ix_notes_owner", "owner_type", "owner_id"),
        Index("ix_notes_node_id", "node_id"),
        ForeignKeyConstraint(
            ["node_id", "course_id"], ["tree_nodes.id", "tree_nodes.course_id"]
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    node_id: Mapped[int | None] = mapped_column(Integer)
    owner_type: Mapped[str] = mapped_column(String(30), default="standalone")
    owner_id: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    search_text: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list[str] | None] = mapped_column(JSON)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    drawings: Mapped[list["NoteDrawing"]] = relationship(
        back_populates="note", cascade="all, delete-orphan"
    )


class NoteDrawing(Base):
    __tablename__ = "note_drawings"

    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id"), index=True)
    strokes: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    png_sha: Mapped[str | None] = mapped_column(ForeignKey("blobs.sha256"))
    view: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    ocr_version: Mapped[int] = mapped_column(Integer, default=0)
    ocr_blocks: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    ocr_markdown: Mapped[str | None] = mapped_column(Text)
    ocr_job_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    note: Mapped[Note] = relationship(back_populates="drawings")


class NoteVersion(Base):
    __tablename__ = "note_versions"
    __table_args__ = (Index("ix_note_versions_note", "note_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), index=True
    )
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    tags: Mapped[list[str] | None] = mapped_column(JSON)
    body: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    cause: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DeletedItem(Base):
    __tablename__ = "deleted_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    purge_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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


class MaterialSource(Base):
    __tablename__ = "material_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    label: Mapped[str] = mapped_column(String(200))
    path: Mapped[str] = mapped_column(String(1000))
    recursive: Mapped[bool] = mapped_column(Boolean, default=True)
    include_globs: Mapped[list[str] | None] = mapped_column(JSON)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    scan_interval_sec: Mapped[int | None] = mapped_column(Integer)
    last_scan_error: Mapped[str | None] = mapped_column(Text)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CourseType(Base):
    __tablename__ = "course_types"
    __table_args__ = (Index("uq_course_types_key", "key", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)


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
