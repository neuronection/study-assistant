import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.vocab import AttemptMode
from ...domain.models import (
    Activity,
    Answer,
    Attempt,
    Concept,
    ConceptSkillStat,
    Course,
    DailyRollup,
    Exercise,
    FsrsState,
    ItemStat,
    Question,
    ReviewLog,
    StudyGoal,
    utcnow,
)

MIN_CELL_N = 3
ITEM_FLAG_MIN_N = 20
WEAKNESS_WEIGHTS = {"accuracy": 0.6, "recency": 0.2, "volume": 0.2}
SKILLS = ("conceptual", "procedural", "applied", "notation")
XP_PER_CORRECT = 10
XP_PER_ANSWER = 2
XP_PER_CARD = 3


@dataclass(frozen=True)
class AnswerRow:
    correct: bool
    partial_credit: float
    concept: str
    concept_id: int | None
    skill: str
    time_ms: int | None
    expected_time_sec: int | None
    error_tags: list[str]
    response: dict[str, Any] | None
    question_id: int
    created_at: datetime


def answer_rows(
    session: Session, profile_id: int, course_id: int | None = None
) -> list[AnswerRow]:
    statement = (
        select(Answer, Question, Activity)
        .join(Question, Answer.question_id == Question.id)
        .join(Attempt, Answer.attempt_id == Attempt.id)
        .join(Activity, Attempt.activity_id == Activity.id)
        .where(Activity.profile_id == profile_id, Attempt.mode != AttemptMode.EXAM.value)
    )
    if course_id is not None:
        statement = statement.where(Activity.course_id == course_id)
    rows = session.execute(statement.order_by(Answer.id)).all()
    concept_ids_by_course: dict[int, dict[str, int]] = {}

    def concept_id_for(course_key: int, name: str) -> int | None:
        if course_key not in concept_ids_by_course:
            concept_ids_by_course[course_key] = {
                concept.name: concept.id
                for concept in session.scalars(
                    select(Concept).where(Concept.course_id == course_key)
                )
            }
        return concept_ids_by_course[course_key].get(name.strip().lower())

    result: list[AnswerRow] = []
    for answer, question, activity in rows:
        tags = question.tags or []
        concept = str(tags[0] if tags else "untagged")
        concept_id = (
            concept_id_for(activity.course_id, concept)
            if activity.course_id is not None
            else None
        )
        result.append(
            AnswerRow(
                correct=bool(answer.correct),
                partial_credit=float(answer.partial_credit or 0.0),
                concept=concept,
                concept_id=concept_id,
                skill=str(question.skill or "conceptual"),
                time_ms=answer.time_ms,
                expected_time_sec=question.expected_time_sec,
                error_tags=list(answer.error_tags or []),
                response=answer.response,
                question_id=question.id,
                created_at=answer.created_at,
            )
        )
    return result


def weakness_matrix(rows: list[AnswerRow]) -> list[dict[str, Any]]:
    cells: dict[tuple[str, str], list[AnswerRow]] = {}
    for row in rows:
        cells.setdefault((row.concept, row.skill), []).append(row)
    matrix: list[dict[str, Any]] = []
    for (concept, skill), cell_rows in sorted(cells.items()):
        n = len(cell_rows)
        accuracy = sum(1 for r in cell_rows if r.correct) / n
        ratios = [
            r.time_ms / (r.expected_time_sec * 1000)
            for r in cell_rows
            if r.time_ms and r.expected_time_sec
        ]
        last_seen = max(r.created_at for r in cell_rows)
        concept_ids = {r.concept_id for r in cell_rows if r.concept_id is not None}
        matrix.append(
            {
                "concept": concept,
                "concept_id": concept_ids.pop() if len(concept_ids) == 1 else None,
                "skill": skill,
                "n": n,
                "accuracy": round(accuracy, 4),
                "avg_time_ratio": round(sum(ratios) / len(ratios), 3) if ratios else None,
                "last_seen_at": last_seen.isoformat(),
                "weakness_score": round(_weakness(accuracy, n, last_seen), 4),
                "enough_data": n >= MIN_CELL_N,
            }
        )
    return matrix


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _weakness(accuracy: float, n: int, last_seen: datetime) -> float:
    volume = min(1.0, n / 10.0)
    age_days = (
        (utcnow() - _aware(last_seen)).total_seconds() / 86400.0 if last_seen else 0.0
    )
    recency = min(1.0, age_days / 14.0)
    return (
        WEAKNESS_WEIGHTS["accuracy"] * (1.0 - accuracy) * volume
        + WEAKNESS_WEIGHTS["recency"] * recency * volume
        + WEAKNESS_WEIGHTS["volume"] * 0.0
    )


