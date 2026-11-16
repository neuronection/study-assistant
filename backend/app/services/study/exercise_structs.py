import random
import re
from collections.abc import Mapping
from typing import Any

STRUCT_KINDS = ("matching", "ordering", "categorize", "fill_blank", "diagram_label")
BLANK_RE = re.compile(r"\{\{(\d+)\}\}")


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def validate_structural_payload(kind: str, payload: Mapping[str, Any]) -> list[str]:
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
    elif kind == "diagram_label":
        image_sha = str(payload.get("image_sha", "")).strip()
        if not image_sha:
            problems.append("diagram_label: image_sha is required")
        hotspots = _as_list(payload.get("hotspots"))
        if not 1 <= len(hotspots) <= 20:
            problems.append("diagram_label: 1-20 hotspots required")
            return problems
        labels: set[str] = set()
        ids: set[str] = set()
        for index, spot in enumerate(hotspots):
            if not isinstance(spot, dict):
                problems.append(f"hotspot {index}: not an object")
                continue
            spot_id = str(spot.get("id", "")).strip()
            label = str(spot.get("label", "")).strip()
            if not spot_id or spot_id in ids:
                problems.append(f"hotspot {index}: missing or duplicate id")
            if not label or normalize_text(label) in labels:
                problems.append(f"hotspot {index}: missing or duplicate label")
            ids.add(spot_id)
            labels.add(normalize_text(label))
            try:
                x = float(spot.get("x", 0))
                y = float(spot.get("y", 0))
                w = float(spot.get("w", 0))
                h = float(spot.get("h", 0))
            except (TypeError, ValueError):
                problems.append(f"hotspot {index}: coordinates must be numbers")
                continue
            if min(x, y) < 0 or w <= 0 or h <= 0 or x + w > 1.0001 or y + h > 1.0001:
                problems.append(f"hotspot {index}: region outside the image")
        bank = [str(entry).strip() for entry in _as_list(payload.get("labels"))]
        if bank:
            if len({normalize_text(entry) for entry in bank}) != len(bank):
                problems.append("diagram_label: duplicate label in bank")
            missing = labels - {normalize_text(entry) for entry in bank}
            if missing:
                problems.append("diagram_label: label bank misses a hotspot label")
    elif kind == "fill_blank":
        prompt_md = str(payload.get("prompt_md", ""))
        answers = _as_list(payload.get("answers"))
        blanks = [int(match) for match in BLANK_RE.findall(prompt_md)]
        expected = list(range(1, len(blanks) + 1))
        if not blanks or sorted(blanks) != expected:
            problems.append("fill_blank: prompt blanks must be {{1}}..{{n}} with no gaps")
            return problems
        if len(answers) != len(blanks):
            problems.append(f"fill_blank: {len(blanks)} answers required, got {len(answers)}")
            return problems
        for index, answer in enumerate(answers):
            accepted = answer if isinstance(answer, list) else [answer]
            accepted = [str(entry).strip() for entry in accepted if str(entry).strip()]
            if not accepted:
                problems.append(f"blank {index}: no accepted answer")
    else:
        problems.append(f"unknown structural kind: {kind}")
    return problems


def _seed_value(seed: str) -> int:
    return int(seed.replace("-", "")[:16], 16)


def _index_list(response: Any, length: int) -> list[int] | None:
    if not isinstance(response, list) or len(response) != length:
        return None
    result: list[int] = []
    for entry in response:
        if not isinstance(entry, int) or not 0 <= entry < max(length, 1):
            return None
        result.append(entry)
    return result


def check_structural(kind: str, payload: Mapping[str, Any], response: Any) -> tuple[bool, str]:
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
            if isinstance(entries[index], dict) and picks[index] == entries[index].get("category")
        )
        return hits == len(entries), (
            "categorize: correct"
            if hits == len(entries)
            else f"categorize: {hits}/{len(entries)} items sorted correctly"
        )
    if kind == "diagram_label":
        hotspots = _as_list(payload.get("hotspots"))
        expected = {
            str(spot.get("id")): normalize_text(str(spot.get("label", "")))
            for spot in hotspots
            if isinstance(spot, dict)
        }
        placements = response if isinstance(response, list) else []
        chosen: dict[str, str] = {}
        for entry in placements:
            if not isinstance(entry, dict):
                return False, "diagram_label: malformed response"
            hotspot_id = str(entry.get("hotspot_id", ""))
            label = normalize_text(str(entry.get("label", "")))
            if hotspot_id in chosen:
                return False, "diagram_label: hotspot labelled twice"
            chosen[hotspot_id] = label
        hits = sum(1 for hotspot_id, label in expected.items() if chosen.get(hotspot_id) == label)
        return hits == len(expected), (
            "diagram_label: correct"
            if hits == len(expected)
            else f"diagram_label: {hits}/{len(expected)} labels correct"
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


def public_input(kind: str, payload: Mapping[str, Any], seed: str) -> dict[str, Any]:
    rnd = random.Random(_seed_value(seed))
    if kind == "matching":
        pairs = _as_list(payload.get("pairs"))
        rights = list(range(len(pairs)))
        rnd.shuffle(rights)
        return {
            "widget": "matching",
            "lefts": [str(pair.get("left", "")) for pair in pairs],
            "rights": [
                {"index": index, "label": str(pairs[index].get("right", ""))} for index in rights
            ],
        }
    if kind == "ordering":
        items = _as_list(payload.get("items"))
        order = list(range(len(items)))
        rnd.shuffle(order)
        return {
            "widget": "ordering",
            "items": [{"id": index, "label": str(items[index])} for index in order],
        }
    if kind == "categorize":
        return {
            "widget": "categorize",
            "categories": [str(entry) for entry in _as_list(payload.get("categories"))],
            "items": [str(entry.get("label", "")) for entry in _as_list(payload.get("items"))],
        }
    if kind == "diagram_label":
        hotspots = _as_list(payload.get("hotspots"))
        labels = [str(entry).strip() for entry in _as_list(payload.get("labels"))]
        if not labels:
            labels = [str(spot.get("label", "")) for spot in hotspots]
        rnd.shuffle(labels)
        return {
            "widget": "diagram_label",
            "image_sha": str(payload.get("image_sha", "")),
            "hotspots": [
                {
                    "id": str(spot.get("id", "")),
                    "x": float(spot.get("x", 0)),
                    "y": float(spot.get("y", 0)),
                    "w": float(spot.get("w", 0)),
                    "h": float(spot.get("h", 0)),
                }
                for spot in hotspots
            ],
            "labels": labels,
            "mode": str(payload.get("mode", "click")),
        }
    if kind == "fill_blank":
        prompt_md = str(payload.get("prompt_md", ""))
        return {
            "widget": "fill_blank",
            "prompt_md": prompt_md,
            "blank_count": len(BLANK_RE.findall(prompt_md)),
        }
    return {"widget": "math"}
