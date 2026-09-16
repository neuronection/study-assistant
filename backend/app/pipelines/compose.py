import re
from typing import Any, cast

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.gateway import LLMGateway, ProviderError
from ..ai.runner import AuditRef, TaskRunner
from ..ai.skills import COMPOSE_SYSTEM, PRACTICE_SET_SYSTEM
from ..ai.structured import PracticeSetOut
from ..core.vocab import ProvenanceKind
from ..domain.models import (
    Course,
    Extraction,
    Material,
    MaterialLink,
    Note,
    TreeNode,
)
from ..jobs.cancellation import JobCancelled, is_cancel_requested
from ..jobs.payloads import ComposePayload, IngestPayload
from ..jobs.runner import JobError, JobHandler, JobRunner, ProgressReporter
from ..math.equivalence import parse_math
from ..services.content.materials import MaterialsService
from ..services.knowledge.context import (
    COVERAGE_GATE,
    COVERAGE_MIN_MATERIALS,
    ContextBundle,
    ContextError,
    ContextResolver,
    ContextScope,
    ContextSpec,
)
from ..services.knowledge.tree import TreeService
from ..services.study.answer_validation import (
    PRACTICE_ANSWER_KINDS,
    validate_answer_shape,
    validate_distractor_equivalence,
)
from ..storage.blobs import BlobStore

logger = structlog.get_logger(__name__)

COMPOSE_TASK = "material_compose"
COMPOSE_SKILL = "material.compose"
COMPOSE_PRACTICE_SKILL = "material.compose_practice"
MAX_REPAIR_ROUNDS = 2
MIN_CHARS = 400
MAX_CHARS = 60000
MATH_SAMPLE = 5
MAX_PRACTICE_ITEMS = 30
PRACTICE_LETTERS = "abcdef"
PRACTICE_JSON_CONTRACT = (
    "Output format (STRICT): return only a JSON object "
    '{"items": [...]} where every item is '
    '{"stem_md": str, "answer_kind": "single" | "multi" | "truefalse" | '
    '"numeric" | "equation", "answer": object, "choices": [str] | null, '
    '"solution_steps": [str] | null} — no prose, no code fences.\n'
    '- single/multi: 2-5 entries in "choices"; answer = {"index": i} or '
    '{"indices": [i, ...]} (0-based into choices).\n'
    '- truefalse: answer = {"value": true | false}. numeric: '
    '{"value": "<number>"}. equation: {"value": "<parseable expression>"}.\n'
    "Every answer must be objectively correct; wrong choices plausible but "
    f"provably not the answer. At most {MAX_PRACTICE_ITEMS} items."
)
LATEX_SPAN_RE = re.compile(r"\$\$(.+?)\$\$|\$([^$\n]+?)\$", re.DOTALL)
FORMULA_MAX_PER_NODE = 40
FORMULA_MIN_CHARS = 3

KINDS = {
    "study_guide": "study guide (structure + explanations + worked examples)",
    "summary_sheet": "summary sheet (compact formulas and definitions)",
    "practice_set": "practice set (problems with an answers section at the end)",
    "error_recap": "error recap (mistake patterns and how to avoid them)",
    "mindmap": "mindmap (a markdown outline of the topic's structure)",
    "formula_sheet": "formula sheet (the collected formulas, grouped and titled)",
    "cheat_sheet": "cheat sheet (one-page revision sheet: formulas, definitions, procedures)",
    "node_review": "node review report (coverage gaps, ordering, orphans)",
    "lesson": (
        "lesson (expository lesson on the node's topic: definitions, explanation, "
        "a worked example, common pitfalls; teach from model knowledge when the "
        "node has no material yet; no fabricated citations)"
    ),
}

RETRIEVAL_EXCLUDED_KINDS = {"node_review"}


def find_live_artifact(
    session: Session, course_id: int, node_id: int, kind: str
) -> Material | None:
    rows = session.execute(
        select(Material)
        .join(MaterialLink, MaterialLink.material_id == Material.id)
        .where(
            MaterialLink.course_id == course_id,
            MaterialLink.node_id == node_id,
            Material.provenance.is_not(None),
        )
        .order_by(Material.id.desc())
    ).scalars()
    for material in rows:
        provenance = material.provenance
        if isinstance(provenance, dict) and provenance.get("kind") == kind:
            return material
    return None

TRIVIAL_ARITHMETIC_RE = re.compile(r"^[\d\s+\-*/=.,()]+$")


