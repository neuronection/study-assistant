from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

MODEL_CAPS = ("text", "vision", "tools", "embeddings", "audio")


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


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(pattern="^(google|openai_compatible|anthropic)$")
    base_url: str | None = None
    api_key: str | None = None


class ProviderUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    enabled: bool | None = None
    api_key: str | None = None


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

    @field_validator("caps")
    @classmethod
    def caps_within_vocabulary(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        unknown = [cap for cap in value if cap not in MODEL_CAPS]
        if unknown:
            raise ValueError(f"unknown caps: {', '.join(unknown)}")
        return value


class ProviderOut(BaseModel):
    id: int
    name: str
    type: str
    base_url: str
    enabled: bool
    masked_key: str | None
    status: dict[str, Any] | None
    created_at: datetime


class ModelOut(BaseModel):
    id: int
    provider_id: int
    external_id: str
    label: str
    caps: list[str]
    enabled: bool
    missing: bool
    reasoning_effort: str | None = None


class ModelUpdate(BaseModel):
    label: str | None = None
    enabled: bool | None = None
    caps: list[str] | None = None
    reasoning_effort: str | None = Field(default=None, max_length=20)

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
    default_fallback_model_label: str | None = None
    monthly_cap_usd: float | None = None


class DefaultTaskOut(BaseModel):
    requires: str
    model_id: int | None
    fallback_model_id: int | None
    model_label: str | None
    fallback_model_label: str | None


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
    requires: str
    model_id: int | None
    fallback_model_id: int | None
    model_label: str | None
    fallback_model_label: str | None
    global_model_label: str | None
    global_fallback_model_label: str | None


class MaterialOut(BaseModel):
    id: int
    title: str
    kind: str
    status: str
    filename: str
    mime: str | None
    pages: int | None
    course_id: int
    group_id: int | None
    folder_id: int | None
    blob_sha: str | None
    provenance: dict[str, Any] | None = None
    created_at: datetime


class MaterialUploadOut(BaseModel):
    material: MaterialOut
    job_id: int | None
    deduped: bool


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


class MaterialDetailOut(BaseModel):
    material: MaterialOut
    extraction: ExtractionOut | None
    index_card: IndexCardOut | None
    drawings: list[DrawingOut] = Field(default_factory=list)


class SearchHit(BaseModel):
    material_id: int
    title: str
    snippet: str
    score: float | None = None


class SearchOut(BaseModel):
    query: str
    hits: list[SearchHit]


class ExtractionEdit(BaseModel):
    markdown: str = Field(min_length=1)
