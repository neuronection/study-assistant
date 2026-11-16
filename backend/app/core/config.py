import sys
from functools import lru_cache
from os import environ
from pathlib import Path
from urllib.parse import urlparse

from nx_auth.instance import IdentityMode, parse_identity_mode
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .working_dir import read_override

APP_DIR_NAME = "StudyAssistant"

_DEV_ENVS = ("development", "test", "testing")


def _resolve_env_file() -> str | None:
    """Locate the `.env` file (ADR-0028 §4): explicit `SA_ENV_FILE`, else
    the nearest walk-up hit — but only in dev/test.

    OS environment variables always override file values. The walk-up is
    **disabled outside dev/test** so a baked-in `.env` can never downgrade
    a production boot (health audit rule C-5); production operators point
    `SA_ENV_FILE` at their deployment file explicitly.
    """
    explicit = environ.get("SA_ENV_FILE")
    if explicit:
        return explicit
    if environ.get("SA_APP_ENV") not in _DEV_ENVS:
        return None
    here = Path(__file__).resolve().parent
    for parent in [here, *here.parents]:
        candidate = parent / ".env"
        if candidate.is_file():
            return str(candidate)
    return None


def _platform_base() -> Path:
    if sys.platform == "win32":
        appdata = environ.get("APPDATA")
        return Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    xdg = environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base


def _platform_config_base() -> Path:
    if sys.platform == "win32":
        appdata = environ.get("APPDATA")
        return Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    xdg = environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base


def default_data_dir() -> Path:
    return _platform_base() / APP_DIR_NAME


def default_config_dir() -> Path:
    return _platform_config_base() / APP_DIR_NAME