def _normalize_formula(latex: str) -> str:
    return re.sub(r"\s+", "", latex.strip())


def collect_formulas(session: Session, course_id: int) -> list[dict[str, Any]]:
    nodes = list(
        session.scalars(
            select(TreeNode)
            .where(TreeNode.course_id == course_id)
            .order_by(TreeNode.sort_path)
        )
    )
    title_by_node = {node.id: node.title for node in nodes}

    def collect_from_texts(
        node_id: int | None, texts: list[str]
    ) -> list[tuple[str, int | None]]:
        found: list[tuple[str, int | None]] = []
        for text in texts:
            for match in LATEX_SPAN_RE.finditer(text):
                latex = (match.group(1) or match.group(2) or "").strip()
                if len(latex) < FORMULA_MIN_CHARS:
                    continue
                if TRIVIAL_ARITHMETIC_RE.match(latex):
                    continue
                found.append((latex, node_id))
        return found

    pairs: list[tuple[str, int | None]] = []
    notes = list(session.scalars(select(Note).where(Note.course_id == course_id)))
    for note in notes:
        texts = [str(block.get("md") or "") for block in note.body or []]
        texts += [
            drawing.ocr_markdown
            for drawing in note.drawings
            if drawing.ocr_markdown
        ]
        pairs.extend(collect_from_texts(note.node_id, texts))
    link_node: dict[int, int] = {}
    for material_id, node_id in session.execute(
        select(MaterialLink.material_id, MaterialLink.node_id).where(
            MaterialLink.course_id == course_id
        )
    ):
        link_node[int(material_id)] = int(node_id)
    rows = list(
        session.execute(
            select(Extraction.material_id, Extraction.markdown)
            .join(Material, Extraction.material_id == Material.id)
            .where(Material.course_id == course_id)
            .order_by(Extraction.material_id, Extraction.version.desc())
        )
    )
    seen_materials: set[int] = set()
    for material_id, markdown in rows:
        if material_id in seen_materials:
            continue
        seen_materials.add(material_id)
        pairs.extend(collect_from_texts(link_node.get(material_id), [markdown]))
    by_node: dict[int | None, dict[str, str]] = {}
    for latex, node_id in pairs:
        key = _normalize_formula(latex)
        bucket = by_node.setdefault(node_id, {})
        if key not in bucket:
            bucket[key] = latex
    result: list[dict[str, object]] = []
    for node_id, formulas in by_node.items():
        entries = list(formulas.items())[:FORMULA_MAX_PER_NODE]
        result.append(
            {
                "node_id": node_id,
                "node_title": title_by_node.get(node_id) if node_id is not None else None,
                "formulas": [{"latex": latex, "key": key} for key, latex in entries],
            }
        )
    return result


def _strip_unknown_formulas(markdown: str, known_keys: set[str]) -> tuple[str, int, int]:
    spans: list[tuple[re.Match[str], str]] = []
    for match in LATEX_SPAN_RE.finditer(markdown):
        latex = (match.group(1) or match.group(2) or "").strip()
        if latex:
            spans.append((match, latex))
    if not spans:
        return markdown, 0, 0
    unknown_ranges: list[tuple[int, int]] = []
    unknown = 0
    for match, latex in spans:
        if _normalize_formula(latex) not in known_keys:
            unknown += 1
            unknown_ranges.append((match.start(), match.end()))
    if not unknown_ranges:
        return markdown, 0, len(spans)
    pieces: list[str] = []
    cursor = 0
    for start, end in unknown_ranges:
        pieces.append(markdown[cursor:start])
        cursor = end
    pieces.append(markdown[cursor:])
    return "".join(pieces), unknown, len(spans)


class ComposeError(ValueError):
    pass


def _math_lint_advisory(markdown: str) -> None:
    spans: list[str] = []
    for match in LATEX_SPAN_RE.finditer(markdown):
        span = (match.group(1) or match.group(2) or "").strip()
        if span:
            spans.append(span)
    failures: list[str] = []
    from ..math.equivalence import parse_math

    for span in spans[:MATH_SAMPLE]:
        try:
            parse_math(span)
        except Exception:
            failures.append(span[:60])
    if failures:
        logger.info("compose_math_lint", failures=failures)


