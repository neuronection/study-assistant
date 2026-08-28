from typing import Any

import jinja2
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.contracts.contracts import Constraint
from ..ai.skills import CONTEXT_VARS, SEED_COURSE_TYPES, SEED_ERROR_PATTERNS, SEEDS
from ..domain.models import Course, CourseType, ErrorPattern, Skill, SkillVersion, utcnow

SCOPE_TYPES = ("system", "course_type", "course")


class SkillsError(ValueError):
    pass


def seed_course_types(session: Session) -> None:
    for key, name, description in SEED_COURSE_TYPES:
        if session.scalars(select(CourseType).where(CourseType.key == key)).first() is None:
            session.add(CourseType(key=key, name=name, description=description))
    session.flush()


def seed_error_patterns(session: Session) -> None:
    for seed in SEED_ERROR_PATTERNS:
        if session.scalars(select(ErrorPattern).where(ErrorPattern.key == seed.key)).first():
            continue
        course_type = session.scalars(
            select(CourseType).where(CourseType.key == seed.course_type)
        ).first()
        session.add(
            ErrorPattern(
                key=seed.key,
                course_type_id=course_type.id if course_type is not None else None,
                name=seed.name,
                description=seed.description,
                example=seed.example,
                detection=seed.detection,
                is_system=True,
                is_active=True,
                order_idx=seed.order_idx,
                created_at=utcnow(),
            )
        )
    session.flush()


def seed_skills(session: Session) -> None:
    for seed in SEEDS:
        existing = session.scalars(select(Skill).where(Skill.key == seed.key)).first()
        if existing is None:
            existing = Skill(
                task=seed.task,
                key=seed.key,
                name=seed.name,
                description=seed.description,
                is_system=True,
            )
            session.add(existing)
            session.flush()
            session.add(
                SkillVersion(
                    skill_id=existing.id,
                    scope_type="system",
                    scope_ref=None,
                    version=1,
                    system_template=seed.system_prompt,
                    user_template=seed.user_template,
                    params=seed.params,
                    contract=seed.contract,
                    is_active=True,
                    created_at=utcnow(),
                )
            )
            continue
        system = session.scalars(
            select(SkillVersion)
            .where(
                SkillVersion.skill_id == existing.id,
                SkillVersion.scope_type == "system",
            )
            .order_by(SkillVersion.version.asc())
        ).first()
        if system is not None:
            SkillService(session)._refresh_system_template(seed.key, system)
        if existing.name != seed.name:
            existing.name = seed.name
        if existing.description != seed.description:
            existing.description = seed.description
    session.flush()


