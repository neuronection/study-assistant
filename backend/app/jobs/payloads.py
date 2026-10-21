from typing import Required, TypedDict


class IngestPayload(TypedDict, total=False):
    material_id: Required[str]
    blob_sha: str | None
    mode: str


class PostprocessPayload(TypedDict, total=False):
    material_id: Required[str]
    old_chunk_ids: list[str]
    extraction_id: str


class ChatTurnPayload(TypedDict):
    chat_session_id: str
    user_message_id: str


class DrawingOcrPayload(TypedDict, total=False):
    kind: Required[str]
    drawing_id: Required[str]
    note_id: str
    material_id: str


class ImageOcrPayload(TypedDict, total=False):
    image_id: Required[str]
    material_id: Required[str]


class GenesisPayload(TypedDict, total=False):
    course_id: Required[str]
    lessons: bool
    quizzes: bool
    flashcards: bool


class UrlImportPayload(TypedDict, total=False):
    material_id: Required[str]
    action: str


class ComposePayload(TypedDict, total=False):
    course_id: Required[str]
    profile_id: str | None
    node_id: str | None
    kind: str | None
    title: str | None
    instructions: str | None
    extra_md: str | None
    scope: str | None
    include_material_ids: list[str] | None
    exclude_material_ids: list[str] | None
    note_ids: list[str] | None
    concept_ids: list[str] | None
    context_hint: str | None
    regenerate: bool | None
    include_unassigned: bool | None
    material_id: str | None
