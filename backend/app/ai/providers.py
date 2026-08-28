import contextlib
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import secrets
from ..domain.models import (
    AiModel,
    CourseDefaultTaskAssignment,
    CourseTaskAssignment,
    DefaultTaskAssignment,
    Provider,
    TaskAssignment,
    utcnow,
)

PROVIDER_TYPES = ("google", "openai_compatible", "anthropic")

DEFAULT_REQUIRES = ("text", "vision", "embeddings", "audio")

DEFAULT_BASE_URLS: dict[str, str] = {
    "google": "https://generativelanguage.googleapis.com",
    "anthropic": "https://api.anthropic.com",
}

PRESETS: dict[str, dict[str, str]] = {
    "google": {"name": "Google Gemini", "type": "google", "base_url": DEFAULT_BASE_URLS["google"]},
    "openai": {
        "name": "OpenAI",
        "type": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
    },
    "anthropic": {
        "name": "Anthropic",
        "type": "anthropic",
        "base_url": DEFAULT_BASE_URLS["anthropic"],
    },
    "ollama": {
        "name": "Ollama (local)",
        "type": "openai_compatible",
        "base_url": "http://localhost:11434/v1",
    },
}


class ProviderError(ValueError):
    pass


@dataclass(frozen=True)
class RemoteModel:
    external_id: str
    caps: tuple[str, ...]


def infer_caps(external_id: str, methods: list[str] | None = None) -> list[str]:
    name = external_id.lower()
    if "embedding" in name or "bge" in name or (methods is not None and "embedContent" in methods):
        return ["embeddings"]
    stt_hints = ("whisper", "transcribe")
    if any(hint in name for hint in stt_hints):
        return ["audio"]
    if methods is not None and "generateContent" not in methods:
        return []
    caps = ["text"]
    vision_hints = (
        "gemini", "gpt-4o", "gpt-4.1", "gpt-4-turbo", "claude-3", "claude-4",
        "claude-sonnet", "claude-opus", "claude-haiku", "vision", "-vl", "llava",
        "pixtral", "gemma3",
    )
    if any(hint in name for hint in vision_hints):
        caps.append("vision")
    if "gemini" in name:
        caps.append("audio")
    tool_hints = (
        "gpt-4", "gpt-5", "o3", "o4", "claude", "gemini", "deepseek", "qwen",
        "llama-3", "mistral",
    )
    if any(hint in name for hint in tool_hints):
        caps.append("tools")
    return caps


def fetch_remote_models(
    provider_type: str,
    base_url: str,
    api_key: str | None,
    transport: httpx.BaseTransport | None = None,
) -> list[RemoteModel]:
    with httpx.Client(timeout=30, transport=transport) as client:
        if provider_type == "google":
            response = client.get(
                f"{base_url}/v1beta/models",
                params={"key": api_key, "pageSize": 200},
            )
            response.raise_for_status()
            items: list[dict[str, Any]] = response.json().get("models", [])
            models = []
            for item in items:
                external_id = item.get("name", "").removeprefix("models/")
                if not external_id:
                    continue
                methods = item.get("supportedGenerationMethods", [])
                caps = infer_caps(external_id, methods)
                if caps:
                    models.append(RemoteModel(external_id=external_id, caps=tuple(caps)))
            return models
        if provider_type == "openai_compatible":
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            response = client.get(f"{base_url}/models", headers=headers)
            response.raise_for_status()
            data = response.json().get("data", [])
            return [
                RemoteModel(external_id=item["id"], caps=tuple(infer_caps(item["id"])))
                for item in data
                if item.get("id")
            ]
        if provider_type == "anthropic":
            headers = {"x-api-key": api_key or "", "anthropic-version": "2023-06-01"}
            response = client.get(f"{base_url}/v1/models", headers=headers)
            response.raise_for_status()
            data = response.json().get("data", [])
            return [
                RemoteModel(external_id=item["id"], caps=tuple(infer_caps(item["id"])))
                for item in data
                if item.get("id")
            ]
    raise ProviderError(f"unknown provider type '{provider_type}'")


