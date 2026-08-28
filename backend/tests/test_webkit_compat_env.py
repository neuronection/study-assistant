import sys
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

import app.shell as shell
from app.shell import _plan_fallback, _relaunch_argv, _watch_renderer, apply_webkit_compat_env


def test_compat_env_software_when_probe_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shell, "_egl_probe", lambda: False)
    env = apply_webkit_compat_env({})
    assert env["WEBKIT_DISABLE_DMABUF_RENDERER"] == "1"
    assert env["WEBKIT_DISABLE_COMPOSITING_MODE"] == "1"


def test_compat_env_gpu_when_probe_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shell, "_egl_probe", lambda: True)
    env = apply_webkit_compat_env({})
    assert "WEBKIT_DISABLE_DMABUF_RENDERER" not in env
    assert "WEBKIT_DISABLE_COMPOSITING_MODE" not in env


def test_compat_env_gpu_forced_overrides_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shell, "_egl_probe", lambda: False)
    env = apply_webkit_compat_env({"SA_WEBKIT_GPU": "1"})
    assert "WEBKIT_DISABLE_DMABUF_RENDERER" not in env


def test_compat_env_soft_fallback_marker_forces_software(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shell, "_egl_probe", lambda: True)
    env = apply_webkit_compat_env({"SA_WEBKIT_SOFT_FALLBACK": "1"})
    assert env["WEBKIT_DISABLE_DMABUF_RENDERER"] == "1"


def test_compat_env_skips_probe_off_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(shell, "_egl_probe", lambda: False)
    env = apply_webkit_compat_env({})
    assert "WEBKIT_DISABLE_DMABUF_RENDERER" not in env


def test_relaunch_argv_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/usr/lib/studyassistant/studyassistant")
    monkeypatch.setattr(sys, "argv", ["/usr/lib/studyassistant/studyassistant"])
    assert _relaunch_argv("app") == ["/usr/lib/studyassistant/studyassistant", "app"]


def test_relaunch_argv_dev_replaces_mode_keeps_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    monkeypatch.setattr(
        sys, "argv", ["backend/studyassistant/__main__.py", "web", "--flag"]
    )
    assert _relaunch_argv("app") == [
        "/usr/bin/python3",
        "-m",
        "studyassistant",
        "--flag",
        "app",
    ]


def test_plan_fallback_first_step_software() -> None:
    env: dict[str, str] = {}
    mode, event = _plan_fallback(env)
    assert mode == "app"
    assert event == "webkit_renderer_dead_relaunching_software"
    assert env["SA_WEBKIT_SOFT_FALLBACK"] == "1"


def test_plan_fallback_second_step_browser() -> None:
    env = {"SA_WEBKIT_SOFT_FALLBACK": "1"}
    mode, event = _plan_fallback(env)
    assert mode == "web"
    assert event == "webkit_still_dead_relaunching_browser_mode"
    assert env["SA_WEBKIT_BROWSER_FALLBACK"] == "1"


def _app_with_state(**attrs: object) -> FastAPI:
    app = FastAPI()
    for key, value in attrs.items():
        setattr(app.state, key, value)
    return app


def test_watch_renderer_relaunches_when_page_never_loads() -> None:
    app = _app_with_state()
    fired: list[bool] = []
    _watch_renderer(app, threading.Event(), 0.3, lambda: fired.append(True))
    assert fired == [True]


def test_watch_renderer_quiet_when_page_loaded() -> None:
    app = _app_with_state(spa_rendered=True)
    fired: list[bool] = []
    _watch_renderer(app, threading.Event(), 0.3, lambda: fired.append(True))
    assert fired == []


def test_watch_renderer_cancelled() -> None:
    app = _app_with_state()
    cancel = threading.Event()
    cancel.set()
    fired: list[bool] = []
    _watch_renderer(app, cancel, 0.3, lambda: fired.append(True))
    assert fired == []


def test_watch_renderer_no_relaunch_loop_after_success() -> None:
    app = _app_with_state()
    marker = SimpleNamespace(relaunched=False)

    def relaunch() -> None:
        marker.relaunched = True

    thread = threading.Thread(
        target=_watch_renderer, args=(app, threading.Event(), 0.5, relaunch)
    )
    thread.start()
    time.sleep(0.1)
    app.state.spa_rendered = True
    thread.join()
    assert marker.relaunched is False
