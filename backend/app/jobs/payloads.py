from typing import Required, TypedDict


class IngestPayload(TypedDict, total=False):
    material_id: Required[int]
    blob_sha: str | None


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
