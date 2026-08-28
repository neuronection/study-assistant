from app.shell import sanitize_environment


def make_env() -> dict[str, str]:
    return {
        "LD_LIBRARY_PATH": "/snap/core20/current/lib/x86_64-linux-gnu:/opt/rocm-7.1.1/lib:",
        "LD_PRELOAD": "/snap/core20/current/lib/x86_64-linux-gnu/libpthread.so.0",
        "GSETTINGS_SCHEMA_DIR": "/home/ilias/snap/code/257/.local/share/glib-2.0/schemas",
        "XDG_DATA_HOME": "/home/ilias/snap/code/257/.local/share",
        "GDK_BACKEND": "wayland",
    }


def test_snap_paths_stripped_from_library_path() -> None:
    env = make_env()
    sanitize_environment(env)
    assert env["LD_LIBRARY_PATH"] == "/opt/rocm-7.1.1/lib"


def test_fully_polluted_vars_dropped() -> None:
    env = make_env()
    sanitize_environment(env)
    assert "LD_PRELOAD" not in env
    assert "GSETTINGS_SCHEMA_DIR" not in env
    assert "XDG_DATA_HOME" not in env


def test_unpolluted_values_kept() -> None:
    env = make_env()
    sanitize_environment(env)
    assert env["GDK_BACKEND"] == "wayland"


def test_vscode_snap_orig_restores_original() -> None:
    env = make_env()
    env["XDG_DATA_HOME_VSCODE_SNAP_ORIG"] = ""
    env["GDK_BACKEND_VSCODE_SNAP_ORIG"] = "x11"
    sanitize_environment(env)
    assert "XDG_DATA_HOME" not in env
    assert env["GDK_BACKEND"] == "x11"


def test_empty_library_path_removed() -> None:
    env = {"LD_LIBRARY_PATH": "/snap/core20/current/lib:"}
    sanitize_environment(env)
    assert "LD_LIBRARY_PATH" not in env


def test_clean_environment_untouched() -> None:
    env = {"PATH": "/usr/bin", "HOME": "/home/ilias"}
    sanitize_environment(env)
    assert env == {"PATH": "/usr/bin", "HOME": "/home/ilias"}
