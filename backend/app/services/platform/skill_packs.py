from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...ai.tasks import TASKS_BY_NAME
from ...domain.models import Skill, SkillVersion, utcnow
from .skills import SkillsError, SkillService

PACK_FORMAT = "ca-skills/v1"
RESOLUTIONS = ("replace", "rename", "skip")
PACK_SKILL_KEYS = ("task", "key", "name", "versions")


class PackError(ValueError):
    pass


def _version_payload(version: SkillVersion) -> dict[str, Any]:
    return {
        "version": version.version,
        "system_template": version.system_template,
        "user_template": version.user_template,
        "params": version.params,
        "contract": version.contract,
        "is_active": version.is_active,
    }


def export_skill_pack(session: Session, keys: list[str]) -> dict[str, Any]:
    if not keys:
        raise PackError("no skills selected for export")
    skills: list[dict[str, Any]] = []
    for key in keys:
        skill = session.scalars(select(Skill).where(Skill.key == key)).first()
        if skill is None:
            raise PackError(f"unknown skill '{key}'")
        versions = list(
            session.scalars(
                select(SkillVersion)
                .where(
                    SkillVersion.skill_id == skill.id,
                    SkillVersion.scope_type == "system",
                )
                .order_by(SkillVersion.version)
            )
        )
        if not versions:
            raise PackError(f"skill '{key}' has no system-scope versions to export")
        skills.append(
            {
                "task": skill.task,
                "key": skill.key,
                "name": skill.name,
                "description": skill.description,
                "is_system": skill.is_system,
                "versions": [_version_payload(version) for version in versions],
            }
        )
    return {
        "format": PACK_FORMAT,
        "exported_at": utcnow().isoformat(),
        "skills": skills,
    }


def _parse_pack(session: Session, payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise PackError("pack must be a JSON object")
    if payload.get("format") != PACK_FORMAT:
        raise PackError(f"unsupported pack format: {payload.get('format')!r}")
    entries = payload.get("skills")
    if not isinstance(entries, list) or not entries:
        raise PackError("pack has no skills")
    for entry in entries:
        if not isinstance(entry, dict):
            raise PackError("pack skill entries must be objects")
        for required in PACK_SKILL_KEYS:
            if not entry.get(required):
                raise PackError(f"pack skill is missing '{required}'")
        if not isinstance(entry["versions"], list):
            raise PackError(f"pack skill '{entry['key']}' has no versions")
        if entry.get("task") not in TASKS_BY_NAME:
            raise PackError(
                f"pack skill '{entry['key']}' references unknown task '{entry.get('task')}'"
            )
    return entries


def _validate_entry(session: Session, entry: dict[str, Any]) -> list[str]:
    service = SkillService(session)
    errors: list[str] = []
    for version in entry["versions"]:
        if not isinstance(version, dict):
            errors.append("version entry is not an object")
            continue
        system_template = version.get("system_template")
        if not isinstance(system_template, str) or not system_template.strip():
            errors.append("system_template is required")
            continue
        try:
            service.validate_templates(system_template, version.get("user_template") or "")
        except SkillsError as error:
            errors.append(str(error))
    return errors


def preview_skill_pack(session: Session, payload: Any) -> dict[str, Any]:
    entries = _parse_pack(session, payload)
    skills: list[dict[str, Any]] = []
    for entry in entries:
        key = str(entry["key"])
        existing = session.scalars(select(Skill).where(Skill.key == key)).first()
        skills.append(
            {
                "key": key,
                "task": entry["task"],
                "name": entry["name"],
                "description": entry.get("description"),
                "version_count": len(entry["versions"]),
                "active_version": next(
                    (
                        version.get("version")
                        for version in entry["versions"]
                        if isinstance(version, dict) and version.get("is_active")
                    ),
                    None,
                ),
                "collision": existing is not None,
                "errors": _validate_entry(session, entry),
            }
        )
    return {"format": PACK_FORMAT, "skills": skills}


def _unique_key(session: Session, key: str) -> str:
    candidate = key
    suffix = 2
    while session.scalars(select(Skill).where(Skill.key == candidate)).first() is not None:
        candidate = f"{key}-{suffix}"
        suffix += 1
    return candidate


def _write_versions(session: Session, skill: Skill, entry: dict[str, Any]) -> None:
    incoming = [version for version in entry["versions"] if isinstance(version, dict)]
    active_version = next(
        (
            version.get("version")
            for version in incoming
            if version.get("is_active")
        ),
        None,
    )
    latest = session.scalars(
        select(SkillVersion)
        .where(
            SkillVersion.skill_id == skill.id,
            SkillVersion.scope_type == "system",
        )
        .order_by(SkillVersion.version.desc())
        .limit(1)
    ).first()
    next_version = latest.version if latest is not None else 0
    activate_id: int | None = None
    for version in incoming:
        next_version += 1
        row = SkillVersion(
            skill_id=skill.id,
            scope_type="system",
            scope_ref=None,
            version=next_version,
            system_template=str(version.get("system_template") or ""),
            user_template=str(version.get("user_template") or ""),
            params=version.get("params"),
            contract=version.get("contract"),
            is_active=False,
            created_at=utcnow(),
        )
        session.add(row)
        session.flush()
        if active_version is None or version.get("version") == active_version:
            activate_id = row.id
    if activate_id is not None:
        for stale in session.scalars(
            select(SkillVersion).where(
                SkillVersion.skill_id == skill.id,
                SkillVersion.scope_type == "system",
                SkillVersion.scope_ref.is_(None),
                SkillVersion.is_active.is_(True),
            )
        ):
            stale.is_active = False
        activated = session.get(SkillVersion, activate_id)
        if activated is not None:
            activated.is_active = True
    session.flush()


def import_skill_pack(
    session: Session,
    payload: Any,
    resolutions: dict[str, str] | None = None,
) -> dict[str, Any]:
    entries = _parse_pack(session, payload)
    chosen = resolutions or {}
    for key, resolution in chosen.items():
        if resolution not in RESOLUTIONS:
            raise PackError(f"invalid resolution '{resolution}' for skill '{key}'")
    created: list[str] = []
    replaced: list[str] = []
    renamed: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for entry in entries:
        key = str(entry["key"])
        errors = _validate_entry(session, entry)
        if errors:
            skipped.append({"key": key, "reason": "; ".join(errors)})
            continue
        existing = session.scalars(select(Skill).where(Skill.key == key)).first()
        if existing is not None:
            resolution = chosen.get(key, "skip")
            if resolution == "skip":
                skipped.append({"key": key, "reason": "collision — skipped"})
                continue
            if resolution == "rename":
                new_key = _unique_key(session, key)
                skill = Skill(
                    task=str(entry["task"]),
                    key=new_key,
                    name=str(entry["name"]),
                    description=entry.get("description"),
                    is_system=False,
                )
                session.add(skill)
                session.flush()
                _write_versions(session, skill, entry)
                renamed.append({"key": key, "new_key": new_key})
                continue
            _write_versions(session, existing, entry)
            replaced.append(key)
            continue
        skill = Skill(
            task=str(entry["task"]),
            key=key,
            name=str(entry["name"]),
            description=entry.get("description"),
            is_system=False,
        )
        session.add(skill)
        session.flush()
        _write_versions(session, skill, entry)
        created.append(key)
    session.flush()
    return {
        "created": created,
        "replaced": replaced,
        "renamed": renamed,
        "skipped": skipped,
    }
