from app.shell import apply_webkit_compat_env


def test_webkit_compat_env_set_by_default() -> None:
    env = apply_webkit_compat_env({})
    assert env["WEBKIT_DISABLE_DMABUF_RENDERER"] == "1"
    assert env["WEBKIT_DISABLE_COMPOSITING_MODE"] == "1"


def test_webkit_compat_env_gpu_opt_in() -> None:
    env = apply_webkit_compat_env({"SA_WEBKIT_GPU": "1"})
    assert "WEBKIT_DISABLE_DMABUF_RENDERER" not in env
    assert "WEBKIT_DISABLE_COMPOSITING_MODE" not in env
