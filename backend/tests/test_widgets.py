from typing import Any

from app.ai.widgets import (
    CHAT_WIDGET_DOC,
    EXGEN_WIDGET_DOC,
    WIDGET_DOC,
    WIDGET_NAMES,
    WIDGET_SPECS,
    read_widget_state,
    validate_widget_block,
    validate_widget_blocks,
)


def _block(widget: str, props: dict[str, Any], **extra: object) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "widget", "widget": widget, "id": "w1", "props": props}
    block.update(extra)
    return block


def test_valid_checklist() -> None:
    assert (
        validate_widget_block(
            _block("checklist", {"prompt": "Which?", "items": ["a", "b"], "multiple": True})
        )
        == []
    )


def test_valid_choice_and_slider_and_equation() -> None:
    assert (
        validate_widget_block(_block("choice", {"prompt": "Pick", "options": ["x", "y"]}))
        == []
    )
    assert (
        validate_widget_block(_block("slider", {"prompt": "n", "min": 0, "max": 10, "step": 1}))
        == []
    )
    assert (
        validate_widget_block(_block("equation_input", {"prompt": "f(x)"}))
        == []
    )


def test_valid_numberline_chart_geo() -> None:
    assert validate_widget_block(_block("numberline", {"min": -5, "max": 5})) == []
    assert validate_widget_block(_block("chart", {"plotly": {"data": []}})) == []
    assert validate_widget_block(_block("geo", {"jsxgraph": "board.create('point',[0,0])"})) == []


def test_unknown_widget_name() -> None:
    problems = validate_widget_block(_block("hologram", {}))
    assert any("unknown widget" in problem for problem in problems)


def test_wrong_prop_type() -> None:
    problems = validate_widget_block(
        _block("checklist", {"prompt": "Which?", "items": "not-a-list"})
    )
    assert problems


def test_missing_required_prompt() -> None:
    problems = validate_widget_block(_block("choice", {"options": ["x", "y"]}))
    assert any("'prompt'" in problem for problem in problems)


def test_too_few_options() -> None:
    problems = validate_widget_block(_block("choice", {"prompt": "Pick", "options": ["x"]}))
    assert any("at least 2" in problem for problem in problems)


def test_oversized_items() -> None:
    problems = validate_widget_block(
        _block("checklist", {"prompt": "Which?", "items": ["x" * 500]})
    )
    assert any("length limit" in problem for problem in problems)


def test_missing_id() -> None:
    block = {"type": "widget", "widget": "slider", "props": {"prompt": "n", "max": 5}}
    problems = validate_widget_block(block)
    assert any("'id'" in problem for problem in problems)


def test_non_object_block() -> None:
    assert validate_widget_block("widget") == ["widget block must be an object"]


def test_non_widget_type() -> None:
    problems = validate_widget_block({"type": "text", "md": "hi"})
    assert any("not a widget" in problem for problem in problems)


def test_bad_state() -> None:
    problems = validate_widget_block(
        _block("slider", {"prompt": "n", "max": 5}, state="not-an-object")
    )
    assert any("'state'" in problem for problem in problems)


def test_slider_min_not_less_than_max() -> None:
    problems = validate_widget_block(_block("slider", {"prompt": "n", "min": 10, "max": 5}))
    assert any("less than" in problem for problem in problems)


def test_validate_widget_blocks_filters_non_widget_blocks() -> None:
    blocks = [
        {"type": "text", "md": "hello"},
        _block("checklist", {"prompt": "Which?", "items": ["a"]}),
        _block("hologram", {}),
    ]
    problems = validate_widget_blocks(blocks)
    assert len(problems) == 1
    assert "unknown widget" in problems[0]


def test_validate_widget_blocks_ignores_non_list() -> None:
    assert validate_widget_blocks(None) == []


def test_read_widget_state_lookup() -> None:
    assert read_widget_state({"w1": {"checked": []}}, "w1") == {"checked": []}
    assert read_widget_state({"w1": {}}, "w2") is None
    assert read_widget_state(None, "w1") is None


def test_widget_names_derive_from_specs() -> None:
    assert set(WIDGET_NAMES) == set(WIDGET_SPECS)


def test_widget_doc_covers_every_widget_and_its_props() -> None:
    for name in WIDGET_NAMES:
        assert name in WIDGET_DOC
    assert "plotly" in WIDGET_DOC
    assert "jsxgraph" in WIDGET_DOC


def test_chat_widget_doc_teaches_fences() -> None:
    assert "```chart" in CHAT_WIDGET_DOC
    assert "```widget" in CHAT_WIDGET_DOC


def test_exgen_widget_doc_teaches_widgets_array() -> None:
    assert '"widgets"' in EXGEN_WIDGET_DOC
    assert '"type": "widget"' in EXGEN_WIDGET_DOC