class ProvidersService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        name: str,
        provider_type: str,
        base_url: str | None,
        api_key: str | None,
        enabled: bool = True,
    ) -> Provider:
        name = name.strip()
        if not name:
            raise ProviderError("provider name is required")
        if provider_type not in PROVIDER_TYPES:
            raise ProviderError(f"provider type must be one of {PROVIDER_TYPES}")
        resolved_base = (base_url or DEFAULT_BASE_URLS.get(provider_type) or "").strip().rstrip("/")
        if not resolved_base:
            raise ProviderError("base URL is required for openai_compatible providers")
        provider = Provider(
            name=name,
            type=provider_type,
            base_url=resolved_base,
            keyring_ref="pending",
            enabled=enabled,
            status=None,
        )
        self._session.add(provider)
        self._session.flush()
        provider.keyring_ref = f"provider:{provider.id}"
        if api_key:
            secrets.set_secret(provider.keyring_ref, api_key)
        self._session.flush()
        return provider

    def update(
        self,
        provider_id: int,
        *,
        name: str | None = None,
        base_url: str | None = None,
        enabled: bool | None = None,
        api_key: str | None = None,
    ) -> Provider | None:
        provider = self._session.get(Provider, provider_id)
        if provider is None:
            return None
        if name is not None:
            name = name.strip()
            if not name:
                raise ProviderError("provider name is required")
            provider.name = name
        if base_url is not None:
            provider.base_url = base_url.strip().rstrip("/")
        if enabled is not None:
            provider.enabled = enabled
        if api_key:
            secrets.set_secret(provider.keyring_ref, api_key)
        self._session.flush()
        return provider

    def delete(self, provider_id: int) -> bool:
        provider = self._session.get(Provider, provider_id)
        if provider is None:
            return False
        model_ids = list(
            self._session.scalars(select(AiModel.id).where(AiModel.provider_id == provider_id))
        )
        for assignment in self._session.scalars(select(TaskAssignment)):
            if assignment.model_id in model_ids:
                assignment.model_id = None
            if assignment.fallback_model_id in model_ids:
                assignment.fallback_model_id = None
        for default_assignment in self._session.scalars(select(DefaultTaskAssignment)):
            if default_assignment.model_id in model_ids:
                default_assignment.model_id = None
            if default_assignment.fallback_model_id in model_ids:
                default_assignment.fallback_model_id = None
        for model in self._session.scalars(
            select(AiModel).where(AiModel.provider_id == provider_id)
        ):
            self._session.delete(model)
        with contextlib.suppress(Exception):
            secrets.delete_secret(provider.keyring_ref)
        self._session.delete(provider)
        self._session.flush()
        return True

    def masked_key(self, provider: Provider) -> str | None:
        key = secrets.get_secret(provider.keyring_ref)
        if key is None:
            return None
        return f"••••{key[-4:]}"

    def api_key(self, provider: Provider) -> str | None:
        return secrets.get_secret(provider.keyring_ref)

    def record_status(
        self, provider: Provider, *, ok: bool, error: str | None, model_count: int | None = None
    ) -> None:
        provider.status = {
            "last_tested_at": utcnow().isoformat(),
            "ok": ok,
            "error": error,
            "model_count": model_count,
        }
        self._session.flush()

    def discover(
        self,
        provider: Provider,
        transport: httpx.BaseTransport | None = None,
    ) -> list[AiModel]:
        remote = fetch_remote_models(
            provider.type, provider.base_url, self.api_key(provider), transport
        )
        existing = {
            model.external_id: model
            for model in self._session.scalars(
                select(AiModel).where(AiModel.provider_id == provider.id)
            )
        }
        seen: set[str] = set()
        for item in remote:
            seen.add(item.external_id)
            model = existing.get(item.external_id)
            if model is None:
                self._session.add(
                    AiModel(
                        provider_id=provider.id,
                        external_id=item.external_id,
                        label=item.external_id,
                        caps=list(item.caps),
                        enabled=False,
                        missing=False,
                        last_seen_at=utcnow(),
                    )
                )
            else:
                model.missing = False
                model.last_seen_at = utcnow()
        for external_id, model in existing.items():
            if external_id not in seen:
                model.missing = True
        self._session.flush()
        return list(
            self._session.scalars(
                select(AiModel)
                .where(AiModel.provider_id == provider.id)
                .order_by(AiModel.external_id)
            )
        )


def _check_capability(
    session: Session,
    model_id: int | None,
    requires: str,
    field: str,
) -> None:
    if model_id is None:
        return
    model = session.get(AiModel, model_id)
    if model is None:
        raise ProviderError(f"{field} model not found")
    if not model.enabled:
        raise ProviderError(f"{field} model is not enabled")
    if requires not in (model.caps or []):
        raise ProviderError(f"task requires the '{requires}' capability")


