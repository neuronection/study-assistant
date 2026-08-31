from datetime import UTC as UTC
from datetime import date as date
from datetime import datetime as datetime
from typing import Any as Any
from uuid import uuid4 as uuid4

from sqlalchemy import (
    JSON as JSON,
)
from sqlalchemy import (
    Boolean as Boolean,
)
from sqlalchemy import (
    CheckConstraint as CheckConstraint,
)
from sqlalchemy import (
    Date as Date,
)
from sqlalchemy import (
    DateTime as DateTime,
)
from sqlalchemy import (
    Float as Float,
)
from sqlalchemy import (
    ForeignKey as ForeignKey,
)
from sqlalchemy import (
    ForeignKeyConstraint as ForeignKeyConstraint,
)
from sqlalchemy import (
    Index as Index,
)
from sqlalchemy import (
    Integer as Integer,
)
from sqlalchemy import (
    String as String,
)
from sqlalchemy import (
    Text as Text,
)
from sqlalchemy import (
    UniqueConstraint as UniqueConstraint,
)
from sqlalchemy import (
    text as text,
)
from sqlalchemy.orm import Mapped as Mapped
from sqlalchemy.orm import mapped_column as mapped_column
from sqlalchemy.orm import relationship as relationship

from ...storage.db import Base as Base


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

class CourseType(Base):
    __tablename__ = "course_types"
    __table_args__ = (Index("uq_course_types_key", "key", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
