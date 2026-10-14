import json
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.decide import is_decision_slot, probe_decision_provider
from ..ai.decide.systemone.probe import DecisionProbeInput, DecisionProbeResult
from ..ai.decide.types import decision_slot_capability
from ..ai.providers import (
    ALL_PRESETS,
    DEFAULT_REQUIRES,
    CrossProviderModelError,
    ProviderError,
    ProvidersService,
    SetupError,
    SetupOptions,
    UnknownPresetError,
    assign_course_default_task,
    assign_course_task,
    assign_default_task,
    assign_task,
    decision_probe_model_id,
    fetch_remote_models,
    list_assignments,
    list_course_assignments,
    list_course_default_assignments,
    list_default_assignments,
    set_default_model,
    setup_provider_from_preset,
)
from ..ai.providers import (
    detect_local_engines as probe_local_engines,
)
from ..ai.tasks import TASK_DEFS, TaskDef
from ..core.secrets import get_secret
from ..core.vocab import DecisionTransport
from ..domain.models import (
    AiModel,
    Course,
    CourseDefaultTaskAssignment,
    CourseTaskAssignment,
    DefaultTaskAssignment,
    Profile,
    Provider,
    TaskAssignment,
)
from ..search import (
    SearchError,
    delete_search_provider,
    list_search_providers,
    move_search_provider,
    probe_provider,
    provider_key_ref,
    search_provider_views,
    upsert_search_provider,
)
from .deps import get_session
from .schemas import (
    CourseDefaultTaskOut,
    CourseTaskOut,
    DefaultTaskOut,
    ModelCreateIn,
    ModelOut,
    ModelUpdate,
    ProviderCreate,
    ProviderOut,
    ProviderUpdate,
    RemoteModelOut,
    TaskAssignmentIn,
    TaskOut,
)

router = APIRouter(tags=["ai"])


class SearchProviderOut(BaseModel):
    id: str
    name: str
    type: str
    enabled: bool = True
    base_url: str | None = None
    google_cx: str | None = None
    key_hint: str | None = None
    timeout_ms: int = 8000
    max_results: int = 5
    key_set: bool = False


class SearchProviderIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    type: str | None = None
    base_url: str | None = Field(default=None, max_length=500)
    google_cx: str | None = Field(default=None, max_length=120)
    enabled: bool | None = None
    max_results: int | None = Field(default=None, ge=1, le=10)
    # absent = keep the stored key, "" = clear it, value = store it
    api_key: str | None = Field(default=None, max_length=500)


class SearchProvidersOut(BaseModel):
    providers: list[SearchProviderOut]


class SearchProviderProbeOut(BaseModel):
    status: str
    latency_ms: int
    result_count: int | None = None
    error: str | None = None


def _provider_view(view: dict) -> SearchProviderOut:
    return SearchProviderOut.model_validate(view)


def _ensure_profile(session: Session) -> Profile:
    from ..services.platform.profiles import ensure_default_profile

    return ensure_default_profile(session)


# Family web-search contract (ADR-0035 / plan 28): ordered multi-provider
# list; the catalog (labels, key URLs, base-URL rules) is the vendored
# contracts/search-providers.json copy — data-once, never edited here.
_CATALOG_PATH = Path(__file__).resolve().parents[1] / "search" / "providers_catalog.json"


@router.get("/search-providers", response_model=SearchProvidersOut)
def get_search_providers(session: Session = Depends(get_session)) -> SearchProvidersOut:
    profile = _ensure_profile(session)
    return SearchProvidersOut(
        providers=[_provider_view(view) for view in search_provider_views(session, profile.id)]
    )


@router.get("/search-providers/catalog", response_model=dict[str, Any])
def search_provider_catalog() -> dict[str, Any]:
    return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))


@router.post("/search-providers", response_model=SearchProviderOut, status_code=201)
def create_search_provider(
    body: SearchProviderIn, session: Session = Depends(get_session)
) -> SearchProviderOut:
    profile = _ensure_profile(session)
    try:
        view = upsert_search_provider(
            session,
            profile.id,
            {key: value for key, value in body.model_dump().items()},
        )
    except SearchError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _provider_view(view)