def resolve_data_dir() -> Path:
    configured = environ.get("SA_CONFIG_DIR")
    config_dir = Path(configured) if configured else default_config_dir()
    override = read_override(config_dir)
    if override is not None:
        return override
    return default_data_dir()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SA_", env_file=_resolve_env_file(), extra="ignore"
    )

    app_name: str = "Study Assistant"
    host: str = "127.0.0.1"
    port: int = 8200
    debug: bool = False
    log_level: str = "INFO"
    # Fail-safe default (family boot policy): without an explicit
    # SA_APP_ENV the app assumes production and enforces the boot guards
    # (nx_auth.boot). Dev scripts set SA_APP_ENV=development.
    app_env: str = "production"
    # Entrypoint half of the §4 matrix (ADR-0028); unknown values fail
    # closed to `server` via the validator below.
    identity_mode: IdentityMode = IdentityMode.SERVER
    # Init-only (§4): consumed by nx_auth.instance.initialize_instance
    # when seeding an empty DB (invalid values fail closed there; empty ⇒
    # the §4 default). After init the DB row is authoritative.
    auth_mode: str = ""
    demo_mode: bool = False
    shell_secret: str | None = None
    cors_origins: str = ""
    fs_roots: str = ""
    # T3 stdio MCP launch allowlist (plan 37 Phase 6.3): comma-separated
    # bare commands. Empty = stdio disabled (fail-closed); health's
    # allowlist is the family reference. No shell, no inline code.
    mcp_stdio_allowed_commands: str = ""
    config_dir: Path = Field(default_factory=default_config_dir)
    data_dir: Path = Field(default_factory=resolve_data_dir)
    spa_dist: Path | None = None
    # The public base URL of THIS deployment (plan 52 web/desktop fix).
    # Desktop/local leaves it unset and OAuth uses a loopback redirect
    # (RFC 8252 — browser and app share a machine). A web/server deployment
    # sets it so the provider redirects to the server's callback route
    # instead of the user's own localhost.
    app_url: str | None = None
    # Public scheme derivation (ADR-0062 v7 §9 / plan 64 §1.6): cookie
    # `Secure` follows the *public* scheme, never a static compose value.
    # `SA_PUBLIC_URL` states the scheme the outside world uses (nginx/certbot
    # TLS or a BYO proxy); `SA_TLS=1` is the explicit override when TLS
    # terminates elsewhere (a cloud LB). An explicit `SA_COOKIE_SECURE`
    # still wins — LAN/VPN operators can force either way.
    public_url: str | None = None
    tls: bool | None = None
    source_scan_interval_sec: int = Field(default=300, ge=15)
    auto_backup: bool = True
    backup_interval_hours: int = Field(default=24, ge=1, le=168)
    backup_keep_daily: int = Field(default=14, ge=1, le=365)
    backup_keep_weekly: int = Field(default=8, ge=0, le=104)
    backup_sync_dir: Path | None = None
    jobs_done_ttl_days: int = Field(default=14, ge=1)
    checkpoint_ttl_days: int = Field(default=14, ge=1)
    # ADR-0022 / deployment.md — web/server runs PostgreSQL 16
    database_url: str | None = None
    db_name: str = "neuronection_study"
    db_user: str | None = None
    db_password: str | None = None
    db_host: str = "localhost"
    db_port: int = 5434

    # --- Family object storage (ADR-0057 / plan 55) --------------------
    # Pydantic loads these from `.env`/OS env with the `SA_` prefix; the
    # storage bootstrap maps the resolved values into the contract (it
    # never reads `os.environ` directly, so `.env` values reach it).
    cloud_profile: str | None = None
    object_storage_backend: str | None = None
    object_storage_required: bool | None = None
    object_storage_local_root: Path | None = None
    object_storage_max_mb: int | None = None
    object_storage_presign_ttl: int | None = None
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_session_token: str | None = None
    s3_path_style: bool | None = None
    s3_sse: str | None = None
    s3_kms_key_id: str | None = None
    s3_prefix: str | None = None
    s3_verify_tls: bool | None = None
    s3_connect_timeout: float | None = None
    s3_read_timeout: float | None = None
    s3_max_attempts: int | None = None
    azure_storage_container: str | None = None
    azure_storage_connection_string: str | None = None
    azure_storage_account_url: str | None = None
    azure_storage_account_name: str | None = None
    azure_storage_credential: str | None = None
    azure_storage_prefix: str | None = None
    azure_connect_timeout: float | None = None
    azure_read_timeout: float | None = None
    azure_max_attempts: int | None = None

    # --- §16 auth knobs (ADR-0028) -------------------------------------
    # Routed into the auth-kit config via nx_auth.config.knob_overrides
    # so `.env`-file values reach the kit exactly like OS-environment
    # ones (OS env wins per key). Field names mirror the kit's `<SA_>…`
    # env suffixes verbatim.
    auth_access_ttl_minutes: int = 60
    auth_refresh_ttl_days: int = 7
    auth_refresh_absolute_days: int = 30
    auth_lockout_threshold: int = 5
    auth_lockout_minutes: int = 15
    auth_password_min_length: int = 10
    registration_enabled: bool = True
    # None = derive from the public scheme (`effective_cookie_secure`);
    # an explicit `SA_COOKIE_SECURE` wins over every derivation.
    cookie_secure: bool | None = None
    trusted_proxy_count: int = 0
    # §16 rate-limit ceilings (plan 21: the kit's family limiter; units
    # are requests per minute, 0 disables a bucket, ENABLED stops all).
    # AUTH/AUTH_EMAIL also feed the kit's auth limiters (§7).
    ratelimit_enabled: bool = True
    ratelimit_auth: int = 10
    ratelimit_auth_email: int = 30
    ratelimit_ai: int = 30
    ratelimit_mcp: int = 120
    ratelimit_default: int = 240

    # --- §8 key pins (optional — generated 0600 auth_keys.json when
    # unset; all three or none, resolved through KeyRing.load_for).
    session_key: str | None = None
    refresh_key: str | None = None
    data_key: str | None = None
    # Prior DATA_KEY values (comma-separated, decryption-only) for
    # non-disruptive at-rest key rotation — see docs/dev/security.md
    # "Rotating the at-rest key". New writes always seal under data_key.
    data_key_previous: str | None = None

    @field_validator("identity_mode", mode="before")
    @classmethod
    def _fail_closed_identity_mode(cls, value: object) -> IdentityMode:
        """Unknown entrypoint values fail closed to `server` (§4)."""
        return parse_identity_mode(None if value is None else str(value))

    @field_validator(
        "public_url",
        "tls",
        "cookie_secure",
        "cloud_profile",
        "object_storage_backend",
        "object_storage_required",
        "object_storage_local_root",
        "object_storage_max_mb",
        "object_storage_presign_ttl",
        "s3_bucket",
        "s3_region",
        "s3_endpoint_url",
        "s3_access_key_id",
        "s3_secret_access_key",
        "s3_session_token",
        "s3_path_style",
        "s3_sse",
        "s3_kms_key_id",
        "s3_prefix",
        "s3_verify_tls",
        "s3_connect_timeout",
        "s3_read_timeout",
        "s3_max_attempts",
        "azure_storage_container",
        "azure_storage_connection_string",
        "azure_storage_account_url",
        "azure_storage_account_name",
        "azure_storage_credential",
        "azure_storage_prefix",
        "azure_connect_timeout",
        "azure_read_timeout",
        "azure_max_attempts",
        mode="before",
    )
    @classmethod
    def _empty_storage_values_are_unset(cls, value: object) -> object:
        """Compose passes ``${VAR:-}`` as an empty string; treat it as unset."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def effective_cookie_secure(self) -> bool:
        """Cookie `Secure`, derived from the public scheme (plan 64 §1.6).

        Priority: an explicit `SA_COOKIE_SECURE`, then `SA_TLS`, then the
        scheme of `SA_PUBLIC_URL` (falling back to `SA_APP_URL`), else
        False. HTTP (LAN/VPN) logins keep working: derivation never forces
        `Secure` on without a public https:// or explicit TLS flag.
        """
        if self.cookie_secure is not None:
            return self.cookie_secure
        if self.tls is not None:
            return self.tls
        for raw in (self.public_url, self.app_url):
            if not raw:
                continue
            scheme = urlparse(raw.strip()).scheme.lower()
            if scheme in ("https", "wss"):
                return True
            if scheme == "http":
                return False
        return False

    @property
    def db_path(self) -> Path:
        return self.data_dir / "study.sqlite3"

    @property
    def checkpoints_path(self) -> Path:
        return self.data_dir / "checkpoints.sqlite3"

    @property
    def db_url(self) -> str:
        """SQLAlchemy URL (deployment.md): `SA_DATABASE_URL` wins, then
        `SA_DB_*` credentials, else desktop/test SQLite."""
        if self.database_url:
            return self.database_url
        if self.db_user and self.db_password:
            return (
                f"postgresql+psycopg://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        return f"sqlite:///{self.db_path}"

    @property
    def is_production(self) -> bool:
        """True when running with APP_ENV=production (boot guards apply)."""
        return self.app_env == "production"

    @property
    def is_dev(self) -> bool:
        """True in development/test environments."""
        return self.app_env in ("development", "test", "testing")

    @property
    def inbox_dir(self) -> Path:
        return self.data_dir / "import-inbox"

    @property
    def blobs_dir(self) -> Path:
        return self.data_dir / "blobs"

    @property
    def granted_fs_roots(self) -> tuple[Path, ...]:
        roots = {Path.home().resolve(), self.data_dir.resolve()}
        for raw in self.fs_roots.split(","):
            candidate = raw.strip()
            if candidate:
                roots.add(Path(candidate).expanduser().resolve())
        return tuple(sorted(roots, key=lambda item: len(item.parts), reverse=True))

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
