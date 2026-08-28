import sys
from functools import lru_cache
from os import environ
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR_NAME = "StudyAssistant"
LEGACY_APP_DIR_NAME = "CourseAssistant"


def _platform_base() -> Path:
    if sys.platform == "win32":
        appdata = environ.get("APPDATA")
        return Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    xdg = environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base


def default_data_dir() -> Path:
    data_dir = _platform_base() / APP_DIR_NAME
    legacy = data_dir.with_name(LEGACY_APP_DIR_NAME)
    if legacy.is_dir() and not data_dir.exists():
        legacy.rename(data_dir)
    return data_dir


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SA_", env_file=".env")

    app_name: str = "Study Assistant"
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False
    log_level: str = "INFO"
    data_dir: Path = Field(default_factory=default_data_dir)
    spa_dist: Path | None = None
    source_scan_interval_sec: int = Field(default=300, ge=15)
    auto_backup: bool = True
    backup_interval_hours: int = Field(default=24, ge=1, le=168)
    backup_keep_daily: int = Field(default=14, ge=1, le=365)
    backup_keep_weekly: int = Field(default=8, ge=0, le=104)
    backup_sync_dir: Path | None = None
    jobs_done_ttl_days: int = Field(default=14, ge=1)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def inbox_dir(self) -> Path:
        return self.data_dir / "import-inbox"

    @property
    def blobs_dir(self) -> Path:
        return self.data_dir / "blobs"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def thumbnails_dir(self) -> Path:
        return self.data_dir / "thumbnails"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    def ensure_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.blobs_dir,
            self.cache_dir,
            self.thumbnails_dir,
            self.backups_dir,
            self.inbox_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