def error_profile(
    session: Session, profile_id: int, course_id: int | None = None
) -> list[dict[str, Any]]:
    now = utcnow()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    statement = (
        select(Answer.error_tags, Answer.created_at)
        .join(Attempt, Answer.attempt_id == Attempt.id)
        .join(Activity, Attempt.activity_id == Activity.id)
        .where(Activity.profile_id == profile_id, Answer.error_tags.is_not(None))
    )
    if course_id is not None:
        statement = statement.where(Activity.course_id == course_id)
    rows = session.execute(statement.order_by(Answer.id)).all()
    totals: dict[str, int] = {}
    recent: dict[str, int] = {}
    previous: dict[str, int] = {}
    last_seen: dict[str, datetime] = {}
    for tags, created_at in rows:
        moment = _aware(created_at)
        for tag in tags or []:
            totals[tag] = totals.get(tag, 0) + 1
            if moment >= week_ago:
                recent[tag] = recent.get(tag, 0) + 1
            elif moment >= two_weeks_ago:
                previous[tag] = previous.get(tag, 0) + 1
            last_seen[tag] = max(last_seen.get(tag, moment), moment)
    profile: list[dict[str, Any]] = [
        {
            "tag": tag,
            "total": total,
            "recent_7d": recent.get(tag, 0),
            "previous_7d": previous.get(tag, 0),
            "trend": recent.get(tag, 0) - previous.get(tag, 0),
            "last_seen_at": last_seen[tag].isoformat(),
        }
        for tag, total in totals.items()
    ]
    profile.sort(key=lambda entry: (-entry["total"], entry["tag"]))
    return profile


def speed_accuracy(rows: list[AnswerRow]) -> list[dict[str, Any]]:
    by_concept: dict[str, list[AnswerRow]] = {}
    for row in rows:
        by_concept.setdefault(row.concept, []).append(row)
    result = []
    for concept, concept_rows in sorted(by_concept.items()):
        ratios = [
            r.time_ms / (r.expected_time_sec * 1000)
            for r in concept_rows
            if r.time_ms and r.expected_time_sec
        ]
        if not ratios:
            continue
        accuracy = sum(1 for r in concept_rows if r.correct) / len(concept_rows)
        avg_ratio = sum(ratios) / len(ratios)
        speed = "rushing" if avg_ratio < 0.6 else "slow" if avg_ratio > 1.4 else "normal"
        quadrant = _quadrant(avg_ratio, accuracy)
        result.append(
            {
                "concept": concept,
                "n": len(concept_rows),
                "accuracy": round(accuracy, 4),
                "avg_time_ratio": round(avg_ratio, 3),
                "speed": speed,
                "quadrant": quadrant,
            }
        )
    return result


def _quadrant(time_ratio: float, accuracy: float) -> str:
    fast = time_ratio < 1.0
    accurate = accuracy >= 0.7
    if fast and accurate:
        return "fluent"
    if fast and not accurate:
        return "rushing"
    if not fast and accurate:
        return "effortful"
    return "struggling"