def _check_mentions(markdown: str, registry_refs: list[str]) -> list[str]:
    from ..ai.mentions import MENTION_RE

    used = {f"{m.group(1)}{m.group(2)}" for m in MENTION_RE.finditer(markdown)}
    invalid = sorted(used - set(registry_refs))
    if invalid:
        return [
            f"handles {invalid} were not offered in the context — remove or fix them"
        ]
    return []


def _validate_markdown(markdown: str, registry_refs: list[str]) -> list[str]:
    problems: list[str] = []
    text = markdown.strip()
    if len(text) < MIN_CHARS:
        problems.append(f"document too short ({len(text)} chars, need {MIN_CHARS})")
    if len(text) > MAX_CHARS:
        problems.append(f"document too long ({len(text)} chars, limit {MAX_CHARS})")
    problems.extend(_check_mentions(text, registry_refs))
    return problems


def _validate_practice_draft(
    draft: dict[str, Any], registry_refs: list[str]
) -> list[str]:
    items = draft.get("items")
    if not isinstance(items, list) or not items:
        return ["response missing items list"]
    problems: list[str] = []
    if len(items) > MAX_PRACTICE_ITEMS:
        problems.append(f"too many items ({len(items)}, max {MAX_PRACTICE_ITEMS})")
    for index, entry in enumerate(items[:MAX_PRACTICE_ITEMS]):
        label = f"item {index + 1}"
        if not isinstance(entry, dict):
            problems.append(f"{label}: not an object")
            continue
        kind = str(entry.get("answer_kind"))
        if kind not in PRACTICE_ANSWER_KINDS:
            problems.append(
                f"{label}: answer_kind '{entry.get('answer_kind')}' must be one of "
                f"{sorted(PRACTICE_ANSWER_KINDS)}"
            )
            continue
        if not str(entry.get("stem_md", "")).strip():
            problems.append(f"{label}: empty stem")
        answer = entry.get("answer")
        if not isinstance(answer, dict):
            problems.append(f"{label}: missing answer object")
            answer = {}
        choices = entry.get("choices")
        problems.extend(validate_answer_shape(kind, answer, choices, label))
        problems.extend(validate_distractor_equivalence(kind, answer, choices, label))
        if kind == "equation":
            value = str(answer.get("value", "")).strip()
            try:
                parse_math(value)
            except Exception:
                problems.append(
                    f"{label}: equation answer '{value[:40]}' is not parseable"
                )
    rendered = _render_practice_set("Practice set", items[:MAX_PRACTICE_ITEMS])
    problems.extend(_check_mentions(rendered, registry_refs))
    return problems


def _render_practice_set(doc_title: str, items: list[dict[str, Any]]) -> str:
    lines = [f"# {doc_title}", "", "## Problems", ""]
    for index, entry in enumerate(items, start=1):
        stem = str(entry.get("stem_md") or "").strip()
        kind = str(entry.get("answer_kind") or "")
        choices = entry.get("choices")
        if kind in ("single", "multi") and isinstance(choices, list) and choices:
            lines.append(f"{index}. {stem}")
            for letter, choice in zip(PRACTICE_LETTERS, choices, strict=False):
                lines.append(f"   {letter}) {choice}")
        elif kind == "truefalse":
            lines.append(f"{index}. {stem} — true or false?")
        else:
            lines.append(f"{index}. {stem}")
    lines.extend(["", "## Answers", ""])
    for index, entry in enumerate(items, start=1):
        kind = str(entry.get("answer_kind") or "")
        raw_answer = entry.get("answer")
        answer: dict[str, Any] = raw_answer if isinstance(raw_answer, dict) else {}
        raw_choices = entry.get("choices")
        answer_choices: list[Any] = (
            list(raw_choices) if isinstance(raw_choices, list) else []
        )
        rendered = "—"
        if kind == "single":
            try:
                chosen = int(answer.get("index", -1))
            except (TypeError, ValueError):
                chosen = -1
            rendered = (
                f"{PRACTICE_LETTERS[chosen]}) {answer_choices[chosen]}"
                if 0 <= chosen < len(answer_choices)
                else "—"
            )
        elif kind == "multi":
            indices = answer.get("indices")
            picked = []
            if isinstance(indices, list):
                for raw in indices:
                    try:
                        chosen = int(raw)
                    except (TypeError, ValueError):
                        continue
                    if 0 <= chosen < len(answer_choices):
                        picked.append(
                            f"{PRACTICE_LETTERS[chosen]}) {answer_choices[chosen]}"
                        )
            rendered = ", ".join(picked) if picked else "—"
        elif kind == "truefalse":
            rendered = "True" if answer.get("value") is True else "False"
        elif kind == "numeric":
            rendered = str(answer.get("value"))
        elif kind == "equation":
            rendered = f"${answer.get('value')}$"
        lines.append(f"{index}. {rendered}")
        steps = entry.get("solution_steps")
        for step in steps if isinstance(steps, list) else []:
            lines.append(f"   - {step}")
    return "\n".join(lines)