def assign_task(
    session: Session,
    task: str,
    model_id: int | None,
    fallback_model_id: int | None,
) -> TaskAssignment:
    from .tasks import TASKS_BY_NAME

    task_def = TASKS_BY_NAME.get(task)
    if task_def is None:
        raise ProviderError(f"unknown task '{task}'")

    _check_capability(session, model_id, task_def.requires, "assigned")
    _check_capability(session, fallback_model_id, task_def.requires, "fallback")
    assignment = session.get(TaskAssignment, task)
    if assignment is None:
        assignment = TaskAssignment(
            task=task, model_id=model_id, fallback_model_id=fallback_model_id
        )
        session.add(assignment)
    else:
        assignment.model_id = model_id
        assignment.fallback_model_id = fallback_model_id
    session.flush()
    return assignment


def assign_default_task(
    session: Session,
    requires: str,
    model_id: int | None,
    fallback_model_id: int | None,
) -> DefaultTaskAssignment:
    if requires not in DEFAULT_REQUIRES:
        raise ProviderError(f"unknown capability '{requires}'")

    _check_capability(session, model_id, requires, "assigned")
    _check_capability(session, fallback_model_id, requires, "fallback")
    assignment = session.get(DefaultTaskAssignment, requires)
    if assignment is None:
        assignment = DefaultTaskAssignment(
            requires=requires, model_id=model_id, fallback_model_id=fallback_model_id
        )
        session.add(assignment)
    else:
        assignment.model_id = model_id
        assignment.fallback_model_id = fallback_model_id
    session.flush()
    return assignment


def assign_course_task(
    session: Session,
    course_id: int,
    task: str,
    model_id: int | None,
    fallback_model_id: int | None,
) -> CourseTaskAssignment:
    from ..domain.models import Course
    from .tasks import TASKS_BY_NAME

    if session.get(Course, course_id) is None:
        raise ProviderError(f"course {course_id} not found")
    task_def = TASKS_BY_NAME.get(task)
    if task_def is None:
        raise ProviderError(f"unknown task '{task}'")

    _check_capability(session, model_id, task_def.requires, "assigned")
    _check_capability(session, fallback_model_id, task_def.requires, "fallback")
    assignment = session.get(CourseTaskAssignment, (course_id, task))
    if assignment is None:
        assignment = CourseTaskAssignment(
            course_id=course_id,
            task=task,
            model_id=model_id,
            fallback_model_id=fallback_model_id,
        )
        session.add(assignment)
    else:
        assignment.model_id = model_id
        assignment.fallback_model_id = fallback_model_id
    session.flush()
    return assignment


def assign_course_default_task(
    session: Session,
    course_id: int,
    requires: str,
    model_id: int | None,
    fallback_model_id: int | None,
) -> CourseDefaultTaskAssignment:
    from ..domain.models import Course

    if requires not in DEFAULT_REQUIRES:
        raise ProviderError(f"unknown capability '{requires}'")
    if session.get(Course, course_id) is None:
        raise ProviderError(f"course {course_id} not found")

    _check_capability(session, model_id, requires, "assigned")
    _check_capability(session, fallback_model_id, requires, "fallback")
    assignment = session.get(CourseDefaultTaskAssignment, (course_id, requires))
    if assignment is None:
        assignment = CourseDefaultTaskAssignment(
            course_id=course_id,
            requires=requires,
            model_id=model_id,
            fallback_model_id=fallback_model_id,
        )
        session.add(assignment)
    else:
        assignment.model_id = model_id
        assignment.fallback_model_id = fallback_model_id
    session.flush()
    return assignment


def list_course_assignments(
    session: Session, course_id: int
) -> dict[str, CourseTaskAssignment]:
    return {
        assignment.task: assignment
        for assignment in session.scalars(
            select(CourseTaskAssignment).where(CourseTaskAssignment.course_id == course_id)
        )
    }


def list_course_default_assignments(
    session: Session, course_id: int
) -> dict[str, CourseDefaultTaskAssignment]:
    return {
        assignment.requires: assignment
        for assignment in session.scalars(
            select(CourseDefaultTaskAssignment).where(
                CourseDefaultTaskAssignment.course_id == course_id
            )
        )
    }


def seed_default_task_assignments(session: Session) -> None:
    for requires in DEFAULT_REQUIRES:
        if session.get(DefaultTaskAssignment, requires) is None:
            session.add(
                DefaultTaskAssignment(
                    requires=requires, model_id=None, fallback_model_id=None
                )
            )
    session.flush()


def list_assignments(session: Session) -> dict[str, TaskAssignment]:
    return {assignment.task: assignment for assignment in session.scalars(select(TaskAssignment))}


def list_default_assignments(session: Session) -> dict[str, DefaultTaskAssignment]:
    return {
        assignment.requires: assignment
        for assignment in session.scalars(select(DefaultTaskAssignment))
    }
