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
    text as text,
)
from .core import (
    utcnow as utcnow,
)


class Blob(Base):
    __tablename__ = "blobs"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    rel_path: Mapped[str] = mapped_column(String(500))
    size: Mapped[int] = mapped_column(Integer)
    mime: Mapped[str | None] = mapped_column(String(120))
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