def item_analysis(session: Session, profile_id: int) -> list[dict[str, Any]]:
    rows = session.execute(
        select(Answer, Question)
        .join(Question, Answer.question_id == Question.id)
        .join(Attempt, Answer.attempt_id == Attempt.id)
        .join(Activity, Attempt.activity_id == Activity.id)
        .where(Activity.profile_id == profile_id)
        .order_by(Answer.id)
    ).all()
    grouped: dict[int, list[tuple[Answer, Question]]] = {}
    for answer, question in rows:
        grouped.setdefault(question.id, []).append((answer, question))
    stats: list[dict[str, Any]] = []
    for question_id, entries in sorted(grouped.items()):
        n = len(entries)
        p_correct = sum(1 for a, _q in entries if a.correct) / n
        times = [a.time_ms for a, _q in entries if a.time_ms]
        expected = entries[0][1].expected_time_sec
        distractors: dict[str, int] = {}
        for answer, question in entries:
            value = (answer.response or {}).get("value")
            if question.type in ("single", "multi") and isinstance(value, (int, list)):
                choices = value if isinstance(value, list) else [value]
                for choice in choices:
                    key = str(choice)
                    distractors[key] = distractors.get(key, 0) + 1
        avg_time = sum(times) / len(times) if times else None
        ratio = avg_time / (expected * 1000) if avg_time and expected else None
        flag = "ok"
        if n >= ITEM_FLAG_MIN_N and not 0.1 <= p_correct <= 0.95:
            flag = "review"
        stats.append(
            {
                "question_id": question_id,
                "n_attempts": n,
                "p_correct": round(p_correct, 4),
                "avg_time_ms": round(avg_time) if avg_time else None,
                "avg_time_ratio": round(ratio, 3) if ratio else None,
                "distractor_selection": distractors or None,
                "flag": flag,
                "stem_excerpt": _stem_excerpt(entries[0][1]),
            }
        )
    return stats


def _stem_excerpt(question: Question) -> str:
    if not question.stem:
        return ""
    return str(question.stem[0].get("md", ""))[:80]


def _day_key(moment: datetime) -> str:
    return moment.date().isoformat()


def daily_history(session: Session, profile_id: int) -> list[dict[str, Any]]:
    rows = session.execute(
        select(Answer.time_ms, Answer.correct, Answer.created_at)
        .join(Attempt, Answer.attempt_id == Attempt.id)
        .join(Activity, Attempt.activity_id == Activity.id)
        .where(Activity.profile_id == profile_id)
        .order_by(Answer.id)
    ).all()
    cards = session.execute(
        select(ReviewLog.reviewed_at)
        .join(Exercise, ReviewLog.card_id == Exercise.id)
        .where(Exercise.profile_id == profile_id, Exercise.kind.like("card_%"))
    ).all()
    days: dict[str, dict[str, Any]] = {}
    for time_ms, correct, created_at in rows:
        key = _day_key(created_at)
        entry = days.setdefault(
            key, {"answers_n": 0, "correct_n": 0, "cards_reviewed": 0, "minutes": 0.0}
        )
        entry["answers_n"] += 1
        entry["correct_n"] += 1 if correct else 0
        entry["minutes"] += (time_ms or 0) / 60000.0
    for (reviewed_at,) in cards:
        key = _day_key(reviewed_at)
        entry = days.setdefault(
            key, {"answers_n": 0, "correct_n": 0, "cards_reviewed": 0, "minutes": 0.0}
        )
        entry["cards_reviewed"] += 1
    history = []
    for key in sorted(days):
        entry = days[key]
        xp = (
            entry["correct_n"] * XP_PER_CORRECT
            + (entry["answers_n"] - entry["correct_n"]) * XP_PER_ANSWER
            + entry["cards_reviewed"] * XP_PER_CARD
        )
        history.append(
            {
                "day": key,
                "answers_n": entry["answers_n"],
                "correct_n": entry["correct_n"],
                "cards_reviewed": entry["cards_reviewed"],
                "minutes": round(entry["minutes"], 2),
                "xp": xp,
            }
        )
    return history


def streak(history: list[dict[str, Any]]) -> int:
    if not history:
        return 0
    active = {entry["day"] for entry in history if entry["answers_n"] or entry["cards_reviewed"]}
    if not active:
        return 0
    today = utcnow().date()
    current = 0
    cursor = today
    if today.isoformat() not in active:
        cursor = today - timedelta(days=1)
    while cursor.isoformat() in active:
        current += 1
        cursor = cursor - timedelta(days=1)
    return current


