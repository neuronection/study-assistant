import json

from app.ai.parsing import parse_answer_blocks
from app.ai.tools import plot_function, run_tool_line


def test_plot_function_samples_curve() -> None:
    result = json.loads(plot_function("x**2"))
    data = result["data"][0]
    assert data["type"] == "scatter"
    assert data["mode"] == "lines"
    assert len(data["x"]) == 201
    assert data["x"][0] == -10.0
    assert data["x"][-1] == 10.0
    assert data["y"][0] == 100.0


def test_plot_function_discontinuity_becomes_null() -> None:
    result = json.loads(plot_function("sin(x)/x"))
    ys = result["data"][0]["y"]
    assert ys[100] is None


def test_plot_function_rejects_bad_expression() -> None:
    assert plot_function("not an expression!").startswith("error")
    assert plot_function("").startswith("error")


def test_run_tool_line_plot() -> None:
    result = json.loads(run_tool_line("PLOT", "x"))
    assert result["data"][0]["y"][0] == -10.0


def test_parse_answer_blocks_chart_fence() -> None:
    markdown = 'Look:\n\n```chart\n{"data": [{"y": [1, 2]}]}\n```\n\nNice.'
    blocks = parse_answer_blocks(markdown)
    assert [block["type"] for block in blocks] == ["text", "chart", "text"]
    assert blocks[1]["plotly"] == {"data": [{"y": [1, 2]}]}


def test_parse_answer_blocks_widget_fence() -> None:
    markdown = (
        'Which rule?\n\n```widget\n{"widget": "checklist", "id": "w1", '
        '"props": {"prompt": "pick", "items": ["a", "b"]}}\n```'
    )
    blocks = parse_answer_blocks(markdown)
    assert blocks[1]["type"] == "widget"
    assert blocks[1]["widget"] == "checklist"
    assert blocks[1]["id"] == "w1"


def test_parse_answer_blocks_no_fence() -> None:
    assert parse_answer_blocks("plain answer") == [{"type": "text", "md": "plain answer"}]


def test_parse_answer_blocks_malformed_fence_stays_text() -> None:
    markdown = 'before\n```chart\nnot json\n```\nafter'
    blocks = parse_answer_blocks(markdown)
    assert all(block["type"] == "text" for block in blocks)
    assert "".join(str(block["md"]) for block in blocks) == markdown
