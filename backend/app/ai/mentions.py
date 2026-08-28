import re
from dataclasses import asdict, dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

MENTION_RE = re.compile(r"\[([MNCTQE])(\d+)\]")

KIND_BY_LETTER: dict[str, str] = {
    "M": "material",
    "N": "note",
    "C": "concept",
    "T": "node",
    "Q": "quiz",
    "E": "exercise",
}
LETTER_BY_KIND: dict[str, str] = {kind: letter for letter, kind in KIND_BY_LETTER.items()}

REGISTRY_CAP = 200
MANIFEST_CAP = 40

MENTION_TEACH = (
    "You may reference the items listed above in your answer by their handle "
    "(e.g. [M12], [N3]) exactly as shown; the student's app turns them into "
    "clickable cards. Only use handles that were listed — never invent one."
)


@dataclass(frozen=True)
class MentionRef:
    ref: str
    kind: str
    id: int
    title: str
    course_id: int | None = None
    summary: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class MentionRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, MentionRef] = {}

    def add(
        self,
        kind: str,
        item_id: int,
        title: str,
        course_id: int | None = None,
        summary: str | None = None,
    ) -> MentionRef:
        letter = LETTER_BY_KIND.get(kind)
        if letter is None:
            raise ValueError(f"unknown mention kind: {kind}")
        ref = f"{letter}{item_id}"
        existing = self._entries.get(ref)
        if existing is not None:
            return existing
        entry = MentionRef(
            ref=ref,
            kind=kind,
            id=item_id,
            title=title,
            course_id=course_id,
            summary=summary,
        )
        self._entries[ref] = entry
        return entry

    def parse(self, text: str) -> list[MentionRef]:
        used: list[MentionRef] = []
        seen: set[str] = set()
        for match in MENTION_RE.finditer(text):
            ref = f"{match.group(1)}{match.group(2)}"
            entry = self._entries.get(ref)
            if entry is None or entry.ref in seen:
                continue
            seen.add(entry.ref)
            used.append(entry)
        return used

    def extend(self, other: "MentionRegistry") -> None:
        for entry in other.entries():
            self._entries.setdefault(entry.ref, entry)

    def entries(self) -> list[MentionRef]:
        return list(self._entries.values())[-REGISTRY_CAP:]

    def refs(self) -> list[str]:
        return [entry.ref for entry in self._entries.values()]

    def get(self, ref: str) -> MentionRef | None:
        return self._entries.get(ref)

    def __contains__(self, ref: str) -> bool:
        return ref in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def out_of_range(self, text: str) -> list[str]:
        handles = {f"{match.group(1)}{match.group(2)}" for match in MENTION_RE.finditer(text)}
        return sorted(handle for handle in handles if handle not in self._entries)

    def prompt_section(self) -> str:
        entries = self.entries()
        if not entries:
            return ""
        lines = []
        for entry in entries[:MANIFEST_CAP]:
            summary = (entry.summary or "").strip().replace("\n", " ")
            if summary:
                summary = summary[:200]
                lines.append(f"{entry.ref} = {entry.title} — {summary}")
            else:
                lines.append(f"{entry.ref} = {entry.title}")
        return (
            "Referenceable items (mention them by handle; READ a handle to see its "
            "full content):\n"
            + "\n".join(lines)
            + f"\n\n{MENTION_TEACH}"
        )

    def to_json(self) -> list[dict[str, Any]]:
        return [entry.as_dict() for entry in self.entries()]


def registry_from_json(entries: list[dict[str, Any]] | None) -> MentionRegistry:
    registry = MentionRegistry()
    if not entries:
        return registry
    for entry in entries:
        try:
            registry.add(
                str(entry["kind"]),
                int(entry["id"]),
                str(entry["title"]),
                int(entry["course_id"]) if entry.get("course_id") is not None else None,
                str(entry["summary"]) if entry.get("summary") else None,
            )
        except (KeyError, ValueError, TypeError):
            continue
    return registry