def due_cards_count(
    session: Session, profile_id: int, course_id: int | None = None
) -> int:
    now = utcnow()
    due_statement = (
        select(FsrsState.card_id)
        .join(Exercise, FsrsState.card_id == Exercise.id)
        .where(
            Exercise.profile_id == profile_id,
            Exercise.kind.like("card_%"),
            FsrsState.due_at <= now,
        )
    )
    unscheduled_statement = (
        select(Exercise.id)
        .outerjoin(FsrsState, FsrsState.card_id == Exercise.id)
        .where(
            Exercise.profile_id == profile_id,
            Exercise.kind.like("card_%"),
            FsrsState.id.is_(None),
        )
    )
    if course_id is not None:
        due_statement = due_statement.where(Exercise.course_id == course_id)
        unscheduled_statement = unscheduled_statement.where(
            Exercise.course_id == course_id
        )
    due = len(session.execute(due_statement).all())
    unscheduled = session.execute(unscheduled_statement).all()
    return due + len(unscheduled)


def get_goal(session: Session, profile_id: int) -> int:
    goal = session.get(StudyGoal, profile_id)
    return goal.answers_per_day if goal else 20


def set_goal(session: Session, profile_id: int, answers_per_day: int) -> int:
    goal = session.get(StudyGoal, profile_id)
    if goal is None:
        goal = StudyGoal(profile_id=profile_id, answers_per_day=answers_per_day)
        session.add(goal)
    else:
        goal.answers_per_day = answers_per_day
    session.flush()
    return goal.answers_per_day


def exam_status(session: Session, profile_id: int) -> list[dict[str, Any]]:
    from ..knowledge.tree import TreeService

    courses = list(
        session.scalars(
            select(Course).where(
                Course.profile_id == profile_id,
                Course.exam_date.is_not(None),
            )
        )
    )
    today = utcnow().date()
    result: list[dict[str, Any]] = []
    for course in courses:
        assert course.exam_date is not None
        days_left = (course.exam_date - today).days
        if days_left < 0 or days_left > 30:
            continue
        tree = TreeService(session).tree(course.id, profile_id)
        nodes: list[dict[str, Any]] = []

        def walk(entry: dict[str, Any], sink: list[dict[str, Any]]) -> None:
            sink.append(entry)
            for child in entry.get("children", []):
                walk(child, sink)

        for root_entry in tree:
            walk(root_entry, nodes)
        inner = [entry for entry in nodes if not entry.get("is_root")]

        def engaged(entry: dict[str, Any]) -> bool:
            counts = entry.get("counts") or {}
            return bool(
                counts.get("studied", 0) > 0
                or counts.get("notes", 0) > 0
                or counts.get("quizzes", 0) > 0
                or counts.get("exercises", 0) > 0
            )

        total = len(inner)
        engaged_count = sum(1 for entry in inner if engaged(entry))
        remaining = total - engaged_count
        behind = next(
            (
                {"id": entry["id"], "title": entry["title"]}
                for entry in inner
                if not engaged(entry)
            ),
            None,
        )
        pace = round(remaining / days_left, 1) if days_left > 0 else None
        result.append(
            {
                "course_id": course.id,
                "course_title": course.title,
                "exam_date": course.exam_date.isoformat(),
                "days_left": days_left,
                "total_nodes": total,
                "engaged_nodes": engaged_count,
                "remaining_nodes": remaining,
                "nodes_per_day": pace,
                "on_track": pace is not None and pace <= 1.5,
                "most_behind_node": behind,
            }
        )
    result.sort(key=lambda entry: entry["days_left"])
    return result


def overview(session: Session, profile_id: int) -> dict[str, Any]:
    history = daily_history(session, profile_id)
    today_key = _day_key(utcnow())
    today = next((entry for entry in history if entry["day"] == today_key), None)
    total_xp = sum(entry["xp"] for entry in history)
    level = int(math.sqrt(total_xp / 100)) + 1
    return {
        "today": today
        or {
            "day": today_key,
            "answers_n": 0,
            "correct_n": 0,
            "cards_reviewed": 0,
            "minutes": 0.0,
            "xp": 0,
        },
        "goal": get_goal(session, profile_id),
        "streak": streak(history),
        "total_xp": total_xp,
        "level": level,
        "due_cards": due_cards_count(session, profile_id),
        "history": history[-90:],
    }


