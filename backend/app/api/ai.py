import re
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..ai.gateway import BudgetExceeded, ProviderError, TaskUnassigned
from ..ai.tools import CHAT_TOOL_CATALOG
from ..mcp_resources import MCP_INSTRUCTIONS, RESOURCE_TOOLS, create_resource_server
from ..services.knowledge.context import (
    ContextError,
    ContextParams,
    ContextResolver,
    ContextSpec,
)
from ..services.platform.editor_ai import (
    EDITOR_PRESETS,
    MAX_CONTEXT_CHARS,
    MAX_INSTRUCTION_CHARS,
    MAX_TEXT_CHARS,
    EditorTransformService,
)
from ..services.platform.skills import SkillService
from .deps import get_session

router = APIRouter(prefix="/ai", tags=["ai"])

MAX_AUDIO_BYTES = 25 * 1024 * 1024
_LANGUAGE_RE = re.compile(r"^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})?$")

MCP_TOOL_RESPONSE = (
    "JSON object with the requested rows; failures return {\"error\": …}."
)
CHAT_RESOURCE_SCOPE = (
    "Read-only — lists the learner's courses and node resources; also served "
    "to external agents via the MCP resource server."
)


class PreviewIn(ContextParams):
    course_id: int
    node_id: int | None = None
    query: str | None = Field(default=None, max_length=500)
    max_chunks: int = Field(default=12, ge=0, le=32)
    chunk_chars: int = Field(default=1000, ge=200, le=4000)


class PreviewOut(BaseModel):
    stats: dict[str, object]
    rendered: str


class EditorTransformIn(BaseModel):
    text: str = Field(default="", max_length=MAX_TEXT_CHARS)
    instruction: str = Field(default="", max_length=MAX_INSTRUCTION_CHARS)
    preset: str | None = None
    mode: Literal["transform", "write"] = "transform"
    include_context: bool = False
    context_document: str = Field(default="", max_length=MAX_CONTEXT_CHARS)
    ground_in_material: bool = False
    course_id: int | None = None
    node_id: int | None = None


class EditorTransformJobOut(BaseModel):
    job_id: int


class EditorTransformStatusOut(BaseModel):
    status: str
    result_md: str = ""
    error: str | None = None
    problems: list[str] = []
    rounds: int = 0


@router.post("/editor/transform", response_model=EditorTransformJobOut)
def editor_transform(
    body: EditorTransformIn,
    request: Request,
    session: Session = Depends(get_session),
) -> EditorTransformJobOut:
    if body.preset is not None and body.preset not in EDITOR_PRESETS:
        raise HTTPException(status_code=422, detail=f"unknown preset '{body.preset}'")
    if body.mode == "transform" and not body.text.strip():
        raise HTTPException(status_code=422, detail="text is required in transform mode")
    if body.ground_in_material and body.course_id is None:
        raise HTTPException(status_code=422, detail="ground_in_material requires course_id")
    context_material: str | None = None
    if body.ground_in_material:
        try:
            bundle = ContextResolver(session, request.app.state.embedder.embed).resolve(
                ContextSpec(
                    course_id=body.course_id or 0,
                    node_id=body.node_id,
                    query=body.text[:500] or None,
                    max_chunks=8,
                    chunk_chars=1000,
                )
            )
        except ContextError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        context_material = bundle.render_prompt()[:MAX_CONTEXT_CHARS]
    service: EditorTransformService = request.app.state.editor_ai
    job = service.start_transform(
        text=body.text,
        instruction=body.instruction,
        preset=body.preset,
        mode=body.mode,
        context_document=body.context_document if body.include_context else None,
        context_material=context_material,
        course_id=body.course_id,
        bus=request.app.state.bus,
    )
    return EditorTransformJobOut(job_id=job.id)


@router.get("/editor/jobs/{job_id}", response_model=EditorTransformStatusOut)
def editor_transform_job(job_id: int, request: Request) -> EditorTransformStatusOut:
    job = request.app.state.editor_ai.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="editor transform job not found")
    return EditorTransformStatusOut(
        status=job.status,
        result_md=job.result_md,
        error=job.error,
        problems=job.problems,
        rounds=job.rounds,
    )


class EditorCancelOut(BaseModel):
    cancelled: bool


@router.post("/editor/jobs/{job_id}/cancel", response_model=EditorCancelOut)
def editor_transform_cancel(job_id: int, request: Request) -> dict[str, bool]:
    cancelled = request.app.state.editor_ai.cancel_job(job_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="editor transform job not found or finished")
    return {"cancelled": True}