def _practice_item_report(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "stem_md": entry.get("stem_md"),
        "answer_kind": entry.get("answer_kind"),
        "answer": entry.get("answer"),
        "choices": entry.get("choices"),
        "solution_steps": entry.get("solution_steps"),
        "checks": {"shape": True, "parse": True, "distractors": True},
    }


class ComposeService:
    def __init__(self, session: Session, gateway: LLMGateway) -> None:
        self._session = session
        self._gateway = gateway

    def _build_prompt(
        self,
        *,
        kind: str,
        title: str,
        instructions: str | None,
        extra_md: str | None,
        context: ContextBundle | None,
    ) -> str:
        kind_text = KINDS.get(kind, KINDS["study_guide"])
        lines = [
            f"Compose a {kind_text}.",
            f"Title: {title}",
        ]
        if instructions and instructions.strip():
            lines.append(f"Instructions: {instructions.strip()}")
        if extra_md and extra_md.strip():
            lines.append(f"Additional material to incorporate:\n{extra_md.strip()}")
        prompt = "\n\n".join(lines)
        if context is not None:
            context_text = context.render_prompt()
            if context_text:
                prompt = f"{prompt}\n\n{context_text}"
        return prompt

    def compose(
        self,
        *,
        profile_id: int,
        course_id: int,
        node_id: int | None,
        kind: str,
        title: str | None,
        instructions: str | None = None,
        extra_md: str | None = None,
        context_bundle: ContextBundle | None = None,
        blobs: BlobStore | None = None,
        existing: Material | None = None,
        existing_md: str | None = None,
    ) -> Material:
        if kind not in KINDS:
            raise ComposeError(f"unknown kind '{kind}' — one of {sorted(KINDS)}")
        if blobs is None:
            raise ComposeError("blob store is required")
        node: TreeNode | None = None
        if context_bundle is not None:
            node = context_bundle.node
        doc_title = (title or "").strip() or KINDS[kind].split(" (")[0].capitalize()
        known_keys: set[str] = set()
        if kind == "formula_sheet":
            groups = collect_formulas(self._session, course_id)
            for group in groups:
                for formula in group["formulas"]:
                    known_keys.add(str(formula["key"]))
            if not known_keys:
                raise ComposeError(
                    "no formulas found in this course's notes or material yet"
                )
            lines = [
                "Compose a formula sheet from EXACTLY the formulas collected below.",
                "Title: " + doc_title,
                "Rules:",
                "- Organize the formulas into titled sections (source node titles are guidance).",
                "- You may group, reorder and add one short plain-language hint per formula.",
                "- Copy every formula in LaTeX exactly as given (in $...$ or $$...$$).",
                "- Do NOT invent new formulas and do NOT alter the LaTeX of collected ones.",
            ]
            if instructions and instructions.strip():
                lines.append(f"Instructions: {instructions.strip()}")
            for group in groups:
                heading = str(group.get("node_title") or "Course")
                entries = "\n".join(
                    f"- ${formula['latex']}$" for formula in group["formulas"]
                )
                lines.append(f"## {heading}\n{entries}")
            prompt = "\n\n".join(lines)
        else:
            prompt = self._build_prompt(
                kind=kind,
                title=doc_title,
                instructions=instructions,
                extra_md=extra_md,
                context=context_bundle,
            )
            if existing_md:
                prompt += (
                    "\n\nThe student already has a version of this document "
                    "(it may include their own manual edits). Revise and improve "
                    "it — keep what works and keep their valid additions:\n\n"
                    f"{existing_md[:12000]}"
                )
        registry_refs: list[str] = []
        if context_bundle is not None:
            registry_refs = context_bundle.mentions().refs()

        def validate(markdown: str) -> list[str]:
            return _validate_markdown(markdown, registry_refs)

        runner = TaskRunner(self._session, self._gateway)
        practice_items: list[dict[str, Any]] | None = None
        try:
            if kind == "practice_set":
                result = runner.run_json(
                    task=COMPOSE_TASK,
                    prompt=prompt + "\n\n" + PRACTICE_JSON_CONTRACT,
                    validate=lambda draft: _validate_practice_draft(
                        draft, registry_refs
                    ),
                    fallback_system=PRACTICE_SET_SYSTEM,
                    skill_key=COMPOSE_PRACTICE_SKILL,
                    course_id=course_id,
                    max_rounds=MAX_REPAIR_ROUNDS,
                    error_type=ComposeError,
                    audit=AuditRef("compose", course_id, f"compose {kind}"),
                    schema=PracticeSetOut,
                )
                if result.problems:
                    raise ComposeError(
                        "composed practice set did not pass validation: "
                        + "; ".join(result.problems[:6])
                    )
                raw_items = result.draft.get("items") or []
                raw_items = raw_items[:MAX_PRACTICE_ITEMS]
                markdown = _render_practice_set(doc_title, raw_items).strip()
                practice_items = [_practice_item_report(entry) for entry in raw_items]
            else:
                result = runner.run_text(
                    task=COMPOSE_TASK,
                    prompt=prompt,
                    validate=validate,
                    fallback_system=COMPOSE_SYSTEM,
                    skill_key=COMPOSE_SKILL,
                    course_id=course_id,
                    max_rounds=MAX_REPAIR_ROUNDS,
                    audit=AuditRef("compose", course_id, f"compose {kind}"),
                )
                if result.problems:
                    raise ComposeError(
                        "composed document did not pass validation: "
                        + "; ".join(result.problems[:6])
                    )
                markdown = result.output_text.strip()
        except ProviderError as error:
            raise ComposeError(str(error)) from error
        needs_review = False
        if kind == "formula_sheet":
            markdown, unknown, total = _strip_unknown_formulas(markdown, known_keys)
            if unknown > 0:
                logger.info("formula_sheet_stripped", unknown=unknown, total=total)
                if total > 0 and unknown / total > 0.2:
                    needs_review = True
            markdown = markdown.strip()
        _math_lint_advisory(markdown)
        coverage: dict[str, Any] | None = None
        if context_bundle is not None:
            report = context_bundle.coverage
            if report["total"] > 0:
                coverage = report
                if (
                    report["total"] >= COVERAGE_MIN_MATERIALS
                    and report["covered"] / report["total"] < COVERAGE_GATE
                ):
                    logger.info(
                        "compose_low_coverage",
                        total=report["total"],
                        covered=report["covered"],
                    )
                    needs_review = True

        services = MaterialsService(self._session, blobs)
        target_node_id = node.id if node is not None else node_id
        if existing is not None:
            services.edit_extraction(existing, markdown)
            updated = dict(existing.provenance or {})
            if coverage is not None:
                updated["coverage"] = coverage
            if practice_items is not None:
                updated["practice_items"] = practice_items
            if needs_review:
                updated["needs_review"] = True
            else:
                updated.pop("needs_review", None)
            existing.provenance = updated
            self._session.flush()
            return existing
        material, _duplicate = services.create_text(
            profile_id=profile_id,
            course_id=course_id,
            filename=f"{doc_title}.md",
            content=f"# {doc_title}\n\n{markdown}",
        )
        provenance: dict[str, object] = {
            "source": ProvenanceKind.AI_COMPOSED,
            "kind": kind,
            "model": result.model_label,
        }
        if coverage is not None:
            provenance["coverage"] = coverage
        if practice_items is not None:
            provenance["practice_items"] = practice_items
        if needs_review:
            provenance["needs_review"] = True
        material.provenance = provenance
        if target_node_id is not None:
            link = self._session.scalars(
                select(MaterialLink).where(
                    MaterialLink.course_id == course_id,
                    MaterialLink.node_id == target_node_id,
                    MaterialLink.material_id == material.id,
                )
            ).first()
            if link is None:
                self._session.add(
                    MaterialLink(
                        course_id=course_id,
                        node_id=target_node_id,
                        material_id=material.id,
                        rationale=f"AI-composed ({KINDS[kind].split(' (')[0]})",
                    )
                )
        self._session.flush()
        return material

    def compose_organizer_artifact(
        self,
        *,
        profile_id: int,
        course_id: int,
        node_id: int,
        kind: str,
        title: str,
        markdown: str,
        model_label: str | None,
        blobs: BlobStore,
    ) -> Material:
        if kind not in KINDS:
            raise ComposeError(f"unknown kind '{kind}' — one of {sorted(KINDS)}")
        markdown = markdown.strip()
        if not markdown:
            raise ComposeError("artifact markdown is empty")
        services = MaterialsService(self._session, blobs)
        material, _duplicate = services.create_text(
            profile_id=profile_id,
            course_id=course_id,
            filename=f"{title}.md",
            content=f"# {title}\n\n{markdown}",
        )
        material.provenance = {
            "source": ProvenanceKind.AI_COMPOSED,
            "kind": kind,
            "model": model_label,
        }
        existing = self._session.scalars(
            select(MaterialLink).where(
                MaterialLink.course_id == course_id,
                MaterialLink.node_id == node_id,
                MaterialLink.material_id == material.id,
            )
        ).first()
        if existing is None:
            self._session.add(
                MaterialLink(
                    course_id=course_id,
                    node_id=node_id,
                    material_id=material.id,
                    rationale=f"AI-composed ({KINDS[kind].split(' (')[0]})",
                )
            )
        self._session.flush()
        return material


