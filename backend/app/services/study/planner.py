from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...core.vocab import PlanItemKind, PlanItemOrigin
from ...domain.models import Course, PlanItem, TreeNode, utcnow
from ..knowledge.tree import TreeService
from ..platform.metrics import answer_rows, weakness_matrix

MAX_PLAN_HORIZON_DAYS = 180
MAX_WEAK_PRACTICE_ITEMS = 3
WEAK_CELL_ACCURACY = 0.7


class PlannerError(ValueError):
    pass


@dataclass(frozen=True)
class PlannedNode:
    node_id: int
    title: str


def _engaged(entry: dict[str, Any]) -> bool:
    counts = entry.get("counts") or {}
    return bool(
        counts.get("studied", 0) > 0
        or counts.get("notes", 0) > 0
        or counts.get("quizzes", 0) > 0
        or counts.get("exercises", 0) > 0
    )


def _inner_nodes(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stack = list(tree)
    inner: list[dict[str, Any]] = []
    while stack:
        entry = stack.pop(0)
        if not entry.get("is_root"):
            inner.append(entry)
        stack[:0] = entry.get("children", [])
    return inner


def _weak_concepts(
    session: Session, profile_id: int, course_id: int
) -> list[str]:
    rows = answer_rows(session, profile_id, course_id=course_id)
    cells = [
        cell
        for cell in weakness_matrix(rows)
        if cell.get("n", 0) >= 3
        and float(cell.get("accuracy", 1.0)) < WEAK_CELL_ACCURACY
    ]
    cells.sort(key=lambda cell: float(cell.get("accuracy", 1.0)))
    return [str(cell["concept"]) for cell in cells[:MAX_WEAK_PRACTICE_ITEMS]]


def _distribute(
    remaining: list[PlannedNode], n_days: int
) -> list[list[PlannedNode]]:
    if not remaining:
        return []
    groups: list[list[PlannedNode]] = []
    if len(remaining) <= n_days:
        spacing = n_days // len(remaining)
        cursor = 0
        for node in remaining:
            groups.append([node])
            cursor += max(1, spacing)
        return groups
    base, extra = divmod(len(remaining), n_days)
    index = 0
    for day in range(n_days):
        size = base + (1 if day < extra else 0)
        groups.append(remaining[index : index + size])
        index += size
    return groups


def generate_plan(
    session: Session, course: Course, profile_id: int
) -> list[PlanItem]:
    today = utcnow().date()
    exam = course.exam_date
    if exam is None:
        raise PlannerError("set an exam date first — the plan paces toward it")
    days_left = (exam - today).days
    if days_left <= 0:
        raise PlannerError("the exam date has passed — move it to generate a plan")
    horizon = min(days_left, MAX_PLAN_HORIZON_DAYS)

    tree = TreeService(session).tree(course.id, profile_id)
    inner_entries = _inner_nodes(tree)
    remaining = [
        PlannedNode(node_id=int(entry["id"]), title=str(entry["title"]))
        for entry in inner_entries
        if not _engaged(entry)
    ]
    total_inner = len(inner_entries)
    weak = _weak_concepts(session, profile_id, course.id)

    session.execute(
        delete(PlanItem).where(
            PlanItem.course_id == course.id,
            PlanItem.origin == PlanItemOrigin.DRAFT.value,
            PlanItem.done_at.is_(None),
            PlanItem.due_date >= today,
        )
    )

    items: list[tuple[date, int, PlanItem]] = []

    def add(
        due: date, sort_key: int, title: str, kind: PlanItemKind, detail: str | None
    ) -> None:
        items.append(
            (
                due,
                sort_key,
                PlanItem(
                    profile_id=profile_id,
                    course_id=course.id,
                    title=title[:300],
                    detail=detail[:500] if detail else None,
                    kind=kind.value,
                    due_date=due,
                    origin=PlanItemOrigin.DRAFT.value,
                    sort_key=sort_key,
                ),
            )
        )

    day_shift = 1 if days_left > 1 else 0
    study_days = max(1, horizon - day_shift)
    groups = _distribute(remaining, study_days)
    for index, group in enumerate(groups):
        due = today + timedelta(days=day_shift + index)
        if group:
            titles = " + ".join(node.title for node in group[:3])
            extra = len(group) - 3
            if extra > 0:
                titles += f" + {extra} more"
            detail = f"{len(group)} untouched node(s)"
            add(due, index * 10, f"Study: {titles}", PlanItemKind.STUDY, detail)

    practice_slots = sorted(
        {
            max(0, min(study_days - 1, (horizon // (MAX_WEAK_PRACTICE_ITEMS + 1)) * slot))
            for slot in range(1, MAX_WEAK_PRACTICE_ITEMS + 1)
        }
    )
    if weak:
        from ..platform.metrics import course_readiness

        forecast = course_readiness(
            session,
            profile_id,
            course.id,
            total_nodes=total_inner,
            engaged_nodes=total_inner - len(remaining),
        )
        if forecast["readiness_state"] == "ok":
            practice_slots = sorted(
                {0, *practice_slots[: MAX_WEAK_PRACTICE_ITEMS - 1]}
            )
    for slot_index, concept in enumerate(weak):
        day_index = practice_slots[slot_index % len(practice_slots)] if practice_slots else 0
        due = today + timedelta(days=day_shift + day_index)
        add(
            due,
            1000 + day_index * 10,
            f"Practice: {concept}",
            PlanItemKind.PRACTICE,
            "weak cell from recent answers",
        )

    for week in range(1, horizon // 7 + 1):
        due = today + timedelta(days=min(7 * week, horizon))
        add(
            due,
            2000 + week * 10,
            f"Weekly review — week {week}",
            PlanItemKind.REVIEW,
            None,
        )
    add(
        today + timedelta(days=horizon),
        9000,
        f"Exam: {course.title}",
        PlanItemKind.MILESTONE,
        None,
    )

    session.add_all(item for _due, _key, item in items)
    session.flush()
    ordered = session.scalars(
        select(PlanItem)
        .where(
            PlanItem.course_id == course.id,
            PlanItem.origin == PlanItemOrigin.DRAFT.value,
            PlanItem.done_at.is_(None),
        )
        .order_by(PlanItem.due_date, PlanItem.sort_key, PlanItem.id)
    ).all()
    return list(ordered)


def upcoming_items(session: Session, profile_id: int, days: int = 7) -> list[dict[str, Any]]:
    today = utcnow().date()
    end = today + timedelta(days=max(1, min(days, 60)))
    rows = session.execute(
        select(PlanItem, Course)
        .join(Course, PlanItem.course_id == Course.id)
        .where(
            PlanItem.profile_id == profile_id,
            PlanItem.due_date >= today,
            PlanItem.due_date <= end,
            PlanItem.done_at.is_(None),
        )
        .order_by(PlanItem.due_date, PlanItem.sort_key, PlanItem.id)
    ).all()
    return [
        {
            "id": item.id,
            "course_id": item.course_id,
            "course_title": course.title,
            "node_id": item.node_id,
            "title": item.title,
            "detail": item.detail,
            "kind": item.kind,
            "due_date": item.due_date.isoformat(),
            "origin": item.origin,
        }
        for item, course in rows
    ]


def node_title(session: Session, node_id: int | None) -> str | None:
    if node_id is None:
        return None
    node = session.get(TreeNode, node_id)
    return node.title if node is not None else None


ICS_DONE_WINDOW_DAYS = 7
ICS_PRODID = "-//Study Assistant//Plan//EN"


def _ics_escape(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return escaped.replace("\r\n", "\\n").replace("\n", "\\n")


def _ics_fold(line: str) -> list[str]:
    octets = line
    lines: list[str] = []
    while len(octets.encode("utf-8")) > 75:
        cut = 75
        while cut > 1 and len(octets[:cut].encode("utf-8")) > 75:
            cut -= 1
        lines.append(octets[:cut])
        octets = " " + octets[cut:]
    lines.append(octets)
    return lines


def _ics_all_day_event(
    *, uid: str, stamp: str, day: date, summary: str, status: str, description: str | None
) -> list[str]:
    start = day.strftime("%Y%m%d")
    end = (day + timedelta(days=1)).strftime("%Y%m%d")
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{start}",
        f"DTEND;VALUE=DATE:{end}",
        f"SUMMARY:{_ics_escape(summary)}",
        f"STATUS:{status}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{_ics_escape(description)}")
    lines.append("END:VEVENT")
    return lines


def build_course_ics(session: Session, course: Course) -> str:
    now = utcnow()
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    done_cutoff = (now - timedelta(days=ICS_DONE_WINDOW_DAYS)).date()

    items = list(
        session.scalars(
            select(PlanItem)
            .where(
                PlanItem.course_id == course.id,
                (PlanItem.done_at.is_(None)) | (PlanItem.done_at >= done_cutoff),
            )
            .order_by(PlanItem.due_date, PlanItem.id)
        )
    )
    events: list[str] = []
    for item in items:
        events.extend(
            _ics_all_day_event(
                uid=f"planitem-{item.id}@studyassistant.local",
                stamp=stamp,
                day=item.due_date,
                summary=item.title,
                status="CANCELLED" if item.done_at is not None else "CONFIRMED",
                description=item.detail,
            )
        )
    if course.exam_date is not None:
        events.extend(
            _ics_all_day_event(
                uid=f"exam-{course.id}@studyassistant.local",
                stamp=stamp,
                day=course.exam_date,
                summary=f"Exam: {course.title}",
                status="CONFIRMED",
                description=None,
            )
        )

    body_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{ICS_PRODID}",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_ics_escape(course.title)}",
        *events,
        "END:VCALENDAR",
    ]
    folded: list[str] = []
    for line in body_lines:
        folded.extend(_ics_fold(line))
    return "\r\n".join(folded) + "\r\n"
