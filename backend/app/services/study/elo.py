import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...domain.models import ConceptSkillRating, ItemStat, Question

K_BASE = 32.0
K_MIN = 8.0
SEED_BASE = 800.0
SEED_STEP = 100.0
STUDENT_SEED = 1000.0
ELO_SCALE = 400.0
RATING_CELL = 200.0
RATING_MIN_ATTEMPTS = 10


def seeded_item_rating(difficulty: float | None) -> float:
    level = difficulty if difficulty is not None else 3.0
    level = max(1.0, min(5.0, float(level)))
    return SEED_BASE + SEED_STEP * level


def expected_score(player: float, opponent: float) -> float:
    odds: float = math.pow(10.0, (opponent - player) / ELO_SCALE)
    return 1.0 / (1.0 + odds)

def k_factor(rating_count: int | None) -> float:
    return max(K_MIN, K_BASE - float(rating_count or 0))


def rating_to_difficulty(rating: float) -> int:
    return int(max(1, min(5, round((rating - SEED_BASE) / SEED_STEP))))


def is_elo_outlier(
    rating: float | None, rating_count: int | None, difficulty: float | None
) -> bool:
    if rating is None or (rating_count or 0) < RATING_MIN_ATTEMPTS:
        return False
    return abs(rating - seeded_item_rating(difficulty)) >= RATING_CELL


class EloService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(self, profile_id: int, question: Question, score: float) -> None:
        score = max(0.0, min(1.0, float(score)))
        stat = self._session.scalars(
            select(ItemStat).where(ItemStat.question_id == question.id)
        ).first()
        if stat is None:
            stat = ItemStat(
                question_id=question.id,
                n_attempts=0,
                p_correct=0.0,
                flag="ok",
            )
            self._session.add(stat)
        item_rating = stat.rating if stat.rating is not None else seeded_item_rating(
            question.difficulty
        )
        item_count = stat.rating_count or 0

        cells = self._student_cells(profile_id, question)
        student_rating = next(
            (cell.rating for cell in cells if cell.rating is not None),
            STUDENT_SEED,
        )
        student_count = next(
            (cell.rating_count for cell in cells if cell.rating_count is not None),
            0,
        )

        exp_student = expected_score(student_rating, item_rating)
        stat.rating = item_rating + k_factor(item_count) * (exp_student - score)
        stat.rating_count = item_count + 1
        student_delta = k_factor(student_count) * (score - exp_student)
        for cell in cells:
            base = cell.rating if cell.rating is not None else STUDENT_SEED
            cell.rating = base + student_delta
            cell.rating_count = (cell.rating_count or 0) + 1

    def student_rating(self, profile_id: int, concept: str, skill: str | None) -> float | None:
        if not concept:
            return None
        statement = select(ConceptSkillRating.rating).where(
            ConceptSkillRating.profile_id == profile_id,
            ConceptSkillRating.concept == concept,
        )
        if skill:
            statement = statement.where(ConceptSkillRating.skill == skill)
        return self._session.scalars(
            statement.order_by(ConceptSkillRating.rating_count.desc()).limit(1)
        ).first()

    def _student_cells(
        self, profile_id: int, question: Question
    ) -> list[ConceptSkillRating]:
        concepts = [str(tag) for tag in (question.tags or [])][:3]
        skill = question.skill or "procedural"
        cells: list[ConceptSkillRating] = []
        for concept in concepts:
            cell = self._session.scalars(
                select(ConceptSkillRating).where(
                    ConceptSkillRating.profile_id == profile_id,
                    ConceptSkillRating.concept == concept,
                    ConceptSkillRating.skill == skill,
                )
            ).first()
            if cell is None:
                cell = ConceptSkillRating(
                    profile_id=profile_id,
                    concept=concept,
                    skill=skill,
                )
                self._session.add(cell)
            cells.append(cell)
        return cells
