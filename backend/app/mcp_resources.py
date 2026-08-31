import logging
import sys
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .domain.models import (
    Activity,
    Course,
    Exercise,
    ExerciseStep,
    Note,
    Profile,
    Question,
    TreeNode,
)
from .services.knowledge.tree import TreeService

MCP_SERVER_NAME = "studyassistant"
MCP_INSTRUCTIONS = (
    "Read-only access to this learner's Study Assistant study resources. "
    "Nodes form a per-course tree (root = the course itself, up to 4 levels); "
    "every tool accepts a node_id and can roll up descendants via "
    "include_children. No write tools exist by design."
)

LIST_COURSES_DESC = "List the learner's courses with their root node ids."
GET_NODE_OVERVIEW_DESC = (
    "One node of the course tree: breadcrumb, summary, objectives, "
    "children, and per-resource counts (direct vs with children)."
)
GET_NODE_MATERIALS_DESC = (
    "Materials assigned to a node (optionally incl. its descendants), "
    "with read status and allocation rationale."
)
GET_NODE_CONCEPTS_DESC = (
    "Knowledge-graph concepts covering a node's subtree "
    "(name, description, which nodes cover them)."
)
GET_NODE_EXERCISES_DESC = (
    "Multi-step exercises placed at a node (optionally incl. "
    "descendants) with difficulty and step counts."
)
GET_NODE_QUIZZES_DESC = (
    "Quizzes placed at a node (optionally incl. descendants) with "
    "question counts."
)
GET_NODE_NOTES_DESC = (
    "Study notes placed at a node (optionally incl. descendants) with "
    "tags and update times."
)
GET_NODE_CONTEXT_DESC = (
    "Resolve the same study context the in-app AI sees for a node: materials with "
    "index-card summaries, attached notes, covered concepts, ancestor AI hints, "
    "and numbered source excerpts (hybrid retrieval when query is given). Use "
    "get_node_overview for a cheap summary first."
)


class ResourceError(ValueError):
    pass


def _resolve_profile(session: Session, profile_id: int | None) -> Profile:
    statement = select(Profile).order_by(Profile.id)
    if profile_id is not None:
        statement = statement.where(Profile.id == profile_id)
    profile = session.scalars(statement.limit(1)).first()
    if profile is None:
        raise ResourceError("profile not found")
    return profile


def _scoped_node(session: Session, node_id: int, profile_id: int | None) -> TreeNode:
    try:
        node = TreeService(session).get(node_id)
    except ValueError as error:
        raise ResourceError(str(error)) from error
    if profile_id is not None:
        course = session.get(Course, node.course_id)
        if course is None or course.profile_id != profile_id:
            raise ResourceError("node not found")
    return node


def _list_courses(session: Session, profile_id: int | None = None) -> dict[str, Any]:
    profile = _resolve_profile(session, profile_id)
    courses = list(
        session.scalars(
            select(Course)
            .where(Course.profile_id == profile.id, Course.archived_at.is_(None))
            .order_by(Course.title)
        )
    )
    roots = {
        root.course_id: root.id
        for root in session.scalars(select(TreeNode).where(TreeNode.is_root.is_(True)))
    }
    return {
        "courses": [
            {
                "id": course.id,
                "title": course.title,
                "subject": course.subject,
                "level": course.level,
                "root_node_id": roots.get(course.id),
            }
            for course in courses
        ]
    }


def _get_node_overview(
    session: Session, node_id: int, profile_id: int | None = None
) -> dict[str, Any]:
    profile = _resolve_profile(session, profile_id)
    _scoped_node(session, node_id, profile.id)
    workspace = TreeService(session).workspace(node_id, profile.id)
    return {
        "node": workspace["node"],
        "children": workspace["children"],
        "counts": workspace["counts"],
    }


def _get_node_materials(
    session: Session,
    node_id: int,
    include_children: bool = True,
    profile_id: int | None = None,
) -> dict[str, Any]:
    profile = _resolve_profile(session, profile_id)
    _scoped_node(session, node_id, profile.id)
    workspace = TreeService(session).workspace(node_id, profile.id)
    if include_children:
        direct = workspace["materials"]
        by_child = workspace["child_materials"]
        return {"direct": direct, "children": by_child}
    return {"direct": workspace["materials"], "children": {}}


def _get_node_concepts(
    session: Session, node_id: int, profile_id: int | None = None
) -> dict[str, Any]:
    profile = _resolve_profile(session, profile_id)
    _scoped_node(session, node_id, profile.id)
    workspace = TreeService(session).workspace(node_id, profile.id)
    return {"concepts": workspace["concepts"]}


