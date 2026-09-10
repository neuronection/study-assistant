from typing import Any

import pytest

from app.agui.state import StateStore, apply_deltas, apply_patch


def test_add_object_key() -> None:
    document: dict[str, Any] = {"a": 1}
    apply_patch(document, [{"op": "add", "path": "/b", "value": 2}])
    assert document == {"a": 1, "b": 2}


def test_add_nested_key() -> None:
    document: dict[str, Any] = {"a": {"b": 1}}
    apply_patch(document, [{"op": "add", "path": "/a/c", "value": 3}])
    assert document == {"a": {"b": 1, "c": 3}}


def test_add_append_to_array() -> None:
    document: dict[str, Any] = {"items": [1, 2]}
    apply_patch(document, [{"op": "add", "path": "/items/-", "value": 3}])
    assert document == {"items": [1, 2, 3]}


def test_add_at_array_index() -> None:
    document: dict[str, Any] = {"items": [1, 3]}
    apply_patch(document, [{"op": "add", "path": "/items/1", "value": 2}])
    assert document == {"items": [1, 2, 3]}


def test_remove_object_key() -> None:
    document: dict[str, Any] = {"a": 1, "b": 2}
    apply_patch(document, [{"op": "remove", "path": "/b"}])
    assert document == {"a": 1}


def test_remove_array_element() -> None:
    document: dict[str, Any] = {"items": [1, 2, 3]}
    apply_patch(document, [{"op": "remove", "path": "/items/1"}])
    assert document == {"items": [1, 3]}


def test_replace_value() -> None:
    document: dict[str, Any] = {"a": 1}
    apply_patch(document, [{"op": "replace", "path": "/a", "value": 9}])
    assert document == {"a": 9}


def test_move_value() -> None:
    document: dict[str, Any] = {"a": 1, "b": 2}
    apply_patch(document, [{"op": "move", "from": "/a", "path": "/c"}])
    assert document == {"b": 2, "c": 1}


def test_copy_value_is_independent() -> None:
    document: dict[str, Any] = {"a": [1]}
    apply_patch(document, [{"op": "copy", "from": "/a", "path": "/b"}])
    document["a"].append(2)
    assert document["b"] == [1]


def test_test_passes_and_fails() -> None:
    document: dict[str, Any] = {"a": 1}
    apply_patch(document, [{"op": "test", "path": "/a", "value": 1}])
    with pytest.raises(ValueError):
        apply_patch(document, [{"op": "test", "path": "/a", "value": 2}])


def test_pointer_escape_sequences() -> None:
    document: dict[str, Any] = {"a/b": {"c~d": 1}}
    apply_patch(document, [{"op": "replace", "path": "/a~1b/c~0d", "value": 2}])
    assert document == {"a/b": {"c~d": 2}}


def test_unknown_op_raises() -> None:
    with pytest.raises(ValueError):
        apply_patch({}, [{"op": "bogus", "path": "/a", "value": 1}])


def test_missing_parent_raises() -> None:
    with pytest.raises(ValueError):
        apply_patch({}, [{"op": "add", "path": "/a/b", "value": 1}])


def test_replace_missing_key_raises() -> None:
    with pytest.raises(ValueError):
        apply_patch({}, [{"op": "replace", "path": "/a", "value": 1}])


def test_add_existing_key_raises() -> None:
    with pytest.raises(ValueError):
        apply_patch({"a": 1}, [{"op": "add", "path": "/a", "value": 2}])


def test_apply_deltas_folds_a_sequence() -> None:
    document: dict[str, Any] = {"score": 0}
    apply_deltas(
        document,
        [
            [{"op": "replace", "path": "/score", "value": 1}],
            [{"op": "replace", "path": "/score", "value": 2}],
        ],
    )
    assert document == {"score": 2}


def test_state_store_snapshot_is_independent_and_round_trips() -> None:
    store = StateStore({"checked": ["factor"], "complete": False})
    snapshot = store.snapshot()
    snapshot["checked"].append("chain rule")
    assert store.snapshot() == {"checked": ["factor"], "complete": False}

    store.apply([{"op": "replace", "path": "/complete", "value": True}])
    assert store.snapshot() == {"checked": ["factor"], "complete": True}