@router.put("/search-providers/{provider_id}", response_model=SearchProviderOut)
def update_search_provider(
    provider_id: str, body: SearchProviderIn, session: Session = Depends(get_session)
) -> SearchProviderOut:
    profile = _ensure_profile(session)
    try:
        view = upsert_search_provider(
            session,
            profile.id,
            {key: value for key, value in body.model_dump().items()},
            provider_id=provider_id,
        )
    except SearchError as error:
        raise HTTPException(status_code=404 if "not found" in str(error) else 422, detail=str(error)) from error
    return _provider_view(view)


class SearchProviderMoveIn(BaseModel):
    direction: str = Field(pattern="^(up|down)$")


@router.post("/search-providers/{provider_id}/move", response_model=SearchProvidersOut)
def reorder_search_provider(
    provider_id: str,
    body: SearchProviderMoveIn,
    session: Session = Depends(get_session),
) -> SearchProvidersOut:
    profile = _ensure_profile(session)
    try:
        views = move_search_provider(session, profile.id, provider_id, body.direction)
    except SearchError as error:
        raise HTTPException(status_code=404 if "not found" in str(error) else 422, detail=str(error)) from error
    return SearchProvidersOut(providers=[_provider_view(view) for view in views])


@router.delete("/search-providers/{provider_id}", status_code=204)
def remove_search_provider(provider_id: str, session: Session = Depends(get_session)) -> None:
    profile = _ensure_profile(session)
    if not delete_search_provider(session, profile.id, provider_id):
        raise HTTPException(status_code=404, detail="provider not found")


@router.post("/search-providers/{provider_id}/test", response_model=SearchProviderProbeOut)
def test_search_provider(
    provider_id: str, request: Request, session: Session = Depends(get_session)
) -> SearchProviderProbeOut:
    profile = _ensure_profile(session)
    provider = next(
        (entry for entry in list_search_providers(session, profile.id) if entry["id"] == provider_id),
        None,
    )
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    result = probe_provider(
        provider,
        api_key=get_secret(provider_key_ref(provider_id)) or "",
        transport=getattr(request.app.state, "search_transport", None),
    )
    return SearchProviderProbeOut.model_validate(result)


def _provider_out(service: ProvidersService, provider: Provider) -> ProviderOut:
    return ProviderOut(
        id=provider.id,
        name=provider.name,
        type=provider.type,
        base_url=provider.base_url,
        preset_key=provider.preset_key,
        enabled=provider.enabled,
        is_local=provider.is_local,
        country=provider.country,
        masked_key=service.masked_key(provider),
        status=provider.status,
        created_at=provider.created_at,
    )


class PresetOut(BaseModel):
    name: str
    type: str
    base_url: str
    fixed_base: bool
    local: bool
    key_url: str | None = None
    preferred_model: dict[str, Any] | None = None
    curated_models: list[str] | None = None
    stt_model: str | None = None
    decision_models: list[dict[str, Any]] | None = None
    decision_default: str | None = None
    provisional: bool | None = None
    steps: list[str] | None = None
    free_tier_note: str | None = None


@router.get("/providers/presets", response_model=dict[str, PresetOut])
def provider_presets() -> dict[str, PresetOut]:
    return {
        key: PresetOut(
            name=preset["name"],
            type=preset["type"],
            base_url=preset["base_url"],
            fixed_base=preset["fixed_base"],
            local=preset["local"],
            key_url=preset["key_url"],
            preferred_model=preset["preferred_model"],
            curated_models=preset["curated_models"],
            stt_model=preset["stt_model"],
            decision_models=preset["decision_models"],
            decision_default=preset["decision_default"],
            provisional=preset["provisional"],
            steps=preset["steps"],
            free_tier_note=preset["free_tier_note"],
        )
        for key, preset in ALL_PRESETS.items()
    }


class SetupOptionsIn(BaseModel):
    curated_ids: list[str] | None = Field(default=None, max_length=100)
    bind_chat: bool = True
    bind_vision: bool = True
    bind_stt: bool = True
    bind_embeddings: bool = True
    bind_decision: bool = True


class ProviderSetupIn(BaseModel):
    api_key: str | None = Field(default=None, max_length=500)
    name: str | None = Field(default=None, max_length=120)
    options: SetupOptionsIn | None = None