def _get_node_exercises(
    session: Session,
    node_id: int,
    include_children: bool = True,
    profile_id: int | None = None,
) -> dict[str, Any]:
    profile = _resolve_profile(session, profile_id)
    node = _scoped_node(session, node_id, profile.id)
    scope_ids = TreeService(session).subtree_ids(node, include_children)
    exercises = list(
        session.scalars(
            select(Exercise)
            .where(
                Exercise.profile_id == profile.id,
                Exercise.node_id.in_(scope_ids),
            )
            .order_by(Exercise.id.desc())
            .limit(100)
        )
    )
    counted: dict[int, int] = {exercise.id: 0 for exercise in exercises}
    if exercises:
        for (exercise_id,) in session.execute(
            select(ExerciseStep.exercise_id).where(
                ExerciseStep.exercise_id.in_(counted)
            )
        ):
            counted[int(exercise_id)] += 1
    return {
        "exercises": [
            {
                "id": exercise.id,
                "title": exercise.title,
                "difficulty": exercise.difficulty,
                "step_count": counted[exercise.id],
                "node_id": exercise.node_id,
            }
            for exercise in exercises
        ]
    }


def _get_node_quizzes(
    session: Session,
    node_id: int,
    include_children: bool = True,
    profile_id: int | None = None,
) -> dict[str, Any]:
    profile = _resolve_profile(session, profile_id)
    node = _scoped_node(session, node_id, profile.id)
    scope_ids = TreeService(session).subtree_ids(node, include_children)
    activities = list(
        session.scalars(
            select(Activity)
            .where(
                Activity.profile_id == profile.id,
                Activity.type == "quiz",
                Activity.node_id.in_(scope_ids),
            )
            .order_by(Activity.id.desc())
            .limit(100)
        )
    )
    counted: dict[int, int] = {activity.id: 0 for activity in activities}
    if activities:
        for (activity_id,) in session.execute(
            select(Question.activity_id).where(
                Question.activity_id.in_(counted)
            )
        ):
            counted[int(activity_id)] += 1
    return {
        "quizzes": [
            {
                "id": activity.id,
                "title": activity.title,
                "node_id": activity.node_id,
                "question_count": counted[activity.id],
            }
            for activity in activities
        ]
    }


def _get_node_notes(
    session: Session,
    node_id: int,
    include_children: bool = True,
    profile_id: int | None = None,
) -> dict[str, Any]:
    profile = _resolve_profile(session, profile_id)
    node = _scoped_node(session, node_id, profile.id)
    scope_ids = TreeService(session).subtree_ids(node, include_children)
    notes = list(
        session.scalars(
            select(Note)
            .where(
                Note.profile_id == profile.id,
                Note.node_id.in_(scope_ids),
            )
            .order_by(Note.pinned.desc(), Note.updated_at.desc())
            .limit(100)
        )
    )
    return {
        "notes": [
            {
                "id": note.id,
                "title": note.title,
                "tags": note.tags or [],
                "pinned": note.pinned,
                "node_id": note.node_id,
                "updated_at": (
                    note.updated_at.isoformat() if note.updated_at else None
                ),
            }
            for note in notes
        ]
    }


def _get_node_context(
    session: Session,
    node_id: int,
    scope: str = "subtree",
    query: str | None = None,
    max_chunks: int = 12,
    profile_id: int | None = None,
) -> dict[str, Any]:
    from .services.knowledge.context import (
        ContextError,
        ContextResolver,
        ContextScope,
        ContextSpec,
    )

    node = _scoped_node(session, node_id, profile_id)
    if query is not None and len(query) > 500:
        raise ResourceError("query must be at most 500 chars")

    def no_embed(text: str) -> tuple[str, list[list[float]]] | None:
        return None

    resolver = ContextResolver(session, no_embed)
    try:
        bundle = resolver.resolve(
            ContextSpec(
                course_id=node.course_id,
                node_id=node.id,
                scope=ContextScope(scope),
                query=query,
                max_chunks=max_chunks,
            )
        )
    except (ContextError, ValueError) as error:
        raise ResourceError(str(error)) from error
    return {
        "node_id": node.id,
        "course_id": node.course_id,
        "scope": scope,
        "stats": bundle.stats(),
        "rendered": bundle.render_prompt(),
    }


# Chat-callable resource tools (curated subset). `keyword` is the chat tool line,
# `arg` names the argument kind the chat resolves (currently only "node").
RESOURCE_TOOLS: list[dict[str, Any]] = [
    {
        "keyword": "COURSES",
        "name": "list_courses",
        "description": LIST_COURSES_DESC,
        "arg": None,
        "call": _list_courses,
    },
    {
        "keyword": "NODE_OVERVIEW",
        "name": "get_node_overview",
        "description": GET_NODE_OVERVIEW_DESC,
        "arg": "node",
        "call": _get_node_overview,
    },
    {
        "keyword": "NODE_QUIZZES",
        "name": "get_node_quizzes",
        "description": GET_NODE_QUIZZES_DESC,
        "arg": "node",
        "call": _get_node_quizzes,
    },
    {
        "keyword": "NODE_EXERCISES",
        "name": "get_node_exercises",
        "description": GET_NODE_EXERCISES_DESC,
        "arg": "node",
        "call": _get_node_exercises,
    },
    {
        "keyword": "NODE_NOTES",
        "name": "get_node_notes",
        "description": GET_NODE_NOTES_DESC,
        "arg": "node",
        "call": _get_node_notes,
    },
]

