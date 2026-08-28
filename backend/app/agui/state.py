import copy
from typing import Any


def _parse_pointer(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError(f"invalid JSON pointer: {pointer!r}")
    return [
        token.replace("~1", "/").replace("~0", "~")
        for token in pointer[1:].split("/")
    ]


def _existing_index(node: list[Any], token: str) -> int:
    try:
        index = int(token)
    except ValueError as error:
        raise ValueError(f"invalid array index {token!r}") from error
    if index < 0 or index >= len(node):
        raise ValueError(f"array index {token!r} out of range")
    return index


def _insert_index(node: list[Any], token: str) -> int:
    if token == "-":
        return len(node)
    try:
        index = int(token)
    except ValueError as error:
        raise ValueError(f"invalid array index {token!r}") from error
    if index < 0 or index > len(node):
        raise ValueError(f"array index {token!r} out of range")
    return index


def _descend(node: Any, token: str) -> Any:
    if isinstance(node, dict):
        if token not in node:
            raise ValueError(f"path segment {token!r} does not exist")
        return node[token]
    if isinstance(node, list):
        return node[_existing_index(node, token)]
    raise ValueError(f"cannot descend into {type(node).__name__}")


def _resolve(document: Any, tokens: list[str]) -> Any:
    node = document
    for token in tokens:
        node = _descend(node, token)
    return node


def _parent(document: Any, tokens: list[str]) -> tuple[Any, str]:
    if not tokens:
        raise ValueError("path must identify a location")
    node = document
    for token in tokens[:-1]:
        node = _descend(node, token)
    return node, tokens[-1]


def _set_at(document: Any, tokens: list[str], value: Any, replace: bool) -> None:
    parent, key = _parent(document, tokens)
    if isinstance(parent, dict):
        if replace and key not in parent:
            raise ValueError(f"key {key!r} does not exist")
        if not replace and key in parent:
            raise ValueError(f"key {key!r} already exists")
        parent[key] = value
        return
    if isinstance(parent, list):
        if replace:
            parent[_existing_index(parent, key)] = value
        else:
            parent.insert(_insert_index(parent, key), value)
        return
    raise ValueError("parent is not a container")


def _remove_at(document: Any, tokens: list[str]) -> Any:
    parent, key = _parent(document, tokens)
    if isinstance(parent, dict):
        if key not in parent:
            raise ValueError(f"key {key!r} does not exist")
        return parent.pop(key)
    if isinstance(parent, list):
        return parent.pop(_existing_index(parent, key))
    raise ValueError("parent is not a container")


def _test_at(document: Any, tokens: list[str], value: Any) -> None:
    if _resolve(document, tokens) != value:
        raise ValueError("JSON Patch test failed")


def apply_patch(document: Any, patch: list[dict[str, Any]]) -> Any:
    for operation in patch:
        op = operation.get("op")
        path = _parse_pointer(str(operation.get("path", "")))
        if op == "add":
            _set_at(document, path, operation["value"], replace=False)
        elif op == "remove":
            _remove_at(document, path)
        elif op == "replace":
            _set_at(document, path, operation["value"], replace=True)
        elif op == "move":
            source = _parse_pointer(str(operation.get("from", "")))
            _set_at(document, path, _remove_at(document, source), replace=False)
        elif op == "copy":
            source = _parse_pointer(str(operation.get("from", "")))
            _set_at(document, path, copy.deepcopy(_resolve(document, source)), replace=False)
        elif op == "test":
            _test_at(document, path, operation["value"])
        else:
            raise ValueError(f"unknown JSON Patch op: {op!r}")
    return document


def apply_deltas(document: Any, deltas: list[list[dict[str, Any]]]) -> Any:
    for delta in deltas:
        apply_patch(document, delta)
    return document


class StateStore:
    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._state: dict[str, Any] = initial if initial is not None else {}

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self._state)

    def apply(self, delta: list[dict[str, Any]]) -> dict[str, Any]:
        apply_patch(self._state, delta)
        return self.snapshot()