class SetupOut(BaseModel):
    ok: bool
    provider: ProviderOut
    catalog_count: int
    curated_missed: bool
    assigned_chat_model: str | None = None
    assigned_vision_model: str | None = None
    assigned_stt_model: str | None = None
    assigned_embeddings_model: str | None = None
    assigned_decision_slots: dict[str, str] | None = None


@router.post("/providers/{preset_key}/setup", response_model=SetupOut)
def setup_preset_provider(
    preset_key: str,
    body: ProviderSetupIn,
    session: Session = Depends(get_session),
) -> SetupOut:
    service = ProvidersService(session)
    options = None
    if body.options is not None:
        options = SetupOptions(
            curated_ids=body.options.curated_ids,
            bind_chat=body.options.bind_chat,
            bind_vision=body.options.bind_vision,
            bind_stt=body.options.bind_stt,
            bind_embeddings=body.options.bind_embeddings,
            bind_decision=body.options.bind_decision,
        )
    try:
        outcome = setup_provider_from_preset(
            session,
            preset_key,
            body.api_key,
            name=body.name,
            options=options,
        )
    except UnknownPresetError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SetupError as error:
        session.rollback()
        raise HTTPException(
            status_code=422,
            detail={
                "code": error.classified.code.value,
                "suspected_vendor": error.classified.suspected_vendor,
                "detail": error.vendor_message,
            },
        ) from error
    except ProviderError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    provider = session.get(Provider, outcome.provider_id)
    assert provider is not None
    return SetupOut(
        ok=True,
        provider=_provider_out(service, provider),
        catalog_count=outcome.catalog_count,
        curated_missed=outcome.curated_missed,
        assigned_chat_model=outcome.assigned_chat_model,
        assigned_vision_model=outcome.assigned_vision_model,
        assigned_stt_model=outcome.assigned_stt_model,
        assigned_embeddings_model=outcome.assigned_embeddings_model,
        assigned_decision_slots=outcome.assigned_decision_slots,
    )


class SetDefaultIn(BaseModel):
    model_name: str = Field(min_length=1, max_length=200)
    task: str = Field(default="chat", max_length=40)


@router.put("/providers/{provider_id}/set-default", response_model=TaskOut)
def set_provider_default(
    provider_id: int,
    body: SetDefaultIn,
    session: Session = Depends(get_session),
) -> TaskOut:
    try:
        set_default_model(session, provider_id, body.model_name, body.task)
    except ProviderError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except CrossProviderModelError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    session.commit()
    labels = {model.id: model.label for model in session.scalars(select(AiModel))}
    task_def = next(t for t in TASK_DEFS if t.task == body.task)
    assignment = session.get(TaskAssignment, body.task)
    default = session.get(DefaultTaskAssignment, task_def.requires)
    return _task_out(task_def, assignment, default, labels)


class LocalEngineHitOut(BaseModel):
    preset_id: str
    name: str
    base_url: str
    models: list[str]


@router.get("/providers/detect-local", response_model=list[LocalEngineHitOut])
def detect_local(session: Session = Depends(get_session)) -> list[LocalEngineHitOut]:
    configured = set(session.scalars(select(Provider.base_url)).all())
    hits = probe_local_engines(configured_base_urls=configured)
    return [
        LocalEngineHitOut(
            preset_id=hit.preset_id,
            name=hit.name,
            base_url=hit.base_url,
            models=list(hit.models),
        )
        for hit in hits
    ]


@router.get("/providers", response_model=list[ProviderOut])
def list_providers(session: Session = Depends(get_session)) -> list[ProviderOut]:
    service = ProvidersService(session)
    return [
        _provider_out(service, provider)
        for provider in session.scalars(select(Provider).order_by(Provider.id))
    ]


@router.post("/providers", response_model=ProviderOut, status_code=201)
def create_provider(body: ProviderCreate, session: Session = Depends(get_session)) -> ProviderOut:
    service = ProvidersService(session)
    provider: Provider | None = None
    try:
        provider = service.create(
            name=body.name,
            provider_type=body.type,
            base_url=body.base_url,
            api_key=body.api_key,
        )
        provider.is_local = body.is_local
        provider.country = (body.country or "").strip() or None
        remote = service.discover(provider)
        service.record_status(provider, ok=True, error=None, model_count=len(remote))
    except ProviderError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        if provider is None:
            session.rollback()
            raise HTTPException(status_code=422, detail=str(error)) from error
        service.record_status(provider, ok=False, error=str(error)[:300])
    session.commit()
    return _provider_out(service, provider)