def recommendations(
    session: Session, profile_id: int, course_id: int | None = None
) -> list[dict[str, Any]]:
    rows = answer_rows(session, profile_id, course_id)
    matrix = weakness_matrix(rows)
    recs: list[dict[str, Any]] = []

    due = due_cards_count(session, profile_id, course_id)
    if due > 0:
        recs.append(
            {
                "kind": "review",
                "priority": 100 + min(due, 20),
                "title_key": "review_due",
                "concept": None,
                "evidence": {"due_cards": due},
            }
        )

    weak_cells = [c for c in matrix if c["enough_data"]]
    weak_cells.sort(key=lambda c: -c["weakness_score"])
    for cell in weak_cells[:3]:
        misses = round(cell["n"] * (1 - cell["accuracy"]))
        recs.append(
            {
                "kind": "read" if cell["skill"] == "conceptual" else "drill",
                "priority": round(cell["weakness_score"] * 50),
                "concept": cell["concept"],
                "skill": cell["skill"],
                "evidence": {
                    "misses": misses,
                    "n": cell["n"],
                    "accuracy": cell["accuracy"],
                    "last_seen_at": cell["last_seen_at"],
                },
            }
        )

    strong_stale = [
        c
        for c in weak_cells
        if c["accuracy"] >= 0.85
        and (utcnow() - _aware(datetime.fromisoformat(c["last_seen_at"]))).total_seconds()
        > 7 * 86400
    ]
    for cell in strong_stale[:1]:
        recs.append(
            {
                "kind": "challenge",
                "priority": 20,
                "concept": cell["concept"],
                "skill": cell["skill"],
                "evidence": {
                    "accuracy": cell["accuracy"],
                    "n": cell["n"],
                    "last_seen_at": cell["last_seen_at"],
                },
            }
        )

    recs.sort(key=lambda entry: -entry["priority"])
    return recs


def materialize(session: Session, profile_id: int) -> None:
    rows = answer_rows(session, profile_id)
    matrix = weakness_matrix(rows)
    session.query(ConceptSkillStat).filter(
        ConceptSkillStat.profile_id == profile_id
    ).delete()
    for cell in matrix:
        session.add(
            ConceptSkillStat(
                profile_id=profile_id,
                concept=cell["concept"],
                concept_id=cell.get("concept_id"),
                skill=cell["skill"],
                n=cell["n"],
                accuracy=cell["accuracy"],
                avg_time_ratio=cell["avg_time_ratio"],
                last_seen_at=datetime.fromisoformat(cell["last_seen_at"]),
                weakness_score=cell["weakness_score"],
            )
        )
    history = daily_history(session, profile_id)
    session.query(DailyRollup).filter(DailyRollup.profile_id == profile_id).delete()
    for entry in history:
        session.add(
            DailyRollup(
                profile_id=profile_id,
                day=entry["day"],
                answers_n=entry["answers_n"],
                correct_n=entry["correct_n"],
                cards_reviewed=entry["cards_reviewed"],
                minutes=entry["minutes"],
                xp=entry["xp"],
            )
        )
    items = item_analysis(session, profile_id)
    for item in items:
        existing = session.query(ItemStat).filter(
            ItemStat.question_id == item["question_id"]
        )
        stat = existing.first()
        if stat is None:
            stat = ItemStat(question_id=item["question_id"])
            session.add(stat)
        stat.n_attempts = item["n_attempts"]
        stat.p_correct = item["p_correct"]
        stat.avg_time_ms = item["avg_time_ms"]
        stat.avg_time_ratio = item["avg_time_ratio"]
        stat.distractor_selection = item["distractor_selection"]
        stat.flag = item["flag"]
        stat.updated_at = utcnow()
        question = session.get(Question, item["question_id"])
        if question is not None and item["flag"] == "review":
            question.flag = "review"
    session.flush()
