from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field, field_validator

from ..core.vocab import (
    DecisionTransport,
    MaterialKind,
    MaterialStatus,
    applicable_extraction_modes,
)

MODEL_CAPS = ("text", "vision", "tools", "embeddings", "stt", "tts", "decision")


def _validate_decision_transport(value: str | None) -> str | None:
    """The decision transport seam (D2): one shipping transport today —
    anything else is a data error, never silently coerced."""
    if value is None:
        return value
    if value != DecisionTransport.SYSTEMONE.value:
        raise ValueError(f"unknown decision transport: {value}")
    return value


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    db: Literal["ok"]


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    course_id: int
    parent_id: int | None = None


class FolderRename(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class FolderMove(BaseModel):
    parent_id: int | None


class FolderOut(BaseModel):
    id: int
    name: str
    path: str
    course_id: int
    parent_id: int | None
    source_id: int | None = None
    created_at: datetime
    node_link_count: int = 0


class ProviderCreate(BaseModel):
    is_local: bool | None = None
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    name: str = Field(min_length=1, max_length=120)
    # `decision` = decision-typed providers (ADR-0032: the typesafe preset's
    # wire type); models added under one default to the decision capability.
    type: str = Field(pattern="^(google|openai_compatible|anthropic|decision)$")
    base_url: str | None = None
    api_key: str | None = None


class ProviderUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    enabled: bool | None = None
    api_key: str | None = None
    is_local: bool | None = None
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")


class RemoteModelOut(BaseModel):
    external_id: str
    caps: list[str]


class ModelCreateIn(BaseModel):
    provider_id: int
    external_id: str = Field(min_length=1, max_length=300)
    label: str | None = Field(default=None, max_length=300)
    caps: list[str] | None = None
    enabled: bool = True
    reasoning_effort: str | None = Field(default=None, max_length=20)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    decision_transport: str | None = Field(default=None, max_length=20)

    @field_validator("caps")
    @classmethod
    def caps_within_vocabulary(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        unknown = [cap for cap in value if cap not in MODEL_CAPS]
        if unknown:
            raise ValueError(f"unknown caps: {', '.join(unknown)}")
        return value

    @field_validator("decision_transport")
    @classmethod
    def transport_within_vocabulary(cls, value: str | None) -> str | None:
        return _validate_decision_transport(value)


class ProviderOut(BaseModel):
    id: int
    name: str
    type: str
    base_url: str
    preset_key: str | None = None
    enabled: bool
    is_local: bool | None = None
    country: str | None = None
    masked_key: str | None
    status: dict[str, Any] | None
    created_at: datetime


class ModelOut(BaseModel):
    id: int
    provider_id: int
    external_id: str
    label: str
    caps: list[str]
    decision_transport: str | None = None
    enabled: bool
    missing: bool
    reasoning_effort: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class ModelUpdate(BaseModel):
    label: str | None = None
    enabled: bool | None = None
    caps: list[str] | None = None
    reasoning_effort: str | None = Field(default=None, max_length=20)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    decision_transport: str | None = Field(default=None, max_length=20)

    @field_validator("decision_transport")
    @classmethod
    def transport_within_vocabulary(cls, value: str | None) -> str | None:
        return _validate_decision_transport(value)

    @field_validator("caps")
    @classmethod
    def caps_within_vocabulary(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        unknown = [cap for cap in value if cap not in MODEL_CAPS]
        if unknown:
            raise ValueError(f"unknown caps: {', '.join(unknown)}")
        return value


class TaskAssignmentIn(BaseModel):
    model_id: int | None = None
    fallback_model_id: int | None = None


class TaskOut(BaseModel):
    task: str
    description: str
    requires: str
    model_id: int | None
    fallback_model_id: int | None
    model_label: str | None
    fallback_model_label: str | None
    inherits_default: bool = False
    default_model_label: str | None = None
    # ADR-0037: capability defaults are single-slot — no inherited-fallback
    # label; the prior `default_fallback_model_label` is removed.
    monthly_cap_usd: float | None = None


class DefaultTaskOut(BaseModel):
    requires: str
    model_id: int | None
    # Fallback stays on the wire for the decision kind override rows this
    # endpoint also serves (ADR-0037); capability rows always carry null.
    fallback_model_id: int | None
    model_label: str | None
    fallback_model_label: str | None
    # ADR-0036 §4: the model a decision kind inherits when its picker's
    # labeled null option is chosen (the `decision` default resolution).
    # Populated for decision:<kind> rows only.
    resolved_inherit_label: str | None = None


class CourseTaskOut(BaseModel):
    task: str
    description: str
    requires: str
    model_id: int | None
    fallback_model_id: int | None
    model_label: str | None
    fallback_model_label: str | None
    global_model_label: str | None
    global_fallback_model_label: str | None


class CourseDefaultTaskOut(BaseModel):
    # ADR-0037: course capability defaults are single-slot — no fallback
    # fields; the inherited view is the global default's primary.
    requires: str
    model_id: int | None
    model_label: str | None
    global_model_label: str | None


class MaterialOut(BaseModel):
    id: int
    title: str
    description: str | None = None
    kind: MaterialKind
    status: MaterialStatus
    filename: str
    mime: str | None
    pages: int | None
    course_id: int
    group_id: int | None
    folder_id: int | None
    blob_sha: str | None
    provenance: dict[str, Any] | None = None
    created_at: datetime
    source_url: str | None = None
    has_extraction: bool = False
    tags: list[str] = []
    starred: bool = False
    link_count: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def reextract_modes(self) -> list[str]:
        return [mode.value for mode in applicable_extraction_modes(self.kind)]


class UploadWarningOut(BaseModel):
    code: str
    limit_mb: int | None = None
    file_mb: float | None = None


class MaterialJobOut(BaseModel):
    job_id: int


class MaterialUploadOut(BaseModel):
    material: MaterialOut
    job_id: int | None
    deduped: bool
    node_id: int | None = None
    warnings: list[UploadWarningOut] = Field(default_factory=list)


class ExtractionOut(BaseModel):
    id: int
    material_id: int
    version: int
    extractor: str
    markdown: str
    blocks: list[dict[str, Any]]


class ViewBox(BaseModel):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    width: float = Field(gt=0, allow_inf_nan=False)
    height: float = Field(gt=0, allow_inf_nan=False)


class DrawingOut(BaseModel):
    id: int
    png_sha: str | None
    strokes: list[dict[str, Any]]
    view: ViewBox | None = None
    ocr_version: int
    ocr_markdown: str | None
    ocr_job_id: int | None = None
    created_at: datetime


class DrawingIn(BaseModel):
    strokes: list[dict[str, Any]] = Field(min_length=1)
    png_base64: str = Field(min_length=1)
    view: ViewBox | None = None
    ocr: bool = True


class IndexCardOut(BaseModel):
    reading_minutes: int | None
    summary: str | None
    topics: list[str]
    key_terms: list[str] | None = None
    difficulty: int | None = None


class MaterialImageOut(BaseModel):
    id: int
    position: int
    blob_sha: str | None
    mime: str | None
    ocr_version: int
    ocr_markdown: str | None
    ocr_job_id: int | None = None
    created_at: datetime


class MaterialDetailOut(BaseModel):
    material: MaterialOut
    extraction: ExtractionOut | None
    index_card: IndexCardOut | None
    drawings: list[DrawingOut] = Field(default_factory=list)
    images: list[MaterialImageOut] = Field(default_factory=list)


class SearchHitNode(BaseModel):
    course_id: int
    node_id: int
    node_title: str


class SearchHit(BaseModel):
    material_id: int
    title: str
    snippet: str
    score: float | None = None
    nodes: list[SearchHitNode] = []


class SearchOut(BaseModel):
    query: str
    hits: list[SearchHit]


class ExtractionEdit(BaseModel):
    markdown: str = Field(min_length=1)
