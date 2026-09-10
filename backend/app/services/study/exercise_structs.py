import random
import re
from typing import Any

STRUCT_KINDS = ("matching", "ordering", "categorize", "fill_blank")
BLANK_RE = re.compile(r"\{\{(\d+)\}\}")


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def validate_structural_payload(kind: str, payload: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if kind == "matching":
        pairs = _as_list(payload.get("pairs"))
        if not 2 <= len(pairs) <= 8:
            problems.append("matching: 2-8 pairs required")
            return problems
        lefts: set[str] = set()
        rights: set[str] = set()
        for index, pair in enumerate(pairs):
            if not isinstance(pair, dict):
                problems.append(f"pair {index}: not an object")
                continue
            left = str(pair.get("left", "")).strip()
            right = str(pair.get("right", "")).strip()
            if not left or not right:
                problems.append(f"pair {index}: empty side")
                continue
            if normalize_text(left) in lefts or normalize_text(right) in rights:
                problems.append(f"pair {index}: duplicate side label")
            lefts.add(normalize_text(left))
            rights.add(normalize_text(right))
    elif kind == "ordering":
        items = _as_list(payload.get("items"))
        if not 3 <= len(items) <= 8:
            problems.append("ordering: 3-8 items required")
            return problems
        seen: set[str] = set()
        for index, item in enumerate(items):
            label = str(item).strip() if not isinstance(item, dict) else ""
            if not label:
                problems.append(f"item {index}: empty label")
                continue
            if normalize_text(label) in seen:
                problems.append(f"item {index}: duplicate label")
            seen.add(normalize_text(label))
    elif kind == "categorize":
        categories = _as_list(payload.get("categories"))
        items = _as_list(payload.get("items"))
        if not 2 <= len(categories) <= 5:
            problems.append("categorize: 2-5 categories required")
            return problems
        category_labels: set[str] = set()
        for index, category in enumerate(categories):
            label = str(category).strip()
            if not label:
                problems.append(f"category {index}: empty label")
            elif normalize_text(label) in category_labels:
                problems.append(f"category {index}: duplicate label")
            category_labels.add(normalize_text(label))
        if not 2 <= len(items) <= 10:
            problems.append("categorize: 2-10 items required")
            return problems
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                problems.append(f"item {index}: not an object")
                continue
            if not str(item.get("label", "")).strip():
                problems.append(f"item {index}: empty label")
                continue
            category = item.get("category")
            if not isinstance(category, int) or not 0 <= category < len(categories):
                problems.append(f"item {index}: category index out of range")
    elif kind == "fill_blank":
        prompt_md = str(payload.get("prompt_md", ""))
        answers = _as_list(payload.get("answers"))
        blanks = [int(match) for match in BLANK_RE.findall(prompt_md)]
        expected = list(range(1, len(blanks) + 1))
        if not blanks or sorted(blanks) != expected:
            problems.append(
                "fill_blank: prompt blanks must be {{1}}..{{n}} with no gaps"
            )
            return problems
        if len(answers) != len(blanks):
            problems.append(
                f"fill_blank: {len(blanks)} answers required, got {len(answers)}"
            )
            return problems
        for index, answer in enumerate(answers):
            accepted = answer if isinstance(answer, list) else [answer]
            accepted = [str(entry).strip() for entry in accepted if str(entry).strip()]
            if not accepted:
                problems.append(f"blank {index}: no accepted answer")
    else:
        problems.append(f"unknown structural kind: {kind}")
    return problems


def _index_list(response: Any, length: int) -> list[int] | None:
    if not isinstance(response, list) or len(response) != length:
        return None
    result: list[int] = []
    for entry in response:
        if not isinstance(entry, int) or not 0 <= entry < max(length, 1):
            return None
        result.append(entry)
    return result


def check_structural(
    kind: str, payload: dict[str, Any], response: Any
) -> tuple[bool, str]:
    if kind == "matching":
        pairs = _as_list(payload.get("pairs"))
        picks = _index_list(response, len(pairs))
        if picks is None:
            return False, "matching: malformed response"
        hits = sum(1 for index, pick in enumerate(picks) if pick == index)
        return hits == len(pairs), (
            "matching: correct"
            if hits == len(pairs)
            else f"matching: {hits}/{len(pairs)} pairs correct"
        )
    if kind == "ordering":
        items = _as_list(payload.get("items"))
        order = _index_list(response, len(items))
        if order is None or sorted(order) != list(range(len(items))):
            return False, "ordering: malformed response"
        hits = sum(1 for index, item in enumerate(order) if item == index)
        return hits == len(items), (
            "ordering: correct"
            if hits == len(items)
            else f"ordering: {hits}/{len(items)} items in position"
        )
    if kind == "categorize":
        entries = _as_list(payload.get("items"))
        picks = _index_list(response, len(entries))
        if picks is None:
            return False, "categorize: malformed response"
        hits = sum(
            1
            for index, pick in enumerate(picks)
            if isinstance(entries[index], dict) and picks[index]
            == entries[index].get("category")
        )
        return hits == len(entries), (
            "categorize: correct"
            if hits == len(entries)
            else f"categorize: {hits}/{len(entries)} items sorted correctly"
        )
    if kind == "fill_blank":
        answers = _as_list(payload.get("answers"))
        values = _as_list(response)
        if len(values) != len(answers):
            return False, "fill_blank: malformed response"
        hits = 0
        for index, answer in enumerate(answers):
            accepted = answer if isinstance(answer, list) else [answer]
            accepted = [str(entry) for entry in accepted if str(entry).strip()]
            given = str(values[index]) if index < len(values) else ""
            if normalize_text(given) in {normalize_text(entry) for entry in accepted}:
                hits += 1
        return hits == len(answers), (
            "fill_blank: correct"
            if hits == len(answers)
            else f"fill_blank: {hits}/{len(answers)} blanks correct"
        )
    return False, f"unknown structural kind: {kind}"


def public_input(kind: str, payload: dict[str, Any], seed: int) -> dict[str, Any]:
    rnd = random.Random(seed)
    if kind == "matching":
        pairs = _as_list(payload.get("pairs"))
        rights = list(range(len(pairs)))
        rnd.shuffle(rights)
        return {
            "widget": "matching",
            "lefts": [str(pair.get("left", "")) for pair in pairs],
            "rights": [
                {"index": index, "label": str(pairs[index].get("right", ""))}
                for index in rights
            ],
        }
    if kind == "ordering":
        items = _as_list(payload.get("items"))
        order = list(range(len(items)))
        rnd.shuffle(order)
        return {
            "widget": "ordering",
            "items": [
                {"id": index, "label": str(items[index])} for index in order
            ],
        }
    if kind == "categorize":
        return {
            "widget": "categorize",
            "categories": [str(entry) for entry in _as_list(payload.get("categories"))],
            "items": [
                str(entry.get("label", "")) for entry in _as_list(payload.get("items"))
            ],
        }
    if kind == "fill_blank":
        prompt_md = str(payload.get("prompt_md", ""))
        return {
            "widget": "fill_blank",
            "prompt_md": prompt_md,
            "blank_count": len(BLANK_RE.findall(prompt_md)),
        }
    return {"widget": "math"}
