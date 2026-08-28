import json
import os
import socket
import threading
import webbrowser
from collections.abc import MutableMapping, Sequence
from pathlib import Path
from typing import Any, TypedDict

import uvicorn
import webview

from .core.config import get_settings
from .main import create_app

_SNAP_POLLUTED_VARS = (
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "GDK_BACKEND",
    "GIO_MODULE_DIR",
    "GSETTINGS_SCHEMA_DIR",
    "XDG_DATA_HOME",
    "XDG_CONFIG_DIRS",
    "XDG_CACHE_HOME",
)


def sanitize_environment(
    environ: MutableMapping[str, str] | None = None,
) -> MutableMapping[str, str]:
    env: MutableMapping[str, str] = os.environ if environ is None else environ

    def get(name: str) -> str | None:
        return env.get(name)

    def put(name: str, value: str) -> None:
        env[name] = value

    def drop(name: str) -> None:
        env.pop(name, None)

    for name in _SNAP_POLLUTED_VARS:
        original = get(f"{name}_VSCODE_SNAP_ORIG")
        if original is not None:
            if original:
                put(name, original)
            else:
                drop(name)
            continue
        value = get(name)
        if not value:
            continue
        if name in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
            kept = [e for e in value.split(":") if e and "/snap/" not in e]
            if kept:
                put(name, ":".join(kept))
            else:
                drop(name)
        elif "/snap/" in value:
            drop(name)
    return env


def find_free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class WindowState(TypedDict, total=False):
    width: int
    height: int
    x: int
    y: int
    maximized: bool


WINDOW_STATE_FILE = "window-state.json"
DEFAULT_WINDOW_WIDTH = 1280
DEFAULT_WINDOW_HEIGHT = 800
MIN_WINDOW_WIDTH = 640
MIN_WINDOW_HEIGHT = 480
VISIBLE_MARGIN = 80


def default_window_state() -> WindowState:
    return {"width": DEFAULT_WINDOW_WIDTH, "height": DEFAULT_WINDOW_HEIGHT}


def _screen_for(x: int, y: int, screens: Sequence[Any]) -> Any | None:
    for screen in screens:
        if (
            screen.x <= x < screen.x + screen.width
            and screen.y <= y < screen.y + screen.height
        ):
            return screen
    return None


def clamp_window_state(state: WindowState, screens: Sequence[Any]) -> WindowState:
    width = state.get("width", DEFAULT_WINDOW_WIDTH)
    height = state.get("height", DEFAULT_WINDOW_HEIGHT)
    clamped: WindowState = {"width": width, "height": height}
    if "maximized" in state:
        clamped["maximized"] = bool(state["maximized"])
    if not screens:
        return clamped

    primary = screens[0]
    screen = primary
    if "x" in state and "y" in state:
        screen = _screen_for(int(state["x"]), int(state["y"]), screens) or primary
    width = max(MIN_WINDOW_WIDTH, min(width, screen.width))
    height = max(MIN_WINDOW_HEIGHT, min(height, screen.height))
    clamped["width"] = width
    clamped["height"] = height

    if "x" in state and "y" in state:
        left_limit = screen.x - width + VISIBLE_MARGIN
        right_limit = screen.x + screen.width - VISIBLE_MARGIN
        x = max(left_limit, min(int(state["x"]), right_limit))
        y = max(screen.y, min(int(state["y"]), screen.y + screen.height - VISIBLE_MARGIN))
        clamped["x"] = x
        clamped["y"] = y
    else:
        clamped["x"] = screen.x + (screen.width - width) // 2
        clamped["y"] = screen.y + (screen.height - height) // 2
    return clamped


