"""ICS import: VEVENTs → planner items, bounded RRULE expansion.

Plan 85 C (ADR-213). File-only (no network, no OAuth). Times normalize to the
event's local calendar date for the all-day planner; every generated datetime
is normalized to naive UTC where one is retained (ADR-199). Expansion is
bounded by the planner horizon and a hard occurrence cap — an unbounded
`FREQ=DAILY` rule can never flood the planner.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.vocab import PlanItemKind
from ...domain.models import Course, PlanItem

MAX_OCCURRENCES_PER_EVENT = 200
MAX_TOTAL_OCCURRENCES = 500
MAX_ITERATIONS = 5000
WINDOW_PAST_DAYS = 30
WINDOW_FUTURE_DAYS = 180

EXAM_PATTERN = re.compile(
    r"\b(exam|final|midterm|test|quiz|prüfung|klausur|testat|εξέταση|διαγώνισμα)\b",
    re.IGNORECASE,
)

WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


class IcsImportError(ValueError):
    pass


@dataclass(frozen=True)
class IcsEvent:
    uid: str
    summary: str
    description: str
    location: str
    day: date
    start: time | None
    exam: bool


@dataclass(frozen=True)
class IcsPreview:
    events: list[IcsEvent]
    exam_candidates: list[IcsEvent]
    total_events: int
    skipped: int


def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _split_property(line: str) -> tuple[str, dict[str, str], str] | None:
    if ":" not in line:
        return None
    head, _colon, value = line.partition(":")
    parts = head.split(";")
    name = parts[0].upper()
    params: dict[str, str] = {}
    for part in parts[1:]:
        key, _eq, raw = part.partition("=")
        params[key.upper()] = raw
    return name, params, value


def _parse_datetime(value: str, params: dict[str, str]) -> datetime:
    raw = value.strip()
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", raw):
        return datetime.strptime(raw[:8], "%Y%m%d")
    if raw.endswith("Z"):
        return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    parsed = datetime.strptime(raw[:15], "%Y%m%dT%H%M%S")
    tzid = params.get("TZID", "").strip()
    if tzid:
        try:
            return parsed.replace(tzinfo=ZoneInfo(tzid))
        except ZoneInfoNotFoundError:
            return parsed.replace(tzinfo=UTC)
    return parsed.replace(tzinfo=UTC)


def _normalized_day(value: datetime) -> date:
    return value.astimezone(UTC).date() if value.tzinfo is not None else value.date()


def _unescape(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
        .strip()
    )


def _parse_rrule(value: str) -> dict[str, str]:
    rule: dict[str, str] = {}
    for part in value.split(";"):
        key, _eq, raw = part.partition("=")
        if key:
            rule[key.strip().upper()] = raw.strip().upper()
    return rule


def _add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    try:
        return date(year, month, day.day)
    except ValueError:
        return date(year, month, 28)


def _expand(
    start: datetime,
    rule: dict[str, str],
    window_start: date,
    window_end: date,
) -> list[date]:
    freq = rule.get("FREQ", "").upper()
    if freq not in ("DAILY", "WEEKLY", "MONTHLY"):
        return [_normalized_day(start)]
    interval = max(1, int(rule.get("INTERVAL", "1") or 1))
    count = int(rule["COUNT"]) if rule.get("COUNT", "").isdigit() else None
    until: date | None = None
    if rule.get("UNTIL"):
        try:
            until = _normalized_day(_parse_datetime(rule["UNTIL"], {}))
        except ValueError:
            until = None
    byday = [
        WEEKDAYS[token[-2:]] for token in rule.get("BYDAY", "").split(",") if token[-2:] in WEEKDAYS
    ]
    occurrences: list[date] = []
    generated = 0
    iterations = 0
    if freq == "WEEKLY" and byday:
        week_start = start.date() - timedelta(days=start.date().weekday())
        while iterations < MAX_ITERATIONS:
            iterations += 1
            week = week_start + timedelta(weeks=interval * iterations - interval)
            if week > window_end:
                break
            for weekday in sorted(set(byday)):
                candidate_day = week + timedelta(days=weekday)
                if candidate_day < start.date():
                    continue
                if until is not None and candidate_day > until:
                    return occurrences
                generated += 1
                if count is not None and generated > count:
                    return occurrences
                if window_start <= candidate_day <= window_end:
                    occurrences.append(candidate_day)
                if len(occurrences) >= MAX_OCCURRENCES_PER_EVENT:
                    return occurrences
            if until is not None and week > until:
                break
        return occurrences
    cursor = start.date()
    step = 0
    while iterations < MAX_ITERATIONS:
        iterations += 1
        if cursor > window_end:
            break
        if until is not None and cursor > until:
            break
        if count is not None and step >= count:
            break
        if window_start <= cursor <= window_end:
            occurrences.append(cursor)
        if len(occurrences) >= MAX_OCCURRENCES_PER_EVENT:
            break
        step += 1
        if freq == "DAILY":
            cursor = start.date() + timedelta(days=interval * step)
        elif freq == "WEEKLY":
            cursor = start.date() + timedelta(weeks=interval * step)
        else:
            cursor = _add_months(start.date(), interval * step)
    return occurrences


def parse_ics(text: str, *, today: date | None = None) -> IcsPreview:
    if not text.strip():
        raise IcsImportError("the calendar file is empty")
    lines = _unfold(text)
    if not any(line.strip().upper() == "BEGIN:VCALENDAR" for line in lines):
        raise IcsImportError("not an iCalendar file (missing BEGIN:VCALENDAR)")
    window_start = (today or datetime.now(UTC).date()) - timedelta(days=WINDOW_PAST_DAYS)
    window_end = (today or datetime.now(UTC).date()) + timedelta(days=WINDOW_FUTURE_DAYS)
    events: list[IcsEvent] = []
    total = 0
    skipped = 0
    block: dict[str, tuple[dict[str, str], str]] = {}
    inside = False
    for line in lines:
        stripped = line.strip()
        if stripped.upper() == "BEGIN:VEVENT":
            inside = True
            block = {}
            continue
        if stripped.upper() == "END:VEVENT":
            inside = False
            total += 1
            parsed = _event_occurrences(block, window_start, window_end)
            if not parsed:
                skipped += 1
            events.extend(parsed)
            continue
        if not inside:
            continue
        parsed_line = _split_property(line)
        if parsed_line is None:
            continue
        name, params, value = parsed_line
        block[name] = (params, value)
    if total == 0:
        raise IcsImportError("the calendar has no VEVENT entries")
    events.sort(key=lambda entry: (entry.day, entry.start or time(0), entry.summary))
    events = events[:MAX_TOTAL_OCCURRENCES]
    exam_candidates = [entry for entry in events if entry.exam]
    return IcsPreview(
        events=events,
        exam_candidates=exam_candidates,
        total_events=total,
        skipped=skipped,
    )


def _event_occurrences(
    block: dict[str, tuple[dict[str, str], str]], window_start: date, window_end: date
) -> list[IcsEvent]:
    if "DTSTART" not in block:
        return []
    summary = _unescape(block.get("SUMMARY", ({}, ""))[1]) or "Calendar event"
    description = _unescape(block.get("DESCRIPTION", ({}, ""))[1])
    location = _unescape(block.get("LOCATION", ({}, ""))[1])
    categories = _unescape(block.get("CATEGORIES", ({}, ""))[1])
    uid = _unescape(block.get("UID", ({}, ""))[1]) or f"{summary}:{block['DTSTART'][1]}"
    start_params, start_value = block["DTSTART"]
    try:
        start = _parse_datetime(start_value, start_params)
    except ValueError:
        return []
    exam = bool(EXAM_PATTERN.search(f"{summary} {categories}"))
    rule: dict[str, str] = {}
    if "RRULE" in block:
        rule = _parse_rrule(block["RRULE"][1])
    days = _expand(start, rule, window_start, window_end)
    start_time = None if start_params.get("VALUE", "").upper() == "DATE" else start.time()
    occurrences: list[IcsEvent] = []
    for index, day in enumerate(days):
        occurrence_uid = uid if index == 0 else f"{uid}#{day.isoformat()}"
        occurrences.append(
            IcsEvent(
                uid=occurrence_uid[:200],
                summary=summary[:300],
                description=description,
                location=location[:200],
                day=day,
                start=start_time,
                exam=exam,
            )
        )
    return occurrences


def apply_preview(
    session: Session, course: Course, preview: IcsPreview, *, confirm_exam: bool
) -> tuple[int, int, date | None]:
    created = 0
    updated = 0
    for event in preview.events:
        existing = session.scalars(
            select(PlanItem).where(
                PlanItem.course_id == course.id,
                PlanItem.external_uid == event.uid,
            )
        ).first()
        detail_parts = [
            part
            for part in (
                event.start.strftime("%H:%M") if event.start else None,
                event.location or None,
            )
            if part
        ]
        detail = " · ".join(detail_parts)[:500] or None
        kind = PlanItemKind.MILESTONE.value if event.exam else PlanItemKind.STUDY.value
        if existing is not None:
            existing.title = event.summary[:300]
            existing.detail = detail
            existing.kind = kind
            if existing.done_at is None:
                existing.due_date = event.day
            updated += 1
            continue
        session.add(
            PlanItem(
                profile_id=course.profile_id,
                course_id=course.id,
                title=event.summary[:300],
                detail=detail,
                kind=kind,
                due_date=event.day,
                origin="manual",
                sort_key=0,
                external_uid=event.uid,
            )
        )
        created += 1
    exam_date: date | None = None
    if confirm_exam and preview.exam_candidates:
        exam_date = min(entry.day for entry in preview.exam_candidates)
        course.exam_date = exam_date
    session.flush()
    return created, updated, exam_date
