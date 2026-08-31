import re
from typing import Any

from sqlalchemy.orm import Session

from ...domain.models import Job
from ...jobs.runner import JobRunner

DRAWING_MD = re.compile(r"!\[[^\]]*\]\(ca-drawing://(\d+)\)")


def md_to_blocks(md: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    position = 0
    for match in DRAWING_MD.finditer(md):
        before = md[position : match.start()]
        if before:
            blocks.append({"type": "text", "md": before})
        blocks.append({"type": "drawing", "drawing_id": int(match.group(1))})
        position = match.end()
    rest = md[position:]
    if rest:
        blocks.append({"type": "text", "md": rest})
    return blocks


def drawing_ref_ids(md: str) -> set[int]:
    return {int(value) for value in DRAWING_MD.findall(md)}


def strip_drawing_refs(md: str, drawing_id: int) -> str:
    return DRAWING_MD.sub(
        lambda match: "" if int(match.group(1)) == drawing_id else match.group(0), md
    )


def remap_drawing_refs(md: str, mapping: dict[int, int]) -> str:
    def _replace(match: re.Match[str]) -> str:
        old = int(match.group(1))
        new = mapping.get(old, old)
        alt = match.group(0).split("](", 1)[0][2:]
        return f"![{alt}](ca-drawing://{new})"

    return DRAWING_MD.sub(_replace, md)


def blocks_md(blocks: list[dict[str, Any]] | None) -> str:
    if not blocks:
        return ""
    result = ""
    for block in blocks:
        if block.get("type") == "drawing":
            part = f"![drawing](ca-drawing://{block['drawing_id']})"
        elif block.get("md"):
            part = str(block["md"])
        else:
            continue
        if result == "":
            result = part
        elif not (result.endswith("\n") or part.startswith("\n")):
            result += f"\n\n{part}"
        else:
            result += part
    return result


def note_search_text(note: Any) -> str:
    parts = [note.title, blocks_md(note.body)]
    for drawing in note.drawings:
        if drawing.ocr_markdown:
            parts.append(drawing.ocr_markdown)
    return "\n".join(parts)


def enqueue_drawing_ocr(
    session: Session, *, kind: str, owner_id: int, drawing_id: int
) -> int:
    payload: dict[str, Any] = {"kind": kind, "drawing_id": drawing_id}
    payload[f"{kind}_id"] = owner_id
    job = JobRunner.enqueue(session, "drawing_ocr", payload)
    return job.id


def pending_ocr_job_id(session: Session, drawing: Any) -> int | None:
    job_id = drawing.ocr_job_id
    if job_id is None:
        return None
    job = session.get(Job, int(job_id))
    if job is not None and job.status in {"queued", "running"}:
        return int(job_id)
    return None