class SkillService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def skill(self, key: str) -> Skill:
        skill = self._session.scalars(select(Skill).where(Skill.key == key)).first()
        if skill is None:
            raise SkillsError(f"unknown skill '{key}'")
        return skill

    def resolve(
        self, key: str, course_id: int | None = None
    ) -> SkillVersion | None:
        skill = self._session.scalars(select(Skill).where(Skill.key == key)).first()
        if skill is None:
            return None
        course_type_id: int | None = None
        if course_id is not None:
            course = self._session.get(Course, course_id)
            if course is not None:
                course_type_id = course.course_type_id
        for scope_type, scope_ref in (
            ("course", course_id),
            ("course_type", course_type_id),
            ("system", None),
        ):
            if scope_type == "system":
                version = self._session.scalars(
                    select(SkillVersion)
                    .where(
                        SkillVersion.skill_id == skill.id,
                        SkillVersion.scope_type == "system",
                        SkillVersion.is_active.is_(True),
                    )
                    .order_by(SkillVersion.version.desc())
                ).first()
            else:
                version = self._session.scalars(
                    select(SkillVersion)
                    .where(
                        SkillVersion.skill_id == skill.id,
                        SkillVersion.scope_type == scope_type,
                        SkillVersion.scope_ref == scope_ref,
                        SkillVersion.is_active.is_(True),
                    )
                    .order_by(SkillVersion.version.desc())
                ).first()
            if version is not None:
                return version
        return None

    def resolution_chain(
        self, key: str, course_id: int | None = None
    ) -> dict[str, str]:
        skill = self._session.scalars(select(Skill).where(Skill.key == key)).first()
        chain: dict[str, str] = {}
        if skill is None:
            return chain
        course_type_id: int | None = None
        if course_id is not None:
            course = self._session.get(Course, course_id)
            if course is not None:
                course_type_id = course.course_type_id
        if course_id is not None:
            active = self._active(skill.id, "course", course_id)
            chain["course"] = f"v{active.version}" if active else "—"
        if course_type_id is not None:
            active = self._active(skill.id, "course_type", course_type_id)
            chain["course_type"] = f"v{active.version}" if active else "—"
        active = self._active(skill.id, "system", None)
        chain["system"] = f"v{active.version}" if active else "—"
        return chain

    def _active(
        self, skill_id: int, scope_type: str, scope_ref: int | None
    ) -> SkillVersion | None:
        return self._session.scalars(
            select(SkillVersion)
            .where(
                SkillVersion.skill_id == skill_id,
                SkillVersion.scope_type == scope_type,
                SkillVersion.scope_ref == scope_ref,
                SkillVersion.is_active.is_(True),
            )
            .order_by(SkillVersion.version.desc())
        ).first()

    def render(
        self,
        version: SkillVersion,
        context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        allowed = set(CONTEXT_VARS)
        clean = {k: v for k, v in (context or {}).items() if k in allowed}
        environment = jinja2.Environment(
            undefined=jinja2.Undefined,
            autoescape=False,
        )
        try:
            system = environment.from_string(version.system_template).render(**clean)
        except jinja2.TemplateError:
            system = version.system_template
        try:
            user = environment.from_string(version.user_template).render(**clean)
        except jinja2.TemplateError:
            user = version.user_template
        return system, user

    def validate_templates(self, system_template: str, user_template: str) -> None:
        environment = jinja2.Environment(undefined=jinja2.Undefined)
        try:
            environment.from_string(system_template).render(
                **dict.fromkeys(CONTEXT_VARS, "")
            )
            environment.from_string(user_template).render(
                **dict.fromkeys(CONTEXT_VARS, "")
            )
        except jinja2.TemplateError as error:
            raise SkillsError(f"template error: {error}") from error

    def constraints(
        self, version: SkillVersion, runtime: dict[str, Any] | None = None
    ) -> list[Constraint]:
        from .contract_builders import build_constraints

        return build_constraints(version, runtime or {})

    def save_version(
        self,
        key: str,
        *,
        scope_type: str,
        scope_ref: int | None,
        system_template: str,
        user_template: str = "",
        params: dict[str, Any] | None = None,
        contract: dict[str, Any] | None = None,
    ) -> SkillVersion:
        if scope_type not in SCOPE_TYPES:
            raise SkillsError(f"scope must be one of {SCOPE_TYPES}")
        self.validate_templates(system_template, user_template)
        skill = self.skill(key)
        latest = self._session.scalars(
            select(SkillVersion)
            .where(
                SkillVersion.skill_id == skill.id,
                SkillVersion.scope_type == scope_type,
                SkillVersion.scope_ref == scope_ref,
            )
            .order_by(SkillVersion.version.desc())
        ).first()
        next_version = (latest.version if latest else 0) + 1
        for stale in self._session.scalars(
            select(SkillVersion).where(
                SkillVersion.skill_id == skill.id,
                SkillVersion.scope_type == scope_type,
                SkillVersion.scope_ref == scope_ref,
                SkillVersion.is_active.is_(True),
            )
        ):
            stale.is_active = False
        version = SkillVersion(
            skill_id=skill.id,
            scope_type=scope_type,
            scope_ref=scope_ref,
            version=next_version,
            system_template=system_template,
            user_template=user_template,
            params=params,
            contract=contract,
            is_active=True,
            created_at=utcnow(),
        )
        self._session.add(version)
        self._session.flush()
        return version

    def activate(self, version_id: int) -> SkillVersion:
        version = self._session.get(SkillVersion, version_id)
        if version is None:
            raise SkillsError("version not found")
        for stale in self._session.scalars(
            select(SkillVersion).where(
                SkillVersion.skill_id == version.skill_id,
                SkillVersion.scope_type == version.scope_type,
                SkillVersion.scope_ref == version.scope_ref,
                SkillVersion.is_active.is_(True),
            )
        ):
            stale.is_active = False
        version.is_active = True
        self._session.flush()
        return version

    def restore_system(self, key: str) -> SkillVersion:
        skill = self.skill(key)
        system = self._session.scalars(
            select(SkillVersion)
            .where(
                SkillVersion.skill_id == skill.id,
                SkillVersion.scope_type == "system",
            )
            .order_by(SkillVersion.version.asc())
        ).first()
        if system is None:
            raise SkillsError("no system default for this skill")
        system = self._refresh_system_template(skill.key, system)
        return self.activate(system.id)

    def _refresh_system_template(
        self, key: str, system: SkillVersion
    ) -> SkillVersion:
        seed = next((seed for seed in SEEDS if seed.key == key), None)
        if (
            seed is not None
            and system.version == 1
            and system.system_template != seed.system_prompt
        ):
            system.system_template = seed.system_prompt
            system.user_template = seed.user_template
            self._session.flush()
        return system

    def versions(self, key: str) -> list[SkillVersion]:
        skill = self.skill(key)
        return list(
            self._session.scalars(
                select(SkillVersion)
                .where(SkillVersion.skill_id == skill.id)
                .order_by(SkillVersion.scope_type, SkillVersion.version)
            )
        )

    @staticmethod
    def diff(left: SkillVersion, right: SkillVersion) -> dict[str, Any]:
        from difflib import unified_diff

        system_diff = "".join(
            unified_diff(
                left.system_template.splitlines(keepends=True),
                right.system_template.splitlines(keepends=True),
                fromfile=f"v{left.version} system",
                tofile=f"v{right.version} system",
            )
        )
        user_diff = "".join(
            unified_diff(
                left.user_template.splitlines(keepends=True),
                right.user_template.splitlines(keepends=True),
                fromfile=f"v{left.version} user",
                tofile=f"v{right.version} user",
            )
        )
        return {"system": system_diff, "user": user_diff}
