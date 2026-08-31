import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...pipelines.qpkg import read_qpkg
from ...pipelines.quizgen import validate_question

INBOX_SUFFIXES = (".caq.json", ".json", ".qpkg")
SCHEMA_CARD = """# Study Assistant quiz authoring (caq/v1)

Drop a `.caq.json` file in this directory and the app will pick it up on the next
inbox scan. The minimal schema:

```json
{
  "$schema": "caq/v1",
  "title": "Your quiz title",
  "questions": [
    {
      "id": "q1",
      "type": "single",
      "stem_md": "Differentiate $f(x) = x^2 \\sin x$",
      "options_md": ["$2x\\sin x$", "$2x\\cos x$", "$x^2\\cos x + 2x\\sin x$"],
      "answer": {"index": 2},
      "explanation_md": "Product rule: $(fg)' = f'g + fg'$.",
      "concepts": ["product rule"],
      "skill": "procedural",
      "bloom": "apply",
      "difficulty": 3,
      "expected_time_sec": 120,
      "misconceptions": {"0": "forgot_product_second_term", "1": "mixed_up_rules"}
    }
  ]
}
```

Required per question: type, stem_md, answer, explanation_md, concepts (1-3),
skill (conceptual|procedural|applied|notation), bloom (remember|understand|apply|
analyze|evaluate|create), difficulty 1-5, expected_time_sec. Types: single, multi,
truefalse, text, numeric, equation. Math MUST be LaTeX in $...$; for equation
questions the answer value must parse (sympy-compatible). Files are validated with
the same rules the app applies to its own generated quizzes — invalid files are
renamed `.rejected` with a report next to them.
"""

SCHEMA_JSON_NAME = "schema.json"
AUTHORING_NAME = "AUTHORING.md"


@dataclass(frozen=True)
class InboxEntry:
    filename: str
    kind: str
    title: str
    ok: bool
    problems: list[str] = field(default_factory=list)
    question_count: int = 0


def _validate_document(document: dict[str, Any]) -> tuple[list[str], int, str]:
    questions = document.get("questions")
    if not isinstance(questions, list) or not questions:
        return ["no questions list"], 0, str(document.get("title", ""))
    problems: list[str] = []
    for index, raw in enumerate(questions):
        if not isinstance(raw, dict):
            problems.append(f"q{index}: not an object")
            continue
        draft = dict(raw)
        answer = draft.get("answer")
        if not isinstance(answer, dict):
            qtype = draft.get("type")
            if qtype == "single" and isinstance(answer, int) and not isinstance(answer, bool):
                draft["answer"] = {"index": answer}
            elif qtype == "multi" and isinstance(answer, list):
                draft["answer"] = {"indices": answer}
            elif (qtype == "truefalse" and isinstance(answer, bool)) or (
                qtype in ("text", "equation") and isinstance(answer, str)
            ):
                draft["answer"] = {"value": answer}
            elif qtype == "numeric" and isinstance(answer, (int, float)):
                draft["answer"] = {"value": answer, "tolerance": 1e-6}
        problems.extend(validate_question(draft, index))
    return problems, len(questions), str(document.get("title", ""))


class InboxService:
    def __init__(self, root: Path) -> None:
        self._root = root

    def ensure_root(self) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        schema = self._root / SCHEMA_JSON_NAME
        if not schema.exists():
            schema.write_text(SCHEMA_CARD, encoding="utf-8")
        authoring = self._root / AUTHORING_NAME
        if not authoring.exists():
            authoring.write_text(SCHEMA_CARD, encoding="utf-8")
        return self._root

    def scan(self) -> list[InboxEntry]:
        root = self.ensure_root()
        entries: list[InboxEntry] = []
        for path in sorted(root.iterdir()):
            if not path.is_file():
                continue
            if path.name in (SCHEMA_JSON_NAME, AUTHORING_NAME):
                continue
            if path.name.endswith((".imported", ".rejected", ".md", ".txt")):
                continue
            if path.suffix == ".qpkg":
                entries.append(self._validate_qpkg(path))
            elif path.suffix == ".json" or path.name.endswith(".caq.json"):
                entries.append(self._validate_caq(path))
        return entries

    def _validate_caq(self, path: Path) -> InboxEntry:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise ValueError("top level must be an object")
        except ValueError as error:
            return InboxEntry(
                filename=path.name, kind="caq", title="", ok=False,
                problems=[f"invalid JSON: {error}"],
            )
        problems, count, title = _validate_document(document)
        return InboxEntry(
            filename=path.name, kind="caq", title=title, ok=not problems,
            problems=problems, question_count=count,
        )

    def _validate_qpkg(self, path: Path) -> InboxEntry:
        try:
            content = read_qpkg(path.read_bytes())
        except Exception as error:
            detail = getattr(error, "detail", str(error))
            return InboxEntry(
                filename=path.name, kind="qpkg", title="", ok=False,
                problems=[f"package error: {detail}"],
            )
        problems, count, title = _validate_document(content.document)
        return InboxEntry(
            filename=path.name, kind="qpkg", title=title, ok=not problems,
            problems=problems, question_count=count,
        )

    def load_document(self, filename: str) -> dict[str, Any]:
        root = self.ensure_root()
        if not re.fullmatch(r"[A-Za-z0-9._\- ]+", filename):
            raise ValueError("bad filename")
        path = root / filename
        if not path.is_file():
            raise FileNotFoundError(filename)
        if path.suffix == ".qpkg":
            return dict(read_qpkg(path.read_bytes()).document)
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("top level must be an object")
        return document

    def mark(self, filename: str, status: str, report: str | None = None) -> Path:
        root = self.ensure_root()
        if not re.fullmatch(r"[A-Za-z0-9._\- ]+", filename):
            raise ValueError("bad filename")
        path = root / filename
        if not path.is_file():
            raise FileNotFoundError(filename)
        target = path.with_name(f"{path.name}.{status}")
        moved = shutil.move(str(path), str(target))
        if report is not None:
            path.with_name(f"{target.name}.txt").write_text(report, encoding="utf-8")
        return Path(moved)
