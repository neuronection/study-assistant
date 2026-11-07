"""Test-only Settings construction factory (rename-guard port, audit b).

Study's pydantic-settings ``Settings`` uses ``extra="ignore"`` with
``env_prefix="SA_"`` and snake_case fields, so an unknown init kwarg (a
field renamed in ``app/core/config.py``) is silently dropped — the
plan-20 F1 class health hit in plan 23 (``2bf0188``/``d8a887e``): a
rename degraded security assertions into vacuous passes with nothing in
the suite able to notice.

Every test-side construction of :class:`app.core.config.Settings`
flows through this module. Two jobs:

* pin the env-file source explicitly (``_env_file``, the ``d4d0e4a``
  helper's job: pydantic-settings' init-only kwarg is invisible to
  mypy, so the loose call has exactly one named home; ``None`` keeps
  tests hermetic — the checkout's untracked ``.env`` is never read);
* **kwarg-name validation** against ``Settings.model_fields`` — every
  constructor raises ``TypeError`` listing near-miss field names on a
  stale/renamed kwarg, so a rename breaks call sites *loudly* (at
  construction), never silently.

Test-only: never import from app code (one direction only), holds
fixture values only — never a default the app reads.
"""

from __future__ import annotations

import difflib
from collections.abc import Callable
from pathlib import Path

from app.core.config import Settings

# Names this factory accepts as construction kwargs: Settings fields
# plus pydantic-settings' own `_env_file` override. Anything else is a
# rename.
_KNOWN_KWARGS = frozenset(Settings.model_fields) | {"_env_file"}


def validate_field_names(**kwargs: object) -> None:
    """Reject kwargs that are not ``Settings`` fields (rename guard).

    ``Settings(extra="ignore")`` would silently drop them — the exact
    mechanism behind plan 20's vacuous boot-guard tests. Raise TypeError
    with near-miss suggestions instead.
    """
    unknown = [name for name in kwargs if name not in _KNOWN_KWARGS]
    if not unknown:
        return
    parts = []
    for name in unknown:
        near = difflib.get_close_matches(name, Settings.model_fields, n=3, cutoff=0.4)
        hint = ", ".join(repr(n) for n in near) or "(no near miss)"
        parts.append(f"  {name!r} is not a Settings field — did you mean: {hint}")
    raise TypeError(
        "settings_factory: unknown kwarg name(s) — a field was renamed or "
        "misspelled; Settings(extra='ignore') would silently drop these:\n" + "\n".join(parts)
    )


def settings_from_env_file(env_file: Path | str | None, **kwargs: object) -> Settings:
    """Build ``Settings`` with the env-file source pinned explicitly.

    ``Settings.__init__`` is typed from the model's fields only, so
    pydantic-settings' init-only kwargs (``_env_file``) are invisible to
    mypy. Routing the call through an untyped factory alias keeps the
    documented constructor call intact with a single, named point of
    looseness instead of a ``# type: ignore`` per call site. Field
    kwargs (e.g. ``data_dir``) flow through the same point and are
    name-validated (rename guard, audit b).
    """
    validate_field_names(**kwargs)
    factory: Callable[..., Settings] = Settings
    return factory(_env_file=env_file, **kwargs)
