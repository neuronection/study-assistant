from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core import secrets
from ...domain.models import AiModel, DefaultTaskAssignment, Provider, TaskAssignment
from ..tasks import TASKS_BY_NAME
from .errors import ClassifiedProviderError, classify_provider_error
from .presets import SETUP_PRESETS
from .service import (
    ProviderError,
    _check_capability,
    fetch_remote_models,
    infer_caps,
)


class UnknownPresetError(Exception):
    pass


class CrossProviderModelError(Exception):
    pass


class SetupError(Exception):
    def __init__(self, classified: ClassifiedProviderError, vendor_message: str) -> None:
        super().__init__(vendor_message)
        self.classified = classified
        self.vendor_message = vendor_message


@dataclass
class SetupOptions:
    curated_ids: list[str] | None = None
    bind_chat: bool = True
    bind_vision: bool = True
    bind_stt: bool = True


@dataclass(frozen=True)
class SetupOutcome:
    provider_id: int
    catalog_count: int
    curated_missed: bool
    assigned_chat_model: str | None = None
    assigned_vision_model: str | None = None
    assigned_stt_model: str | None = None


@dataclass
class _PersistedModel:
    external_id: str
    caps: list[str]
    model_id: int = field(default=0)


def _resolve_target_row(
    session: Session, preset_key: str, preset: dict[str, Any]
) -> Provider | None:
    existing = session.scalars(
        select(Provider).where(Provider.preset_key == preset_key).order_by(Provider.id)
    ).first()
    if existing is not None:
        return existing
    return session.scalars(
        select(Provider)
        .where(
            Provider.preset_key.is_(None),
            Provider.type == preset["type"],
            Provider.base_url == preset["base_url"],
        )
        .order_by(Provider.id)
    ).first()


def _upsert_persisted_models(
    session: Session,
    provider: Provider,
    persist_catalog: list[_PersistedModel],
) -> None:
    existing = {
        model.external_id: model
        for model in session.scalars(
            select(AiModel).where(AiModel.provider_id == provider.id)
        )
    }
    for item in persist_catalog:
        model = existing.get(item.external_id)
        if model is None:
            model = AiModel(
                provider_id=provider.id,
                external_id=item.external_id,
                label=item.external_id,
                caps=list(item.caps),
                enabled=True,
                missing=False,
            )
            session.add(model)
            session.flush()
        elif not model.caps:
            model.caps = list(item.caps)
        item.model_id = model.id


def _slot_alive(session: Session, requires: str) -> tuple[DefaultTaskAssignment, AiModel | None]:
    row = session.get(DefaultTaskAssignment, requires)
    if row is None:
        row = DefaultTaskAssignment(requires=requires, model_id=None, fallback_model_id=None)
        session.add(row)
        session.flush()
        return row, None
    if row.model_id is None:
        return row, None
    model = session.get(AiModel, row.model_id)
    if model is None:
        return row, None
    return row, model


def _match_curated(model_id: str, curated: list[str]) -> str | None:
    for curated_id in curated:
        if model_id == curated_id or model_id.startswith(f"{curated_id}-"):
            return curated_id
    return None


