import json
from dataclasses import dataclass
from pathlib import Path

from app.shell import (
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
    WINDOW_STATE_FILE,
    WindowGeometryTracker,
    WindowState,
    clamp_window_state,
    default_window_state,
    load_window_state,
    save_window_state,
)


@dataclass
class Screen:
    x: int = 0
    y: int = 0
    width: int = 1920
    height: int = 1080


def test_default_state_centers_on_primary_screen() -> None:
    state = default_window_state()
    clamped = clamp_window_state(state, [Screen()])
    assert clamped["width"] == DEFAULT_WINDOW_WIDTH
    assert clamped["height"] == DEFAULT_WINDOW_HEIGHT
    assert clamped["x"] == (1920 - DEFAULT_WINDOW_WIDTH) // 2
    assert clamped["y"] == (1080 - DEFAULT_WINDOW_HEIGHT) // 2
    assert "maximized" not in clamped


def test_clamp_keeps_on_screen_geometry() -> None:
    state: WindowState = {"width": 1000, "height": 700, "x": 200, "y": 100}
    clamped = clamp_window_state(state, [Screen()])
    assert clamped == state


def test_clamp_pulls_off_screen_window_back() -> None:
    state: WindowState = {"width": 800, "height": 600, "x": 5000, "y": 4000}
    clamped = clamp_window_state(state, [Screen()])
    assert clamped["x"] <= 1920 - 80
    assert clamped["y"] <= 1080 - 80


def test_clamp_restores_onto_secondary_monitor() -> None:
    secondary = Screen(x=1920, y=0, width=1280, height=720)
    state: WindowState = {"width": 900, "height": 600, "x": 2100, "y": 50}
    clamped = clamp_window_state(state, [Screen(), secondary])
    assert clamped["x"] == 2100
    assert clamped["y"] == 50


def test_clamp_shrinks_to_smaller_screen() -> None:
    small = Screen(x=1920, y=0, width=1024, height=600)
    state: WindowState = {"width": 1400, "height": 900, "x": 1920, "y": 0}
    clamped = clamp_window_state(state, [Screen(), small])
    assert clamped["width"] == 1024
    assert clamped["height"] == 600


def test_clamp_enforces_minimum_size() -> None:
    state: WindowState = {"width": 100, "height": 50, "x": 10, "y": 10}
    clamped = clamp_window_state(state, [Screen()])
    assert clamped["width"] == MIN_WINDOW_WIDTH
    assert clamped["height"] == MIN_WINDOW_HEIGHT


def test_clamp_without_screens_drops_position() -> None:
    state: WindowState = {"width": 900, "height": 600, "x": 40, "y": 40, "maximized": True}
    clamped = clamp_window_state(state, [])
    assert clamped["width"] == 900
    assert clamped["maximized"] is True
    assert "x" not in clamped


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    state: WindowState = {"width": 1100, "height": 750, "x": 30, "y": 20, "maximized": False}
    save_window_state(tmp_path, state)
    assert (tmp_path / WINDOW_STATE_FILE).is_file()
    loaded = load_window_state(tmp_path, [Screen()])
    assert loaded == state


def test_load_corrupt_file_falls_back_to_defaults(tmp_path: Path) -> None:
    (tmp_path / WINDOW_STATE_FILE).write_text("{not json", encoding="utf-8")
    loaded = load_window_state(tmp_path, [Screen()])
    assert loaded == default_window_state()


def test_load_missing_file_falls_back_to_defaults(tmp_path: Path) -> None:
    loaded = load_window_state(tmp_path, [Screen()])
    assert loaded == default_window_state()


def test_load_sanity_clamps_stale_geometry(tmp_path: Path) -> None:
    (tmp_path / WINDOW_STATE_FILE).write_text(
        json.dumps({"width": 9999, "height": 100, "x": -9000, "y": 9999}),
        encoding="utf-8",
    )
    loaded = load_window_state(tmp_path, [Screen(width=1920, height=1080)])
    assert MIN_WINDOW_WIDTH <= loaded["width"] <= 1920
    assert MIN_WINDOW_HEIGHT <= loaded["height"] <= 1080
    assert loaded["x"] <= 1920 - 80
    assert loaded["y"] <= 1080 - 80


def test_tracker_rebases_move_events_so_roundtrips_do_not_drift() -> None:
    tracker = WindowGeometryTracker(width=1100, height=700, x=60, y=82)
    tracker.on_moved(70, 154)
    tracker.on_moved(170, 154)
    assert tracker.state["x"] == 160
    assert tracker.state["y"] == 82
    tracker.on_moved(270, 254)
    assert tracker.state["x"] == 260
    assert tracker.state["y"] == 182


def test_tracker_first_move_event_is_the_mapping_not_a_user_move() -> None:
    tracker = WindowGeometryTracker(width=1100, height=700, x=60, y=82)
    tracker.on_moved(70, 154)
    assert tracker.state["x"] == 60
    assert tracker.state["y"] == 82


def test_tracker_ignores_resizes_while_maximized() -> None:
    tracker = WindowGeometryTracker(width=1100, height=700, x=60, y=82)
    tracker.on_maximized()
    tracker.on_resized(1920, 1080)
    tracker.on_moved(0, 0)
    assert tracker.state["width"] == 1100
    assert tracker.state["height"] == 700
    assert tracker.state["maximized"] is True
    tracker.on_restored()
    assert tracker.state["maximized"] is False
    assert tracker.state["width"] == 1100
    assert tracker.state["height"] == 700
