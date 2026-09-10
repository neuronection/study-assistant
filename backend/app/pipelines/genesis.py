from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.gateway import LLMGateway
from ..domain.models import Activity, Course, Extraction, TreeNode
from ..jobs.cancellation import JobCancelled, is_cancel_requested
from ..jobs.payloads import GenesisPayload
from ..jobs.runner import JobError, JobHandler, ProgressReporter
from ..services.knowledge.context import ContextResolver, ContextScope, ContextSpec
from ..services.knowledge.courses import genesis_depth1_nodes
from ..storage.blobs import BlobStore
from .compose import ComposeService, find_live_artifact
from .flashcards import FlashcardsService
from .quizgen import QuizgenService

LESSON_KIND = "lesson"
GENESIS_QUIZ_COUNT = 5
GENESIS_CARD_COUNT = 10


def _lesson_markdown(session: Session, material_id: int) -> str | None:
    extraction = session.scalars(
        select(Extraction)
        .where(Extraction.material_id == material_id)
        .order_by(Extraction.version.desc())
        .limit(1)
    ).first()
    return extraction.markdown if extraction is not None else None


def make_genesis_handler(
    gateway: LLMGateway, blobs: BlobStore, embed: Any
) -> JobHandler:
    def handler(session: Session, job: Any, report: ProgressReporter) -> None:
        payload = cast(GenesisPayload, job.payload or {})
        raw_course_id = payload.get("course_id")
        if raw_course_id is None:
            raise JobError("genesis payload missing course_id")
        course = session.get(Course, int(raw_course_id))
        if course is None:
            raise JobError(f"course {raw_course_id} not found")
        lessons = bool(payload.get("lessons", True))
        quizzes = bool(payload.get("quizzes", False))
        flashcards = bool(payload.get("flashcards", False))
        nodes: list[TreeNode] = genesis_depth1_nodes(session, course)
        tasks_per_node = sum((lessons, quizzes, flashcards))
        if not nodes:
            raise JobError("genesis course has no chapter nodes")
        if tasks_per_node == 0:
            return
        total = tasks_per_node * len(nodes)
        done = 0
        failures: list[str] = []
        resolver = ContextResolver(session, embed)

        def checkpoint() -> None:
            if is_cancel_requested(job.id):
                raise JobCancelled()

        def run_lesson(node: TreeNode) -> str:
            bundle = resolver.resolve(
                ContextSpec(
                    course_id=course.id,
                    node_id=node.id,
                    scope=ContextScope.node,
                    query=node.title,
                )
            )
            live = find_live_artifact(session, course.id, node.id, LESSON_KIND)
            existing_md: str | None = None
            if live is not None:
                existing_md = _lesson_markdown(session, live.id)
            material = ComposeService(session, gateway).compose(
                profile_id=course.profile_id,
                course_id=course.id,
                node_id=node.id,
                kind=LESSON_KIND,
                title=f"{node.title} — lesson",
                context_bundle=bundle,
                blobs=blobs,
                existing=live,
                existing_md=existing_md,
            )
            session.commit()
            markdown = _lesson_markdown(session, material.id)
            return markdown or ""

        def run_quiz(node: TreeNode, lesson_md: str | None) -> None:
            bundle = resolver.resolve(
                ContextSpec(
                    course_id=course.id,
                    node_id=node.id,
                    scope=ContextScope.node,
                    query=node.title,
                )
            )
            activity = Activity(
                profile_id=course.profile_id,
                course_id=course.id,
                node_id=node.id,
                type="quiz",
                title=f"{node.title} · quiz",
                config={"count": GENESIS_QUIZ_COUNT, "topic": node.title},
            )
            session.add(activity)
            session.flush()
            try:
                QuizgenService(session, gateway).generate(
                    activity,
                    count=GENESIS_QUIZ_COUNT,
                    topic=node.title,
                    context=bundle,
                )
            except Exception:
                stale = session.get(Activity, activity.id)
                if stale is not None:
                    session.delete(stale)
                    session.commit()
                raise
            session.commit()

        def run_flashcards(node: TreeNode, lesson_md: str | None) -> None:
            parts = [f"Topic: {node.title}"]
            if node.ai_hint:
                parts.append(f"Objectives: {node.ai_hint}")
            if lesson_md:
                parts.append(lesson_md)
            bundle = resolver.resolve(
                ContextSpec(
                    course_id=course.id,
                    node_id=node.id,
                    scope=ContextScope.node,
                    query=node.title,
                )
            )
            FlashcardsService(session, gateway).generate(
                course.profile_id,
                course_id=course.id,
                node_id=node.id,
                count=GENESIS_CARD_COUNT,
                source="material",
                content="\n\n".join(parts),
                context=bundle,
            )
            session.commit()

        for node in nodes:
            lesson_md: str | None = None
            if lessons:
                checkpoint()
                try:
                    lesson_md = run_lesson(node)
                except JobCancelled:
                    raise
                except Exception as error:
                    session.rollback()
                    failures.append(f"lesson {node.title}: {error}")
                done += 1
                report(int(done / total * 100), f"lesson: {node.title}")
            if quizzes:
                checkpoint()
                try:
                    run_quiz(node, lesson_md)
                except JobCancelled:
                    raise
                except Exception as error:
                    session.rollback()
                    failures.append(f"quiz {node.title}: {error}")
                done += 1
                report(int(done / total * 100), f"quiz: {node.title}")
            if flashcards:
                checkpoint()
                try:
                    run_flashcards(node, lesson_md)
                except JobCancelled:
                    raise
                except Exception as error:
                    session.rollback()
                    failures.append(f"flashcards {node.title}: {error}")
                done += 1
                report(int(done / total * 100), f"flashcards: {node.title}")
        if failures:
            if len(failures) >= total:
                raise JobError("all genesis tasks failed: " + "; ".join(failures[:4]))
            report(
                100,
                f"done with {len(failures)} failed task(s): " + "; ".join(failures[:4]),
            )

    return handler
