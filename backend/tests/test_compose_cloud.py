"""Cloud overlay guards: no silent local fallback, no /data tar under cloud."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

COMPOSE = Path(__file__).resolve().parents[2] / "docker"


def _load(name: str) -> dict[str, Any]:
    with (COMPOSE / name).open(encoding="utf-8") as handle:
        return cast(dict[str, Any], yaml.safe_load(handle))


def test_cloud_overlay_requires_profile_and_backend() -> None:
    cloud = _load("docker-compose.cloud.yml")
    app = cloud["services"]["app"]["environment"]
    assert app["SA_CLOUD_PROFILE"].startswith("${SA_CLOUD_PROFILE:?")
    assert app["SA_OBJECT_STORAGE_BACKEND"].startswith("${SA_OBJECT_STORAGE_BACKEND:?")
    assert app["SA_OBJECT_STORAGE_REQUIRED"] == "true"


def test_cloud_overlay_backup_sees_the_object_backend() -> None:
    prod = _load("docker-compose.prod.yml")
    cloud = _load("docker-compose.cloud.yml")
    backup = {
        **prod["services"]["backup"]["environment"],
        **cloud["services"]["backup"]["environment"],
    }
    assert backup["SA_CLOUD_PROFILE"].startswith("${SA_CLOUD_PROFILE:?")
    assert backup["SA_OBJECT_STORAGE_BACKEND"].startswith("${SA_OBJECT_STORAGE_BACKEND:?")
    command = prod["services"]["backup"]["command"]
    guard = 'if [ "$$SA_OBJECT_STORAGE_BACKEND" = "local" ] && [ -z "$$SA_CLOUD_PROFILE" ]'
    assert guard in command
