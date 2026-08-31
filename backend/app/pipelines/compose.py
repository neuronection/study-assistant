import re
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.gateway import LLMGateway, ProviderError
from ..ai.runner import AuditRef, TaskRunner
from ..ai.skills import COMPOSE_SYSTEM
from ..core.vocab import ProvenanceKind
from ..domain.models import Extraction, Material, MaterialLink, Note, TreeNode
from ..services.content.materials import MaterialsService
from ..services.knowledge.context import ContextBundle
from ..storage.blobs import BlobStore

logger = structlog.get_logger(__name__)

COMPOSE_TASK = "material_compose"
COMPOSE_SKILL = "material.compose"
MAX_REPAIR_ROUNDS = 2
MIN_CHARS = 400
MAX_CHARS = 60000
MATH_SAMPLE = 5
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


def _validate_markdown(markdown: str, registry_refs: list[str]) -> list[str]:
    problems: list[str] = []
    text = markdown.strip()
    if len(text) < MIN_CHARS:
        problems.append(f"document too short ({len(text)} chars, need {MIN_CHARS})")
    if len(text) > MAX_CHARS:
        problems.append(f"document too long ({len(text)} chars, limit {MAX_CHARS})")
    from ..ai.mentions import MENTION_RE

    used = {f"{m.group(1)}{m.group(2)}" for m in MENTION_RE.finditer(text)}
    allowed = set(registry_refs)
    invalid = sorted(used - allowed)
    if invalid:
        problems.append(
            f"handles {invalid} were not offered in the context — remove or fix them"
        )
    return problems


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
        try:
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
        except ProviderError as error:
            raise ComposeError(str(error)) from error
        if result.problems:
            raise ComposeError(
                "composed document did not pass validation: "
                + "; ".join(result.problems[:6])
            )
        markdown = result.output_text.strip()
        needs_review = False
        if kind == "formula_sheet":
            markdown, unknown, total = _strip_unknown_formulas(markdown, known_keys)
            if unknown > 0:
                logger.info("formula_sheet_stripped", unknown=unknown, total=total)
                if total > 0 and unknown / total > 0.2:
                    needs_review = True
            markdown = markdown.strip()
        _math_lint_advisory(markdown)

        services = MaterialsService(self._session, blobs)
        target_node_id = node.id if node is not None else node_id
        if existing is not None:
            services.edit_extraction(existing, markdown)
            if needs_review:
                updated = dict(existing.provenance or {})
                updated["needs_review"] = True
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
