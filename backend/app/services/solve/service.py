from sqlalchemy.orm import Session

from ...core.vocab import SolveInputKind
from ...domain.models import Note, SolveEntry
from ..content.drawings import md_to_blocks, note_search_text
from ..content.notes import normalize_tags
from ..knowledge.courses import ensure_scratch_course
from ..knowledge.tree import TreeService
from .parse import classify
from .steps import solve
from .variants import build_variants


class SolveError(ValueError):
    pass


def solve_input(
    session: Session,
    *,
    profile_id: str,
    input_text: str,
    input_kind: str = SolveInputKind.TYPED.value,
) -> SolveEntry:
    if input_kind not in {member.value for member in SolveInputKind}:
        raise SolveError("unknown input kind")
    parsed = classify(input_text)
    outcome = solve(parsed)
    result = outcome.result
    result["input"] = input_text.strip()
    result["normalized"] = parsed.normalized
    result["intent"] = parsed.intent.value
    entry = SolveEntry(
        profile_id=profile_id,
        input_kind=input_kind,
        input_text=input_text.strip(),
        intent=parsed.intent.value,
        verified=bool(result.get("verified")),
        result=result,
    )
    session.add(entry)
    session.flush()
    return entry


def variants_for(entry: SolveEntry) -> list[dict[str, object]]:
    parsed = classify(entry.input_text)
    variants = build_variants(parsed, seed=int(entry.id[:8], 16))
    return [
        {
            "index": variant.index,
            "prompt": variant.prompt,
            "kind": variant.kind,
            "answer_display": variant.answer_display,
            "answer_check": variant.answer_check,
        }
        for variant in variants
    ]


def check_variant(entry: SolveEntry, index: int, response: str) -> tuple[bool, str | None]:
    variants = variants_for(entry)
    match = next((variant for variant in variants if variant["index"] == index), None)
    if match is None:
        raise SolveError("variant not found")
    from .variants import check_variant as verify

    correct = verify(str(match["answer_check"]), response)
    return correct, str(match["answer_display"])


def result_markdown(entry: SolveEntry) -> str:
    result = entry.result or {}
    lines = ["## Problem", "", f"$$ {result.get('normalized', entry.input_text)} $$", ""]
    if result.get("answer_latex"):
        lines += ["## Answer", "", f"$$ {result['answer_latex']} $$", ""]
    steps = result.get("steps") or []
    if steps:
        lines += ["## Verified steps", ""]
        for index, step in enumerate(steps, start=1):
            lines.append(f"{index}. **{step.get('title', step.get('op', 'Step'))}**")
            if step.get("before") and step.get("after"):
                lines.append(f"   $$ {step['before']} \\;\\longrightarrow\\; {step['after']} $$")
            if step.get("detail"):
                lines.append(f"   _{step['detail']}_")
            lines.append("")
    assumptions = result.get("assumptions") or []
    if assumptions:
        lines += ["## Assumptions", ""]
        lines += [f"- {assumption}" for assumption in assumptions]
    if result.get("message"):
        lines += ["", f"> {result['message']}"]
    return "\n".join(lines).strip() + "\n"


def save_as_note(session: Session, entry: SolveEntry, *, profile_id: str) -> Note:
    if not entry.verified or not (entry.result or {}).get("answer_latex"):
        raise SolveError("only a verified solve can be saved as a note")
    if entry.note_id is not None:
        existing = session.get(Note, entry.note_id)
        if existing is not None and existing.profile_id == profile_id:
            return existing
    course = ensure_scratch_course(session, profile_id)
    node_id = TreeService(session).ensure_root(course.id).id
    first_line = entry.input_text.strip().splitlines()[0] if entry.input_text.strip() else "problem"
    title = f"Solved: {first_line}"[:300]
    note = Note(
        profile_id=profile_id,
        course_id=course.id,
        node_id=node_id,
        owner_type="standalone",
        title=title,
        body=md_to_blocks(result_markdown(entry)),
        tags=normalize_tags(["solve", entry.intent]),
    )
    note.search_text = note_search_text(note)
    session.add(note)
    session.flush()
    entry.note_id = note.id
    session.flush()
    return note