class TranscribeOut(BaseModel):
    text: str
    model: str


@router.post("/transcribe", response_model=TranscribeOut)
async def transcribe_audio(
    request: Request,
    file: Annotated[UploadFile, File()],
    language: Annotated[str | None, Form()] = None,
    session: Session = Depends(get_session),
) -> TranscribeOut:
    if language is not None:
        language = language.strip() or None
        if language is not None and not _LANGUAGE_RE.match(language):
            raise HTTPException(
                status_code=422,
                detail="language must be an ISO language code like 'en' or 'de'",
            )
    mime = (file.content_type or "").split(";")[0].strip().lower()
    if not mime.startswith("audio/") and mime != "video/webm":
        raise HTTPException(status_code=422, detail="file must be an audio recording")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="audio file is empty")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="audio file too large (max 25 MB)")
    version = SkillService(session).resolve("transcribe.audio")
    instruction = version.system_template if version is not None else None
    try:
        return await run_in_threadpool(
            request.app.state.gateway.transcribe,
            data,
            mime,
            language=language,
            instruction=instruction,
        )
    except TaskUnassigned as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except BudgetExceeded as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except ProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post("/context/preview", response_model=PreviewOut)
def preview_context(
    body: PreviewIn,
    request: Request,
    session: Session = Depends(get_session),
) -> PreviewOut:
    try:
        bundle = ContextResolver(session, request.app.state.embedder.embed).resolve(
            body.to_spec(
                course_id=body.course_id,
                node_id=body.node_id,
                query=body.query,
                max_chunks=body.max_chunks,
                chunk_chars=body.chunk_chars,
            )
        )
    except ContextError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return PreviewOut(stats=bundle.stats(), rendered=bundle.render_prompt()[:8000])


def _schema_arguments(schema: dict[str, Any]) -> list[dict[str, Any]]:
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    arguments: list[dict[str, Any]] = []
    for name, spec in properties.items():
        if isinstance(spec.get("anyOf"), list):
            variants = [
                str(variant.get("type"))
                for variant in spec["anyOf"]
                if isinstance(variant, dict) and variant.get("type") != "null"
            ]
            arg_type = variants[0] if variants else "any"
            if len(variants) > 1:
                arg_type = " | ".join(variants)
        else:
            arg_type = str(spec.get("type") or "any")
        arguments.append(
            {
                "name": name,
                "type": arg_type,
                "required": name in required,
                "description": spec.get("description"),
            }
        )
    return arguments


def _resource_tool_info(tool: dict[str, Any]) -> dict[str, Any]:
    keyword = str(tool["keyword"])
    arguments: list[dict[str, Any]] = []
    if tool.get("arg") == "node":
        arguments.append(
            {
                "name": "node",
                "type": "string",
                "required": False,
                "description": (
                    "a node handle (T#) from the referenceable-items manifest, "
                    "or 'here' for the current node"
                ),
            }
        )
    return {
        "name": keyword,
        "description": str(tool["description"]),
        "example": f"{keyword} here" if tool.get("arg") == "node" else keyword,
        "arguments": arguments,
        "response": MCP_TOOL_RESPONSE,
        "scope": CHAT_RESOURCE_SCOPE,
    }


class ToolArgumentOut(BaseModel):
    name: str
    type: str
    required: bool
    description: str | None


class ToolInfoOut(BaseModel):
    name: str
    description: str
    example: str | None = None
    arguments: list[ToolArgumentOut]
    response: str | None = None
    scope: str | None = None


class ToolsOut(BaseModel):
    tools: list[ToolInfoOut]


@router.get("/tools", response_model=ToolsOut)
async def list_tools(request: Request) -> dict[str, Any]:
    return {
        "tools": [
            *CHAT_TOOL_CATALOG,
            *(_resource_tool_info(tool) for tool in RESOURCE_TOOLS),
        ]
    }


class McpToolOut(BaseModel):
    name: str
    description: str | None
    arguments: list[ToolArgumentOut]


class McpInfoOut(BaseModel):
    command: str
    instructions: str
    tools: list[McpToolOut]


@router.get("/mcp", response_model=McpInfoOut)
async def mcp_info(request: Request) -> dict[str, Any]:
    server = create_resource_server(request.app.state.session_factory)
    mcp_tools = await server.list_tools()
    return {
        "command": "python -m studyassistant mcp",
        "instructions": MCP_INSTRUCTIONS,
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "arguments": _schema_arguments(tool.input_schema or {}),
            }
            for tool in mcp_tools
        ],
    }