def make_compose_handler(
    gateway: LLMGateway, blobs: BlobStore, embed: Any
) -> JobHandler:
    def handler(session: Session, job: Any, report: ProgressReporter) -> None:
        payload = cast(ComposePayload, job.payload or {})
        raw_course_id = payload.get("course_id")
        if raw_course_id is None:
            raise JobError("compose payload missing course_id")
        course = session.get(Course, int(raw_course_id))
        if course is None:
            raise JobError(f"course {raw_course_id} not found")
        if is_cancel_requested(job.id):
            raise JobCancelled()
        course_id = int(raw_course_id)
        node_id = payload.get("node_id")
        kind = str(payload.get("kind") or "study_guide")
        report(10, "context")
        resolver = ContextResolver(session, embed)
        try:
            bundle = resolver.resolve(
                ContextSpec(
                    course_id=course_id,
                    node_id=int(node_id) if node_id is not None else None,
                    scope=ContextScope(str(payload.get("scope") or "subtree")),
                    include_material_ids=[
                        int(value)
                        for value in (payload.get("include_material_ids") or [])
                    ],
                    exclude_material_ids=[
                        int(value)
                        for value in (payload.get("exclude_material_ids") or [])
                    ],
                    note_ids=[
                        int(value) for value in (payload.get("note_ids") or [])
                    ],
                    concept_ids=[
                        int(value) for value in (payload.get("concept_ids") or [])
                    ],
                    hint=payload.get("context_hint"),
                    query=str(
                        payload.get("title")
                        or payload.get("instructions")
                        or "study material"
                    ),
                    exclude_ai_composed=True,
                    include_unassigned=bool(
                        payload.get("include_unassigned", False)
                    ),
                )
            )
        except ContextError as error:
            raise JobError(str(error)) from error
        placement_node_id = bundle.node.id if bundle.node is not None else node_id
        if placement_node_id is None:
            placement_node_id = TreeService(session).ensure_root(course_id).id
        regenerate = bool(payload.get("regenerate", False))
        live = find_live_artifact(session, course_id, int(placement_node_id), kind)
        if live is not None and not regenerate:
            raise JobError(
                f"a {kind.replace('_', ' ')} already exists at this node "
                f"(material {live.id})"
            )
        existing_md: str | None = None
        if live is not None:
            extraction = session.scalars(
                select(Extraction)
                .where(Extraction.material_id == live.id)
                .order_by(Extraction.version.desc())
                .limit(1)
            ).first()
            existing_md = extraction.markdown if extraction is not None else None
        if is_cancel_requested(job.id):
            raise JobCancelled()
        report(30, "compose")
        material = ComposeService(session, gateway).compose(
            profile_id=int(payload.get("profile_id") or course.profile_id),
            course_id=course_id,
            node_id=node_id,
            kind=kind,
            title=payload.get("title"),
            instructions=payload.get("instructions"),
            extra_md=payload.get("extra_md"),
            context_bundle=bundle,
            blobs=blobs,
            existing=live,
            existing_md=existing_md,
        )
        if is_cancel_requested(job.id):
            raise JobCancelled()
        report(90, "persist")
        session.commit()
        if live is None:
            JobRunner.enqueue(
                session,
                "ingest",
                IngestPayload(material_id=material.id, blob_sha=material.blob_sha),
            )
            session.commit()
        updated = dict(job.payload or {})
        updated["material_id"] = material.id
        job.payload = updated
        session.commit()
        report(100, "done")

    return handler