def setup_provider_from_preset(
    session: Session,
    preset_key: str,
    api_key: str | None,
    *,
    name: str | None = None,
    options: SetupOptions | None = None,
    transport: httpx.BaseTransport | None = None,
) -> SetupOutcome:
    options = options or SetupOptions()
    preset = SETUP_PRESETS.get(preset_key)
    if preset is None:
        raise UnknownPresetError(f"unknown provider preset '{preset_key}'")

    existing = _resolve_target_row(session, preset_key, preset)
    key = "" if preset["local"] else (api_key or "").strip()
    if not key and existing is not None:
        key = secrets.get_secret(existing.keyring_ref) or ""

    resolved_base = preset["base_url"]
    if existing is not None:
        existing.type = preset["type"]
        existing.base_url = resolved_base
        provider = existing
    else:
        provider = Provider(
            name=(name or "").strip() or preset["name"],
            type=preset["type"],
            base_url=resolved_base,
            keyring_ref="pending",
            enabled=True,
            is_local=preset["local"],
            status=None,
        )
        session.add(provider)
        session.flush()
        provider.keyring_ref = f"provider:{provider.id}"
    provider.preset_key = preset_key
    session.flush()

    try:
        catalog = fetch_remote_models(
            provider.type, provider.base_url, key or None, transport=transport
        )
    except Exception as error:
        classified = classify_provider_error(
            error,
            local_provider=bool(preset["local"]),
            api_key=key or None,
            attempted_preset=preset_key,
        )
        session.rollback()
        raise SetupError(classified, str(error)[:300]) from error

    use_preset_curated = options.curated_ids is None
    curated = preset["curated_models"] if use_preset_curated else options.curated_ids
    curated = curated or []
    persist_catalog = [
        _PersistedModel(external_id=item.external_id, caps=list(item.caps))
        for item in catalog
    ]
    for item in persist_catalog:
        if not item.caps:
            item.caps = infer_caps(item.external_id)

    def curated_match(item: _PersistedModel) -> str | None:
        return _match_curated(item.external_id, curated)

    any_curated_match = any(curated_match(item) is not None for item in persist_catalog)
    if curated:
        if any_curated_match:
            persist_catalog = [item for item in persist_catalog if curated_match(item)]
        elif not use_preset_curated:
            persist_catalog = []
    elif not use_preset_curated:
        persist_catalog = []
    curated_missed = bool(use_preset_curated and curated and not any_curated_match)

    _upsert_persisted_models(session, provider, persist_catalog)
    if key:
        secrets.set_secret(provider.keyring_ref, key)
    session.flush()

    assigned_chat: str | None = None
    assigned_vision: str | None = None
    assigned_stt: str | None = None
    by_wire_id = {item.external_id: item for item in persist_catalog}

    preferred = preset["preferred_model"]
    preferred_model_id = preferred["id"] if preferred else None
    preferred_resolved_id = None
    if preferred_model_id:
        preferred_resolved_id = next(
            (
                item.external_id
                for item in persist_catalog
                if item.external_id == preferred_model_id
                or _match_curated(item.external_id, curated) == preferred_model_id
            ),
            None,
        )
    fallback_candidate_id = next(
        (
            item.external_id
            for curated_id in curated
            for item in persist_catalog
            if _match_curated(item.external_id, curated) == curated_id
        ),
        None,
    )
    assignment_candidate_id = preferred_resolved_id or fallback_candidate_id
    if preferred_resolved_id:
        assignment_vision_capable = bool(
            preferred and "vision" in (preferred.get("caps") or [])
        )
    elif assignment_candidate_id:
        assignment_vision_capable = "vision" in by_wire_id[assignment_candidate_id].caps
    else:
        assignment_vision_capable = False

    chat_row, chat_model = _slot_alive(session, "text")
    vision_candidate_id: str | None = None
    vision_capable_flag = False
    chat_wire_id = chat_model.external_id if chat_model is not None else None
    if (
        chat_wire_id
        and chat_wire_id in by_wire_id
        and "vision" in by_wire_id[chat_wire_id].caps
    ):
        vision_candidate_id = chat_wire_id
        vision_capable_flag = True
    if vision_candidate_id is None and assignment_candidate_id:
        vision_candidate_id = assignment_candidate_id
        vision_capable_flag = assignment_vision_capable

    if options.bind_chat and assignment_candidate_id and chat_model is None:
        assigned_chat = assignment_candidate_id
        chat_row.model_id = by_wire_id[assignment_candidate_id].model_id
        session.flush()
    if options.bind_vision and vision_candidate_id and vision_capable_flag:
        vision_row, vision_model = _slot_alive(session, "vision")
        if vision_model is None:
            assigned_vision = vision_candidate_id
            vision_row.model_id = by_wire_id[vision_candidate_id].model_id
            session.flush()

    stt_model_id = preset["stt_model"]
    stt_resolved_id = None
    if stt_model_id:
        stt_resolved_id = next(
            (
                item.external_id
                for item in persist_catalog
                if item.external_id == stt_model_id
                or _match_curated(item.external_id, curated) == stt_model_id
            ),
            None,
        )
    if options.bind_stt and stt_resolved_id:
        stt_row, stt_model = _slot_alive(session, "stt")
        if stt_model is None:
            assigned_stt = stt_resolved_id
            stt_row.model_id = by_wire_id[stt_resolved_id].model_id
            session.flush()

    return SetupOutcome(
        provider_id=provider.id,
        catalog_count=len(persist_catalog),
        curated_missed=curated_missed,
        assigned_chat_model=assigned_chat,
        assigned_vision_model=assigned_vision,
        assigned_stt_model=assigned_stt,
    )


def set_default_model(
    session: Session,
    provider_id: int,
    model_name: str,
    task: str = "chat",
) -> AiModel:
    provider = session.get(Provider, provider_id)
    if provider is None:
        raise ProviderError("provider not found")
    task_def = TASKS_BY_NAME.get(task)
    if task_def is None:
        raise ProviderError(f"unknown task '{task}'")
    model_name = model_name.strip()
    if not model_name:
        raise ProviderError("model_name is required")

    model = session.scalars(
        select(AiModel).where(
            AiModel.provider_id == provider_id, AiModel.external_id == model_name
        )
    ).first()
    if model is None:
        elsewhere = session.scalars(
            select(AiModel).where(AiModel.external_id == model_name)
        ).first()
        if elsewhere is not None:
            raise CrossProviderModelError(
                f"model '{model_name}' belongs to another provider"
            )
        model = AiModel(
            provider_id=provider_id,
            external_id=model_name,
            label=model_name,
            caps=infer_caps(model_name),
            enabled=True,
            missing=False,
        )
        session.add(model)
        session.flush()
    _check_capability(session, model.id, task_def.requires, "assigned")

    assignment = session.get(TaskAssignment, task)
    if assignment is None:
        assignment = TaskAssignment(task=task, model_id=model.id, fallback_model_id=None)
        session.add(assignment)
    else:
        assignment.model_id = model.id
    session.flush()
    return model
