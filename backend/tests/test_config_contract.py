"""Config rename-guard meta-tests (rename-guard port, audit follow-up b).

Study's mirror of health's plan-23 ``test_config_contract.py``
(``2bf0188``/``d8a887e``), adapted to the pydantic-settings prefix
style: health's ``Settings`` reads env through its *field names* (an env
var named like the field), while study reads ``SA_<SUFFIX>`` env names
into snake_case fields — so every name check here goes through the same
translation the product's §16 getter uses
(``name.removeprefix("SA_").lower()``).

Two silent-failure classes these meta-tests make loud:

* **knob no-op (plan-20 B2's exact shape):** a Settings field rename
  turns ``getattr(settings, field, None)`` in ``app.auth.install`` into
  a silent ``None`` — the knob falls back to the kit's ``os.environ``
  read and a deployment ``.env`` value (the reason Settings routing
  exists) dies quietly. (a) resolves EVERY entry of the kit's
  ``AUTH_KNOB_ENV_NAMES`` through the real getter end-to-end;
* **stale env writes (plan-20 F1's mirror image):** a field rename
  leaves the suite setting an env name nothing consumes. (b) checks
  every env name the suite writes against the prefix translation, with
  declared tables for names read outside ``app/core/config.py`` and
  names set only to prove they are inert.

Plus (c) the §16/§8 security-relevant field pins and (d) the factory's
loud-rename behavior (new Settings construction goes through
``tests/settings_factory.py``; the ~40 legacy ``Settings(...)`` call
sites predate it and are converted only as they are touched).

Deliberately **declared tables, not AST magic** (health's rule):
readable, cheap, stable across refactors; renames break the tables
loudly and the tables are greppable when they need to move.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
from nx_auth import AuthConfig
from nx_auth.config import AUTH_KNOB_ENV_NAMES, knob_overrides
from settings_factory import settings_from_env_file

from app.auth.install import _settings_knob
from app.core.config import Settings
from app.main import create_app

TESTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TESTS_DIR.parent
PREFIX = "SA"

# (a) knobs that deliberately have NO Settings field because
# `install_identity` routes a computed value instead. Keyed by the
# kit-side suffix (an entry of AUTH_KNOB_ENV_NAMES).
COMPUTED_KNOBS = {
    "REQUIRE_SHELL_SECRET": (
        "the computed §11 truth (shell_attached: SA_SHELL=1 + desktop "
        "identity) — routing it through Settings would let an env flag arm "
        "a gate no shell can answer; see app/auth/install.py and "
        "test_identity_core.test_env_require_shell_secret_never_arms_the_gate"
    ),
}

# (a) kit knobs with no Settings mirror field — a pinned finding each
# (career's AUTH_PASSWORD_MIN_LENGTH is the cautionary tale this table
# exists for). Study has none today: every non-computed knob resolves,
# and the truthfulness half of the completeness test below makes any
# future declaration prove the knob genuinely fails to resolve.
KNOWN_UNRESOLVED_KNOBS: dict[str, str] = {}

# (b) env names read outside app/core/config.py (declared, greppable):
# name -> reader file(s) whose source must mention the name.
READ_ELSEWHERE = {
    "SA_SHELL": ("app/auth/install.py",),
    "SA_ENV_FILE": ("app/core/config.py",),
    "XDG_DATA_HOME": ("app/core/config.py",),
    "HOME": ("app/core/config.py",),
    "APPDATA": ("app/core/config.py",),
}

# (b) env names set by tests specifically to prove they are IGNORED —
# `SA_REQUIRE_SHELL_SECRET=1` must never arm the §11 gate
# (behaviorally pinned by
# test_identity_core.test_env_require_shell_secret_never_arms_the_gate).
UNREAD_BY_DESIGN = ("SA_REQUIRE_SHELL_SECRET",)

# (c) the §16/§8 security-relevant field pins — a rename fails loudly
# here first (auth_mode/identity_mode are init-only §4 seeds; the TTL /
# lockout knobs are the §16 tunables; session/refresh/data keys are the
# §8 per-purpose pins; the password floor is the §7 policy knob).
GUARD_FIELDS = (
    "session_key",
    "refresh_key",
    "data_key",
    "auth_mode",
    "identity_mode",
    "app_env",
    "trusted_proxy_count",
    "registration_enabled",
    "cookie_secure",
    "auth_access_ttl_minutes",
    "auth_refresh_ttl_days",
    "auth_refresh_absolute_days",
    "auth_lockout_threshold",
    "auth_lockout_minutes",
    "auth_password_min_length",
    "ratelimit_auth",
    "ratelimit_auth_email",
)

# Every knob field, set to a distinctive-but-valid value so absence is
# detectable in the routed kwargs (defaults would be indistinguishable
# from the kit's own fallback). Bounds honor AuthConfig.__post_init__.
_KNOB_FIELD_VALUES = {
    "identity_mode": "desktop",
    "auth_access_ttl_minutes": 45,
    "auth_refresh_ttl_days": 14,
    "auth_refresh_absolute_days": 60,
    "auth_lockout_threshold": 3,
    "auth_lockout_minutes": 30,
    "auth_password_min_length": 16,
    "registration_enabled": False,
    "cookie_secure": True,
    "trusted_proxy_count": 2,
    "ratelimit_auth": 7,
    "ratelimit_auth_email": 11,
}


def _env_field_name(env_name: str) -> str:
    """The Settings field an env name feeds (the §16 getter's rule)."""
    return env_name.removeprefix(f"{PREFIX}_").lower()


def _suite_py_files() -> list[Path]:
    return sorted(
        p
        for p in TESTS_DIR.glob("*.py")
        # test_config_contract.py is the checker (its pattern literals
        # must not scan) and settings_factory.py is the sanctioned
        # construction site.
        if p.name not in {Path(__file__).name, "settings_factory.py"}
    )


def _suite_env_writes() -> dict[str, list[str]]:
    """name -> [file:line] for every env var the suite writes."""
    write_re = re.compile(
        r"""(?:monkeypatch\.setenv\(|os\.environ\.setdefault\(|os\.environ\[)"""
        r"""\s*[\"']([A-Z][A-Z0-9_]{2,})[\"']"""
    )
    found: dict[str, list[str]] = {}
    for path in _suite_py_files():
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            for match in write_re.finditer(line):
                found.setdefault(match.group(1), []).append(f"{path.name}:{lineno}")
    return found


def _knob_kwargs(settings: Settings) -> dict[str, object]:
    """The exact routed dict `install_identity` feeds `from_env`."""
    return knob_overrides(PREFIX, lambda name: _settings_knob(settings, name))


# ---------------------------------------------------------------------------
# (a) knob-map completeness — the highest-value port
# ---------------------------------------------------------------------------


def test_knob_map_resolves_through_settings() -> None:
    """Every kit knob resolves to a REAL Settings field through the
    product getter — a rename degrades to a silent None (B2 class).
    Declared non-resolving knobs must genuinely fail (no rot) so the
    day one is fixed, this test forces its declaration out."""
    settings = settings_from_env_file(None)
    for suffix in AUTH_KNOB_ENV_NAMES:
        env_name = f"{PREFIX}_{suffix}"
        field = _env_field_name(env_name)
        if suffix in COMPUTED_KNOBS:
            assert field not in Settings.model_fields, (
                f"{env_name} is documented as COMPUTED (routed from "
                "shell_attached, never from a Settings field) — if it gained "
                "a field, update app/auth/install.py and COMPUTED_KNOBS "
                "together."
            )
            continue
        if suffix in KNOWN_UNRESOLVED_KNOBS:
            assert field not in Settings.model_fields, (
                f"{env_name} NOW resolves — the pinned finding was fixed; "
                "delete the KNOWN_UNRESOLVED_KNOBS entry."
            )
            assert _settings_knob(settings, env_name) is None
            continue
        assert field in Settings.model_fields, (
            f"§16 knob {env_name} does not resolve: Settings has no "
            f"{field!r} field — `_settings_knob` returns None silently and "
            "the knob falls back to the kit's os.environ read (a .env value "
            "would no-op). Add the mirror field to app/core/config.py or "
            "declare the knob in COMPUTED_KNOBS/KNOWN_UNRESOLVED_KNOBS "
            "with a reason."
        )


def test_every_knob_reaches_auth_config_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings-backed values actually reach `AuthConfig.from_env` for
    every resolvable knob: all `SA_*` knob env vars are cleared so the
    kit's os.environ fallback can mask nothing, every knob field is set
    to a distinctive value, and each one must arrive — a getter that
    silently returned None would drop its key from the routed dict."""
    for suffix in AUTH_KNOB_ENV_NAMES:
        monkeypatch.delenv(f"{PREFIX}_{suffix}", raising=False)

    settings = settings_from_env_file(None, **_KNOB_FIELD_VALUES)
    routed = _knob_kwargs(settings)

    # kit field name <- env suffix translation, mirroring _KNOB_SPECS
    expected = {
        "identity_mode": "desktop",
        "access_ttl_minutes": 45,
        "refresh_ttl_days": 14,
        "refresh_absolute_days": 60,
        "lockout_threshold": 3,
        "lockout_minutes": 30,
        "password_min_length": 16,
        "registration_enabled": False,
        "cookie_secure": True,
        "trusted_proxy_count": 2,
        "auth_rate_per_minute": 7,
        "auth_email_rate_per_minute": 11,
    }
    assert routed == expected, (
        "the §16 routed kwargs drifted — a knob stopped resolving "
        "(silent None) or started carrying a stray value"
    )

    config = AuthConfig.from_env(PREFIX, iss="study", **routed)
    assert config.identity_mode == "desktop", "IDENTITY_MODE rides the map"
    assert config.access_ttl_minutes == 45
    assert config.refresh_ttl_days == 14
    assert config.refresh_absolute_days == 60
    assert config.lockout_threshold == 3
    assert config.lockout_minutes == 30
    assert config.password_min_length == 16
    assert config.registration_enabled is False
    assert config.cookie_secure is True
    assert config.trusted_proxy_count == 2
    assert config.auth_rate_per_minute == 7
    assert config.auth_email_rate_per_minute == 11


def test_require_shell_secret_computed_knob_routes_non_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The special-cased computed knob routes a non-None value through
    the REAL install getter closure: with SA_REQUIRE_SHELL_SECRET
    cleared from the environment, `require_shell_secret=True` can only
    come from the routed `shell_attached` — never the kit default."""
    monkeypatch.setenv("SA_SHELL", "1")
    monkeypatch.delenv("SA_REQUIRE_SHELL_SECRET", raising=False)
    settings = settings_from_env_file(
        None,
        data_dir=tmp_path,
        config_dir=tmp_path / "config",
        spa_dist=tmp_path / "no-spa",
        log_level="WARNING",
        app_env="test",
        identity_mode="desktop",
        shell_secret="test-shell-secret",
    )
    application = create_app(settings)
    assert application.state.auth.config.identity_mode == "desktop"
    assert application.state.auth.config.require_shell_secret is True, (
        "the computed §11 value must route through the knob map (shell attached ⇒ gate armed)"
    )


# ---------------------------------------------------------------------------
# (b) env writes are read by the app (mirror-image rename guard)
# ---------------------------------------------------------------------------


def test_suite_env_writes_are_read_by_the_app() -> None:
    writes = _suite_env_writes()
    assert writes, "the env-write scan found nothing — the regex rotted"
    for name in sorted(writes):
        if name in UNREAD_BY_DESIGN:
            continue
        if name.startswith(f"{PREFIX}_") and _env_field_name(name) in Settings.model_fields:
            continue  # consumed by pydantic-settings (env_prefix translation)
        readers = READ_ELSEWHERE.get(name)
        assert readers, (
            f"the suite writes env {name!r} ({writes[name]}) but it maps to "
            "no Settings field and no READ_ELSEWHERE reader is declared — "
            "the consumer was renamed and the test now sets a dead env var."
        )
        for reader in readers:
            source = (BACKEND_DIR / reader).read_text()
            assert name in source, (
                f"the suite writes env {name!r} ({writes[name]}) but "
                f"{reader} never mentions it — the reader was renamed and "
                "the test now sets a dead env var (plan 20 F1's mirror)."
            )


def test_unread_by_design_names_are_declared() -> None:
    """The inert-name table must stay a small, deliberate list."""
    assert all(name.isupper() for name in UNREAD_BY_DESIGN)
    assert set(UNREAD_BY_DESIGN).isdisjoint(READ_ELSEWHERE)
    # ...and the inertness itself is behaviorally pinned elsewhere:
    assert (
        "test_env_require_shell_secret_never_arms_the_gate"
        in (TESTS_DIR / "test_identity_core.py").read_text()
    ), "the behavioral pin for the inert knob moved — follow it"


def test_computed_and_unresolved_knob_tables_stay_disjoint() -> None:
    """A knob is exactly one of: Settings-backed, computed, or a pinned
    unresolved finding."""
    assert set(COMPUTED_KNOBS).isdisjoint(KNOWN_UNRESOLVED_KNOBS)
    declared = set(COMPUTED_KNOBS) | set(KNOWN_UNRESOLVED_KNOBS)
    assert declared <= set(AUTH_KNOB_ENV_NAMES), (
        "a declared knob is not in the kit's AUTH_KNOB_ENV_NAMES — the "
        "kit renamed it; update the tables (and install.py's closure)"
    )


# ---------------------------------------------------------------------------
# (c) §16/§8 security-relevant field pins
# ---------------------------------------------------------------------------


def test_guard_field_names_exist_and_are_referenced() -> None:
    settings_source = inspect.getsource(Settings)
    for name in GUARD_FIELDS:
        assert name in Settings.model_fields, (
            f"security-relevant field {name!r} vanished from "
            "Settings.model_fields — renamed? The §16/§8 wiring and the "
            "guard tests assert these names; update them and this table "
            "together."
        )
        assert name in settings_source, (
            f"field {name!r} is no longer referenced in the Settings class "
            "body/validators — the knob may now gate on a renamed attribute."
        )


# ---------------------------------------------------------------------------
# (d) the factory makes renames loud at construction time
# ---------------------------------------------------------------------------


def test_factory_rejects_renamed_kwarg_loudly() -> None:
    """A near-miss kwarg raises TypeError naming the suspects — it must
    never reach Settings(extra='ignore') and be silently dropped."""
    with pytest.raises(TypeError) as exc:
        settings_from_env_file(None, auth_lockout_thresholds=3)
    message = str(exc.value)
    assert "auth_lockout_thresholds" in message
    assert "auth_lockout_threshold" in message  # near-miss suggestion
    with pytest.raises(TypeError):
        settings_from_env_file(None, app_envs="test")


def test_factory_knob_fixture_names_are_settings_fields() -> None:
    """The knob-fixture names the factory must accept are real fields —
    a Settings rename fails here with the suspects named (and loudly at
    every construction via the factory's TypeError)."""
    missing = [name for name in _KNOB_FIELD_VALUES if name not in Settings.model_fields]
    assert not missing, (
        f"knob fixture names vanished from Settings.model_fields: {missing} "
        "— a field was renamed; update _KNOB_FIELD_VALUES and the §16 "
        "mirror fields in app/core/config.py together."
    )