class WindowGeometryTracker:
    def __init__(
        self,
        width: int,
        height: int,
        x: int,
        y: int,
        maximized: bool = False,
    ) -> None:
        self._placed = (x, y)
        self._base: tuple[int, int] | None = None
        self._pre_maximize: tuple[int, int] | None = None
        self.state: WindowState = {
            "width": width,
            "height": height,
            "x": x,
            "y": y,
            "maximized": maximized,
        }

    def on_moved(self, x: int, y: int) -> None:
        if self.state.get("maximized"):
            return
        if self._base is None:
            self._base = (x, y)
            return
        self.state["x"] = self._placed[0] + x - self._base[0]
        self.state["y"] = self._placed[1] + y - self._base[1]

    def on_resized(self, width: int, height: int) -> None:
        if self.state.get("maximized"):
            return
        self.state["width"] = width
        self.state["height"] = height

    def on_maximized(self) -> None:
        self._pre_maximize = (self.state["width"], self.state["height"])
        self.state["maximized"] = True

    def on_restored(self) -> None:
        self.state["maximized"] = False
        if self._pre_maximize is not None:
            self.state["width"], self.state["height"] = self._pre_maximize


def _window_state_path(data_dir: Path) -> Path:
    return data_dir / WINDOW_STATE_FILE


def load_window_state(data_dir: Path, screens: Sequence[Any]) -> WindowState:
    path = _window_state_path(data_dir)
    state: WindowState = default_window_state()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            state = {
                "width": int(raw.get("width", DEFAULT_WINDOW_WIDTH)),
                "height": int(raw.get("height", DEFAULT_WINDOW_HEIGHT)),
            }
            if isinstance(raw.get("x"), int) and isinstance(raw.get("y"), int):
                state["x"] = raw["x"]
                state["y"] = raw["y"]
            if isinstance(raw.get("maximized"), bool):
                state["maximized"] = raw["maximized"]
    except (OSError, ValueError, TypeError):
        return default_window_state()
    return clamp_window_state(state, screens)


def save_window_state(data_dir: Path, state: WindowState) -> None:
    path = _window_state_path(data_dir)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(dict(state)), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass
def run_browser() -> None:
    settings = get_settings()
    app = create_app(settings)
    url = f"http://{settings.host}:{settings.port}"
    threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(
        app, host=settings.host, port=settings.port, log_level=settings.log_level.lower()
    )


def apply_webkit_compat_env(
    environ: MutableMapping[str, str] | None = None,
) -> MutableMapping[str, str]:
    env: MutableMapping[str, str] = os.environ if environ is None else environ
    if env.get("SA_WEBKIT_GPU") != "1":
        env["WEBKIT_DISABLE_DMABUF_RENDERER"] = "1"
        env["WEBKIT_DISABLE_COMPOSITING_MODE"] = "1"
    return env


def run() -> None:
    sanitize_environment()
    apply_webkit_compat_env()
    settings = get_settings()
    app = create_app(settings)
    port = find_free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host=settings.host, port=port, log_level=settings.log_level.lower())
    )
    thread = threading.Thread(target=server.run, name="uvicorn", daemon=True)
    thread.start()
    state = load_window_state(settings.data_dir, webview.screens)
    created = webview.create_window(
        settings.app_name,
        f"http://{settings.host}:{port}",
        width=state["width"],
        height=state["height"],
        x=state.get("x"),
        y=state.get("y"),
        maximized=state.get("maximized", False),
    )
    if created is None:
        raise RuntimeError("webview window creation failed")
    window = created
    tracker = WindowGeometryTracker(
        width=state["width"],
        height=state["height"],
        x=state.get("x", 0),
        y=state.get("y", 0),
        maximized=state.get("maximized", False),
    )
    window.events.moved += tracker.on_moved
    window.events.resized += tracker.on_resized
    window.events.maximized += tracker.on_maximized
    window.events.restored += tracker.on_restored

    def persist_window_state() -> None:
        save_window_state(settings.data_dir, tracker.state)

    window.events.closed += persist_window_state
    webview.start(private_mode=False, debug=settings.debug)
    server.should_exit = True
    thread.join(timeout=5)