@router.patch("/providers/{provider_id}", response_model=ProviderOut)
def update_provider(
    provider_id: int, body: ProviderUpdate, session: Session = Depends(get_session)
) -> ProviderOut:
    service = ProvidersService(session)
    try:
        provider = service.update(
            provider_id,
            name=body.name,
            base_url=body.base_url,
            enabled=body.enabled,
            api_key=body.api_key,
        )
        if provider is not None:
            if "is_local" in body.model_fields_set:
                provider.is_local = body.is_local
            if "country" in body.model_fields_set:
                provider.country = (body.country or "").strip() or None
    except ProviderError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    session.commit()
    return _provider_out(service, provider)


@router.delete("/providers/{provider_id}", status_code=204)
def delete_provider(provider_id: int, session: Session = Depends(get_session)) -> None:
    if not ProvidersService(session).delete(provider_id):
        raise HTTPException(status_code=404, detail="provider not found")
    session.commit()


@router.post("/providers/{provider_id}/test", response_model=ProviderOut)
def test_provider(provider_id: int, session: Session = Depends(get_session)) -> ProviderOut:
    service = ProvidersService(session)
    provider = session.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    if provider.type == "decision":
        probe = _probe_provider(session, provider)
        service.record_status(
            provider,
            ok=probe.ok,
            error=None if probe.ok else (probe.error or "decision probe failed"),
        )
        session.commit()
        return _provider_out(service, provider)
    try:
        remote = fetch_remote_models(provider.type, provider.base_url, service.api_key(provider))
        service.record_status(provider, ok=True, error=None, model_count=len(remote))
    except Exception as error:
        service.record_status(provider, ok=False, error=str(error)[:300])
    session.commit()
    return _provider_out(service, provider)


def _probe_provider(session: Session, provider: Provider) -> DecisionProbeResult:
    api_key = ProvidersService(session).api_key(provider)
    model = session.scalars(
        select(AiModel).where(AiModel.provider_id == provider.id).order_by(AiModel.id)
    ).first()
    if model is None:
        # §15 single-source: a key-only probe derives its model id from the
        # provider's preset stamp in the synced canonical data — never a
        # code literal. A decision provider with neither models nor a
        # declarable preset gets an actionable failure, not an invented id.
        preset = ALL_PRESETS.get(provider.preset_key) if provider.preset_key else None
        if preset is None:
            return DecisionProbeResult(
                ok=False,
                latency_ms=0,
                error="Add a decision model to this provider, then test again.",
            )
        external_id = decision_probe_model_id(preset)
        model = AiModel(
            provider_id=provider.id,
            external_id=external_id,
            label=external_id,
            caps=["decision"],
            decision_transport="systemone",
        )
    return probe_decision_provider(
        DecisionProbeInput(provider=provider, model=model, api_key=api_key or "")
    )


def _remote_error_detail(service: ProvidersService, provider: Provider, error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError) and error.response.status_code in (401, 403):
        if service.api_key(provider) is None:
            state = "no API key is stored for this provider"
        else:
            state = "the stored API key was rejected by the provider"
        return (
            f"{error.response.status_code} — {state}. Fix the key with the "
            "provider's Edit button, or add the model manually."
        )
    return str(error)[:300]


@router.post("/providers/{provider_id}/models", response_model=list[ModelOut])
def discover_models(provider_id: int, session: Session = Depends(get_session)) -> list[ModelOut]:
    service = ProvidersService(session)
    provider = session.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    try:
        models = service.discover(provider)
        service.record_status(provider, ok=True, error=None, model_count=len(models))
    except Exception as error:
        detail = _remote_error_detail(service, provider, error)
        service.record_status(provider, ok=False, error=detail)
        raise HTTPException(status_code=502, detail=detail) from error
    session.commit()
    return [_model_out(model) for model in models]


@router.get("/providers/{provider_id}/remote-models", response_model=list[RemoteModelOut])
def remote_models(
    provider_id: int, session: Session = Depends(get_session)
) -> list[RemoteModelOut]:
    service = ProvidersService(session)
    provider = session.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    try:
        remote = fetch_remote_models(provider.type, provider.base_url, service.api_key(provider))
    except Exception as error:
        raise HTTPException(
            status_code=502, detail=_remote_error_detail(service, provider, error)
        ) from error
    return [RemoteModelOut(external_id=item.external_id, caps=list(item.caps)) for item in remote]