RESOURCE_TOOL_BY_KEYWORD = {tool["keyword"]: tool for tool in RESOURCE_TOOLS}


def resource_native_schemas() -> list[dict[str, Any]]:
    schemas: list[dict[str, Any]] = []
    for tool in RESOURCE_TOOLS:
        if tool["arg"] == "node":
            parameters: dict[str, Any] = {
                "type": "object",
                "properties": {
                    "node": {
                        "type": "string",
                        "description": "A node handle (T#) from the "
                        "referenceable-items manifest, or 'here' for the "
                        "current node",
                    }
                },
                "required": ["node"],
                "additionalProperties": False,
            }
        else:
            parameters = {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            }
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": tool["keyword"],
                    "description": tool["description"],
                    "parameters": parameters,
                },
            }
        )
    return schemas


def build_resource_tool_doc() -> str:
    sections = [
        "You may also browse the learner's data with these read-only tools. "
        "Emit EXACTLY one tool line, nothing else:"
    ]
    for tool in RESOURCE_TOOLS:
        keyword = tool["keyword"]
        body = f"{keyword} <node>" if tool["arg"] == "node" else keyword
        lines = [body, f"  {tool['description'].splitlines()[0]}"]
        if tool["arg"] == "node":
            lines.append(
                "    <node>: a node handle (T#) from the referenceable-items "
                "manifest, or 'here' for the current node"
            )
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def create_resource_server(session_factory: sessionmaker[Session]) -> MCPServer:
    server = MCPServer(name=MCP_SERVER_NAME, instructions=MCP_INSTRUCTIONS)

    def run(fn: Callable[[Session], Any]) -> Any:
        with session_factory() as session:
            try:
                return fn(session)
            except ResourceError as error:
                return {"error": str(error)}

    @server.tool(name="list_courses", description=LIST_COURSES_DESC)
    def list_courses(profile_id: int | None = None) -> Any:
        return run(lambda session: _list_courses(session, profile_id))

    @server.tool(name="get_node_overview", description=GET_NODE_OVERVIEW_DESC)
    def get_node_overview(node_id: int, profile_id: int | None = None) -> Any:
        return run(lambda session: _get_node_overview(session, node_id, profile_id))

    @server.tool(name="get_node_materials", description=GET_NODE_MATERIALS_DESC)
    def get_node_materials(
        node_id: int, include_children: bool = True, profile_id: int | None = None
    ) -> Any:
        return run(
            lambda session: _get_node_materials(
                session, node_id, include_children, profile_id
            )
        )

    @server.tool(name="get_node_concepts", description=GET_NODE_CONCEPTS_DESC)
    def get_node_concepts(node_id: int, profile_id: int | None = None) -> Any:
        return run(lambda session: _get_node_concepts(session, node_id, profile_id))

    @server.tool(name="get_node_exercises", description=GET_NODE_EXERCISES_DESC)
    def get_node_exercises(
        node_id: int, include_children: bool = True, profile_id: int | None = None
    ) -> Any:
        return run(
            lambda session: _get_node_exercises(
                session, node_id, include_children, profile_id
            )
        )

    @server.tool(name="get_node_quizzes", description=GET_NODE_QUIZZES_DESC)
    def get_node_quizzes(
        node_id: int, include_children: bool = True, profile_id: int | None = None
    ) -> Any:
        return run(
            lambda session: _get_node_quizzes(
                session, node_id, include_children, profile_id
            )
        )

    @server.tool(name="get_node_notes", description=GET_NODE_NOTES_DESC)
    def get_node_notes(
        node_id: int, include_children: bool = True, profile_id: int | None = None
    ) -> Any:
        return run(
            lambda session: _get_node_notes(
                session, node_id, include_children, profile_id
            )
        )

    @server.tool(name="get_node_context", description=GET_NODE_CONTEXT_DESC)
    def get_node_context(
        node_id: int,
        scope: str = "subtree",
        query: str | None = None,
        max_chunks: int = 12,
        profile_id: int | None = None,
    ) -> Any:
        return run(
            lambda session: _get_node_context(
                session, node_id, scope, query, max_chunks, profile_id
            )
        )

    return server


def run_mcp_stdio() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    from .core.config import get_settings
    from .storage.db import make_engine, make_session_factory

    settings = get_settings()
    if not settings.db_path.exists():
        raise SystemExit(
            f"no database at {settings.db_path} — start the app once before using MCP"
        )
    engine = make_engine(settings.db_path)
    server = create_resource_server(make_session_factory(engine))
    server.run(transport="stdio")
