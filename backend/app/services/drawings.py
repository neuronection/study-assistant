import re
from typing import Any

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