def _model_out(model: AiModel) -> ModelOut:
    return ModelOut(
        id=model.id,
        provider_id=model.provider_id,
        external_id=model.external_id,
        label=model.label,
        caps=list(model.caps or []),
        decision_transport=model.decision_transport,
        enabled=model.enabled,
        missing=model.missing,
        reasoning_effort=model.reasoning_effort,
        temperature=model.temperature,
        max_tokens=model.max_tokens,
    )


@router.get("/models", response_model=list[ModelOut])
def list_models(
    provider_id: int | None = None, session: Session = Depends(get_session)
) -> list[ModelOut]:
    query = select(AiModel).order_by(AiModel.provider_id, AiModel.external_id)
    if provider_id is not None:
        query = query.where(AiModel.provider_id == provider_id)
    return [_model_out(model) for model in session.scalars(query)]


@router.post("/models", response_model=ModelOut)
def create_model(
    body: ModelCreateIn,
    response: Response,
    session: Session = Depends(get_session),
) -> ModelOut:
    from ..ai.providers import infer_caps

    provider = session.get(Provider, body.provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    external_id = body.external_id.strip()
    if not external_id:
        raise HTTPException(status_code=422, detail="external_id is required")
    caps = body.caps
    decision_provider = provider.type == "decision"
    if caps is None:
        caps = ["decision"] if decision_provider else infer_caps(external_id)
    # The decision transport seam (D2): decision-only providers imply it;
    # an explicit decision capability on any provider row stamps the
    # payload's transport or the one shipping transport; without the
    # capability there is no transport to carry.
    if decision_provider or "decision" in caps:
        decision_transport = (
            body.decision_transport
            if body.decision_transport is not None
            else DecisionTransport.SYSTEMONE.value
        )
    else:
        decision_transport = None
    model = session.scalars(
        select(AiModel).where(
            AiModel.provider_id == body.provider_id,
            AiModel.external_id == external_id,
        )
    ).first()
    if model is None:
        model = AiModel(
            provider_id=body.provider_id,
            external_id=external_id,
            label=(body.label or external_id).strip() or external_id,
            caps=caps,
            decision_transport=decision_transport,
            enabled=body.enabled,
            missing=False,
            reasoning_effort=(body.reasoning_effort or "").strip() or None,
        )
        session.add(model)
        status_code = 201
    else:
        model.missing = False
        model.caps = caps
        model.enabled = body.enabled
        model.decision_transport = decision_transport
        if body.label is not None:
            model.label = body.label.strip() or external_id
        if body.reasoning_effort is not None:
            model.reasoning_effort = body.reasoning_effort.strip() or None
        status_code = 200
    session.commit()
    response.status_code = status_code
    return _model_out(model)


@router.delete("/models/{model_id}", status_code=204)
def delete_model(model_id: int, session: Session = Depends(get_session)) -> None:
    model = session.get(AiModel, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="model not found")
    for assignment in session.scalars(select(TaskAssignment)):
        if assignment.model_id == model_id:
            assignment.model_id = None
        if assignment.fallback_model_id == model_id:
            assignment.fallback_model_id = None
    for default_assignment in session.scalars(select(DefaultTaskAssignment)):
        if default_assignment.model_id == model_id:
            default_assignment.model_id = None
        if default_assignment.fallback_model_id == model_id:
            default_assignment.fallback_model_id = None
    for course_assignment in session.scalars(select(CourseTaskAssignment)):
        if course_assignment.model_id == model_id:
            course_assignment.model_id = None
        if course_assignment.fallback_model_id == model_id:
            course_assignment.fallback_model_id = None
    for course_default in session.scalars(select(CourseDefaultTaskAssignment)):
        if course_default.model_id == model_id:
            course_default.model_id = None
        if course_default.fallback_model_id == model_id:
            course_default.fallback_model_id = None
    session.delete(model)
    session.commit()


@router.patch("/models/{model_id}", response_model=ModelOut)
def update_model(
    model_id: int, body: ModelUpdate, session: Session = Depends(get_session)
) -> ModelOut:
    model = session.get(AiModel, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="model not found")
    if body.label is not None:
        model.label = body.label
    if body.enabled is not None:
        model.enabled = body.enabled
    if body.caps is not None:
        model.caps = body.caps
    if body.reasoning_effort is not None:
        model.reasoning_effort = body.reasoning_effort.strip() or None
    if "temperature" in body.model_fields_set:
        model.temperature = body.temperature
    if "max_tokens" in body.model_fields_set:
        model.max_tokens = body.max_tokens
    effective_caps = body.caps if body.caps is not None else model.caps
    provider_row = session.get(Provider, model.provider_id)
    decision_kept = "decision" in effective_caps or (
        provider_row is not None and provider_row.type == "decision"
    )
    if decision_kept:
        model.decision_transport = body.decision_transport or DecisionTransport.SYSTEMONE.value
    elif "decision_transport" in body.model_fields_set or body.caps is not None:
        # caps changed away from decision (or the transport was set
        # explicitly) — nothing to carry without the capability.
        model.decision_transport = body.decision_transport
    session.commit()
    return _model_out(model)


def _task_out(
    task_def: TaskDef,
    assignment: TaskAssignment | None,
    default: DefaultTaskAssignment | None,
    labels: dict[int, str],
    monthly_cap: float | None = None,
) -> TaskOut:
    model_id = assignment.model_id if assignment else None
    fallback_id = assignment.fallback_model_id if assignment else None
    return TaskOut(
        task=task_def.task,
        description=task_def.description,
        requires=task_def.requires,
        model_id=model_id,
        fallback_model_id=fallback_id,
        model_label=labels.get(model_id) if model_id is not None else None,
        fallback_model_label=(labels.get(fallback_id) if fallback_id is not None else None),
        inherits_default=model_id is None and default is not None,
        default_model_label=(
            labels.get(default.model_id)
            if default is not None and default.model_id is not None
            else None
        ),
        default_fallback_model_label=(
            labels.get(default.fallback_model_id)
            if default is not None and default.fallback_model_id is not None
            else None
        ),
        monthly_cap_usd=monthly_cap,
    )


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(session: Session = Depends(get_session)) -> list[TaskOut]:
    assignments = list_assignments(session)
    defaults = list_default_assignments(session)
    labels = {model.id: model.label for model in session.scalars(select(AiModel))}
    result: list[TaskOut] = []
    for task_def in TASK_DEFS:
        assignment = assignments.get(task_def.task)
        monthly_cap = (assignment.params or {}).get("monthly_cap_usd") if assignment else None
        result.append(
            _task_out(
                task_def,
                assignment,
                defaults.get(task_def.requires),
                labels,
                monthly_cap=monthly_cap,
            )
        )
    return result


@router.get("/tasks/defaults", response_model=list[DefaultTaskOut])
def list_task_defaults(session: Session = Depends(get_session)) -> list[DefaultTaskOut]:
    defaults = list_default_assignments(session)
    labels = {model.id: model.label for model in session.scalars(select(AiModel))}
    result: list[DefaultTaskOut] = []
    for requires in DEFAULT_REQUIRES:
        default = defaults.get(requires)
        model_id = default.model_id if default else None
        fallback_id = default.fallback_model_id if default else None
        result.append(
            DefaultTaskOut(
                requires=requires,
                model_id=model_id,
                fallback_model_id=fallback_id,
                model_label=labels.get(model_id) if model_id is not None else None,
                fallback_model_label=(labels.get(fallback_id) if fallback_id is not None else None),
                resolved_inherit_label=(
                    _decision_inherit_label(session, requires)
                    if is_decision_slot(requires)
                    else None
                ),
            )
        )
    return result


def _decision_inherit_label(session: Session, requires: str) -> str | None:
    """ADR-0036 §4: what the kind's labeled null option names — the model
    the `decision` default slot resolves to for this kind, or None when
    the inherit state honestly resolves to nothing."""
    from ..ai.decide import OffResolution, resolve_decision_inherit

    capability = decision_slot_capability(requires)
    if capability is None:
        return None
    resolution = resolve_decision_inherit(capability, session)
    if isinstance(resolution, OffResolution):
        return None
    label = resolution.model.label or resolution.model.external_id
    return label or None


@router.put("/tasks/defaults/{requires}", response_model=DefaultTaskOut)
def put_task_default(
    requires: str, body: TaskAssignmentIn, session: Session = Depends(get_session)
) -> DefaultTaskOut:
    try:
        assignment = assign_default_task(session, requires, body.model_id, body.fallback_model_id)
    except ProviderError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    labels = {model.id: model.label for model in session.scalars(select(AiModel))}
    return DefaultTaskOut(
        requires=requires,
        model_id=assignment.model_id,
        fallback_model_id=assignment.fallback_model_id,
        model_label=(labels.get(assignment.model_id) if assignment.model_id else None),
        fallback_model_label=(
            labels.get(assignment.fallback_model_id) if assignment.fallback_model_id else None
        ),
    )


class BudgetIn(BaseModel):
    monthly_cap_usd: float | None = Field(default=None, ge=0)


@router.put("/tasks/{task}/budget", response_model=TaskOut)
def put_task_budget(task: str, body: BudgetIn, session: Session = Depends(get_session)) -> TaskOut:
    from ..domain.models import TaskAssignment

    assignment = session.get(TaskAssignment, task)
    if assignment is None:
        raise HTTPException(status_code=404, detail="unknown task")
    params = dict(assignment.params or {})
    if body.monthly_cap_usd is None:
        params.pop("monthly_cap_usd", None)
    else:
        params["monthly_cap_usd"] = body.monthly_cap_usd
    assignment.params = params
    session.commit()
    labels = {model.id: model.label for model in session.scalars(select(AiModel))}
    task_def = next((entry for entry in TASK_DEFS if entry.task == task), None)
    if task_def is None:
        raise HTTPException(status_code=404, detail="unknown task")
    default = session.get(DefaultTaskAssignment, task_def.requires)
    return _task_out(
        task_def,
        assignment,
        default,
        labels,
        monthly_cap=params.get("monthly_cap_usd"),
    )


@router.put("/tasks/{task}", response_model=TaskOut)
def put_task(task: str, body: TaskAssignmentIn, session: Session = Depends(get_session)) -> TaskOut:
    try:
        assignment = assign_task(session, task, body.model_id, body.fallback_model_id)
    except ProviderError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    labels = {model.id: model.label for model in session.scalars(select(AiModel))}
    task_def = next(t for t in TASK_DEFS if t.task == task)
    default = session.get(DefaultTaskAssignment, task_def.requires)
    return _task_out(task_def, assignment, default, labels)


def _course_inherited_labels(
    session: Session, task_def: TaskDef, course_id: int
) -> tuple[str | None, str | None]:
    """What a task uses when the course sets no per-task override.

    Chain (low → high): capability default → global task assignment →
    per-course capability default.
    """
    assignment = session.get(TaskAssignment, task_def.task)
    default: DefaultTaskAssignment | None = session.get(DefaultTaskAssignment, task_def.requires)
    course_default: CourseDefaultTaskAssignment | None = session.get(
        CourseDefaultTaskAssignment, (course_id, task_def.requires)
    )

    def slot(
        task_value: int | None,
        default_value: int | None,
        course_default_value: int | None,
    ) -> int | None:
        value = default_value
        if assignment is not None and task_value is not None:
            value = task_value
        if course_default is not None and course_default_value is not None:
            value = course_default_value
        return value

    model_id = slot(
        assignment.model_id if assignment else None,
        default.model_id if default else None,
        course_default.model_id if course_default else None,
    )
    fallback_id = slot(
        assignment.fallback_model_id if assignment else None,
        default.fallback_model_id if default else None,
        course_default.fallback_model_id if course_default else None,
    )
    labels = {model.id: model.label for model in session.scalars(select(AiModel))}
    return (
        labels.get(model_id) if model_id is not None else None,
        labels.get(fallback_id) if fallback_id is not None else None,
    )


def _global_task_labels(session: Session, task_def: TaskDef) -> tuple[str | None, str | None]:
    assignment = session.get(TaskAssignment, task_def.task)
    default = session.get(DefaultTaskAssignment, task_def.requires)
    global_model_id = (
        assignment.model_id
        if assignment and assignment.model_id is not None
        else default.model_id
        if default
        else None
    )
    global_fallback_id = (
        assignment.fallback_model_id
        if assignment and assignment.fallback_model_id is not None
        else default.fallback_model_id
        if default
        else None
    )
    labels = {model.id: model.label for model in session.scalars(select(AiModel))}
    return (
        labels.get(global_model_id) if global_model_id is not None else None,
        labels.get(global_fallback_id) if global_fallback_id is not None else None,
    )


def _course_task_out(
    session: Session,
    task_def: TaskDef,
    override: CourseTaskAssignment | None,
    course_id: int,
) -> CourseTaskOut:
    labels = {model.id: model.label for model in session.scalars(select(AiModel))}
    inherited_model_label, inherited_fallback_label = _course_inherited_labels(
        session, task_def, course_id
    )
    model_id = override.model_id if override else None
    fallback_id = override.fallback_model_id if override else None
    return CourseTaskOut(
        task=task_def.task,
        description=task_def.description,
        requires=task_def.requires,
        model_id=model_id,
        fallback_model_id=fallback_id,
        model_label=labels.get(model_id) if model_id is not None else None,
        fallback_model_label=(labels.get(fallback_id) if fallback_id is not None else None),
        global_model_label=inherited_model_label,
        global_fallback_model_label=inherited_fallback_label,
    )


def _course_default_out(
    session: Session,
    requires: str,
    row: CourseDefaultTaskAssignment | None,
) -> CourseDefaultTaskOut:
    labels = {model.id: model.label for model in session.scalars(select(AiModel))}
    default = session.get(DefaultTaskAssignment, requires)
    global_model_id = default.model_id if default is not None else None
    global_fallback_id = default.fallback_model_id if default is not None else None
    model_id = row.model_id if row else None
    fallback_id = row.fallback_model_id if row else None
    return CourseDefaultTaskOut(
        requires=requires,
        model_id=model_id,
        fallback_model_id=fallback_id,
        model_label=labels.get(model_id) if model_id is not None else None,
        fallback_model_label=(labels.get(fallback_id) if fallback_id is not None else None),
        global_model_label=(labels.get(global_model_id) if global_model_id is not None else None),
        global_fallback_model_label=(
            labels.get(global_fallback_id) if global_fallback_id is not None else None
        ),
    )


def _get_course_or_404(course_id: int, session: Session) -> Course:
    course = session.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="course not found")
    return course


