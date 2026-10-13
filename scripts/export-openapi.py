import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "openapi.json"


def main() -> None:
    with tempfile.TemporaryDirectory() as data_dir:
        db_path = Path(data_dir) / "study.sqlite3"
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
        command.upgrade(alembic_cfg, "head")
        settings = Settings(
            data_dir=Path(data_dir),
            config_dir=Path(data_dir) / "config",
            spa_dist=Path(data_dir) / "no-spa",
            log_level="WARNING",
            app_env="development",
        )
        app = create_app(settings)
        schema = app.openapi()
    import json

    OUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    schemas = len(schema.get("components", {}).get("schemas", {}))
    paths = len(schema.get("paths", {}))
    print(f"wrote {OUT.relative_to(ROOT)} ({paths} paths, {schemas} schemas)")


if __name__ == "__main__":
    main()
