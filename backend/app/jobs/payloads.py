from typing import Required, TypedDict


class IngestPayload(TypedDict, total=False):
    material_id: Required[int]
    blob_sha: str | None
    mode: str


class PostprocessPayload(TypedDict, total=False):
    material_id: Required[int]
    old_chunk_ids: list[int]
    extraction_id: int


class ChatTurnPayload(TypedDict):
    chat_session_id: int
    user_message_id: int


class DrawingOcrPayload(TypedDict, total=False):
    kind: Required[str]
    drawing_id: Required[int]
    note_id: int
    material_id: int


class ImageOcrPayload(TypedDict, total=False):
    image_id: Required[int]
    material_id: Required[int]


class GenesisPayload(TypedDict, total=False):
    course_id: Required[int]
    lessons: bool
    quizzes: bool
    flashcards: bool


class UrlImportPayload(TypedDict, total=False):
    material_id: Required[int]
    action: str


class ComposePayload(TypedDict, total=False):
    course_id: Required[int]
    profile_id: int | None
    node_id: int | None
    kind: str | None
    title: str | None
    instructions: str | None
    extra_md: str | None
    scope: str | None
    include_material_ids: list[int] | None
    exclude_material_ids: list[int] | None
    note_ids: list[int] | None
    concept_ids: list[int] | None
    context_hint: str | None
    regenerate: bool | None
    include_unassigned: bool | None
    material_id: int | None