@router.get("/courses/{course_id}/tasks", response_model=list[CourseTaskOut])
def list_course_tasks(
    course_id: int, session: Session = Depends(get_session)
) -> list[CourseTaskOut]:
    _get_course_or_404(course_id, session)
    overrides = list_course_assignments(session, course_id)
    return [
        _course_task_out(session, task_def, overrides.get(task_def.task), course_id)
        for task_def in TASK_DEFS
    ]


@router.get(
    "/courses/{course_id}/tasks/defaults",
    response_model=list[CourseDefaultTaskOut],
)
def list_course_task_defaults(
    course_id: int, session: Session = Depends(get_session)
) -> list[CourseDefaultTaskOut]:
    _get_course_or_404(course_id, session)
    rows = list_course_default_assignments(session, course_id)
    return [
        _course_default_out(session, requires, rows.get(requires)) for requires in DEFAULT_REQUIRES
    ]


@router.put(
    "/courses/{course_id}/tasks/defaults/{requires}",
    response_model=CourseDefaultTaskOut,
)
def put_course_task_default(
    course_id: int,
    requires: str,
    body: TaskAssignmentIn,
    session: Session = Depends(get_session),
) -> CourseDefaultTaskOut:
    _get_course_or_404(course_id, session)
    try:
        row = assign_course_default_task(
            session, course_id, requires, body.model_id, body.fallback_model_id
        )
    except ProviderError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _course_default_out(session, requires, row)


@router.put("/courses/{course_id}/tasks/{task}", response_model=CourseTaskOut)
def put_course_task(
    course_id: int, task: str, body: TaskAssignmentIn, session: Session = Depends(get_session)
) -> CourseTaskOut:
    _get_course_or_404(course_id, session)
    try:
        override = assign_course_task(
            session, course_id, task, body.model_id, body.fallback_model_id
        )
    except ProviderError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    task_def = next(t for t in TASK_DEFS if t.task == task)
    return _course_task_out(session, task_def, override, course_id)
