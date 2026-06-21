import logging
import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

ENV = os.getenv("APP_ENV", "dev")

_SERVER_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _SERVER_DIR.parent


def _server_env_file_paths() -> tuple[str, ...]:
    """Load server/.env.{APP_ENV} first, then private/env/server.env.{APP_ENV} (later wins)."""
    cwd_name = f".env.{ENV}"
    local_path = _SERVER_DIR / cwd_name
    private_path = _REPO_ROOT / "private" / "env" / f"server.env.{ENV}"
    paths: list[str] = []
    if local_path.is_file():
        paths.append(str(local_path))
    if private_path.is_file():
        paths.append(str(private_path))
    if not paths:
        paths.append(str(local_path))
    return tuple(paths)


class Settings(BaseSettings):
    APP_NAME: str = Field(default="OpenDesk")
    APP_VERSION: str = Field(default="0.1.0")
    DEBUG: bool = Field(default=False)
    LOG_FORMAT: str = Field(
        default="text",
        description="Log output format: 'text' (human-readable) or 'json' (structured, one JSON object per line)",
    )

    DATABASE_URL: str = Field(default="postgresql+asyncpg://localhost:5432/opendesk")
    AUTO_MIGRATE: bool = Field(default=True, description="Run alembic upgrade head on startup")

    REDIS_URL: str | None = Field(default=None)

    # Message Queue
    MESSAGE_QUEUE_PROVIDER: str = Field(default="redis_streams")

    # OpenAgent integration
    OPEN_AGENT_PROVIDER: str = Field(default="http")

    # Realtime Transport
    REALTIME_PROVIDER: str = Field(default="socketio")
    # Socket.IO heartbeat: server pings every PING_INTERVAL seconds; if no pong
    # within PING_TIMEOUT seconds the connection is dropped. Make sure the
    # reverse proxy idle timeout is greater than (interval + timeout).
    SOCKETIO_PING_INTERVAL: int = Field(default=25)
    SOCKETIO_PING_TIMEOUT: int = Field(default=60)
    # Grace period before a disconnected agent is marked offline. During this
    # window a successful reconnect cancels the pending offline transition.
    AGENT_OFFLINE_GRACE_SECONDS: int = Field(default=30)

    SECRET_KEY: str = Field(default="change-me")
    JWT_ALGORITHM: str = Field(default="HS256")
    # Comma-separated list of browser origins allowed by CORS / Socket.IO,
    # e.g. "https://app.example.com,https://admin.example.com". The default
    # "*" allows any origin (convenient for local/OSS evaluation). Production
    # deployments should set an explicit allowlist; when an explicit list is
    # configured, credentialed (cookie/Authorization) cross-origin requests
    # are permitted, which the "*" wildcard cannot do per the CORS spec.
    CORS_ALLOW_ORIGINS: str = Field(default="*")
    JWT_EXPIRE_HOURS: int = Field(default=24)
    VISITOR_SESSION_EXPIRE_SECONDS: int = Field(default=86400)
    API_CONTEXT_TOKEN_EXPIRE_SECONDS: int = Field(default=1800)
    VISITOR_TIMEOUT_CLOSE_WORKER_ENABLED: bool = Field(default=True)
    VISITOR_TIMEOUT_CLOSE_SCAN_INTERVAL_SECONDS: int = Field(default=60, ge=5)
    VISITOR_TIMEOUT_CLOSE_SCAN_BATCH_SIZE: int = Field(default=100, ge=1, le=500)

    SMTP_HOST: str = Field(default="")
    SMTP_PORT: int = Field(default=465)
    SMTP_USER: str = Field(default="")
    SMTP_PASSWORD: str = Field(default="")
    SMTP_FROM: str = Field(default="")

    VERIFY_CODE_EXPIRE_SECONDS: int = Field(default=600)
    VERIFY_CODE_COOLDOWN_SECONDS: int = Field(default=60)

    # ── Default Tenant (auto-provisioned on first startup) ────────────────
    # On first boot, if the `tenants` table is empty, the seed step creates
    # one tenant + one super-admin employee using the values below.
    # Open-source users log in at `/login` with: tenant=DEFAULT_TENANT_ID,
    # username=DEFAULT_ADMIN_USERNAME, password=DEFAULT_ADMIN_PASSWORD —
    # then change the password immediately.
    # Once any tenant exists, this section is a no-op forever.
    DEFAULT_TENANT_ID: str = Field(default="default")
    DEFAULT_TENANT_NAME: str = Field(default="Default Workspace")
    DEFAULT_ADMIN_USERNAME: str = Field(default="admin")
    DEFAULT_ADMIN_PASSWORD: str = Field(default="Admin123456")

    # Tenant Platform API Key — optional setting consumed by tenant-management
    # extensions registered via the ``app.extensions`` loader. The default
    # single-tenant build does not read this value.
    TENANT_API_KEY: str = Field(default="change-me-tenant-api-key")

    # Storage / OSS
    STORAGE_PROVIDER: str = Field(default="aliyun_oss")

    # ── Telephony / VoIP (call center) ────────────────────────────────────
    # Provider that drives the call-center media plane. "mock" is the safe
    # in-process default for OSS builds — it records RPC calls without
    # touching any external service. Switch to "flowkit" once you have a
    # FlowKit kernel reachable and set TELEPHONY_WS_URL in your env file.
    TELEPHONY_PROVIDER: str = Field(default="mock")
    # WebSocket URL to the FlowKit kernel. MUST be supplied via env when
    # TELEPHONY_PROVIDER=flowkit; we deliberately do not bake in a default
    # so OSS builds never accidentally connect to an upstream address.
    TELEPHONY_WS_URL: str = Field(default="")
    TELEPHONY_SDK_NAME: str = Field(default="opendesk-cc")
    TELEPHONY_SDK_VERSION: str = Field(default="1.0.0")
    TELEPHONY_RPC_TIMEOUT: float = Field(default=30.0)

    # Call center orchestrator startup. Default OFF so OSS deployments without
    # a FlowKit kernel boot cleanly; flip to true once telephony is configured.
    CALL_CENTER_ENABLED: bool = Field(default=False)
    # Tenant slug that owns inbound SIP calls (matched against
    # `tenants.tenant_id`). Empty falls back to DEFAULT_TENANT_ID, then to the
    # first tenant in DB. Multi-tenant deployments should switch to DID-based
    # routing instead.
    CALL_CENTER_DEFAULT_TENANT_SLUG: str = Field(default="")

    # ── FlowKit Telecom Catalog (multi-trunk) ─────────────────────────────
    # Optional: when set, OpenDesk acts as a "Provider" pushing its SipTrunk
    # table to FlowKit's Catalog. When empty, FlowKit falls back to its
    # static `system` Provider (single-trunk env). Multi-trunk deployments
    # MUST set both URL and key. Provider ID identifies this OpenDesk
    # instance to FlowKit and is the {id} in /registrars/{id}/snapshot.
    FLOWKIT_TELECOM_API_URL: str = Field(default="")
    FLOWKIT_TELECOM_API_KEY: str = Field(default="")
    FLOWKIT_TELECOM_PROVIDER_ID: str = Field(default="opendesk")
    # Lease (seconds). Heartbeat interval is lease/3, clamped to [10, 60].
    FLOWKIT_TELECOM_LEASE_SEC: int = Field(default=90)
    # Grace window after lease expiry where inbound stays accepted (covers
    # OpenDesk restarts). 0 = old behavior (instant drop on heartbeat stop).
    FLOWKIT_TELECOM_STALE_ACCEPTABLE_SEC: int = Field(default=30)
    OSS_ACCESS_KEY: str = Field(default="")
    OSS_SECRET_KEY: str = Field(default="")
    OSS_ADDR: str = Field(default="", description="Public access URL prefix, e.g. https://bucket.oss-cn-beijing.aliyuncs.com")
    OSS_URL: str = Field(default="", description="OSS endpoint, e.g. https://oss-cn-beijing.aliyuncs.com")
    OSS_BUCKET: str = Field(default="")

    # ── Observability (vendor-neutral, OTLP/OpenTelemetry-based) ──
    # Backend selector: "otel" → OTLP exporter; "noop" → disabled (zero overhead).
    # Defaults to "noop" so unconfigured environments stay silent.
    OBSERVABILITY_BACKEND: str = Field(default="noop")

    # Service identity (written to every span/log as `resource_attributes`)
    OTEL_SERVICE_NAME: str = Field(default="opendesk-api")
    OTEL_DEPLOYMENT_ENVIRONMENT: str = Field(default="dev")

    # OTLP transport (any OpenTelemetry-compatible backend works here:
    # Grafana Cloud / Tempo, SigNoz, vendor APMs, self-hosted collectors…).
    OTEL_EXPORTER_OTLP_ENDPOINT: str = Field(default="")
    # Comma-separated "k=v,k=v" — typically: Authorization=Basic <base64(user:pass)>
    OTEL_EXPORTER_OTLP_HEADERS: str = Field(default="")

    # ── Vendor-specific extras (GreptimeDB-compatible pipelines etc.) ──
    # Extra header injected on the traces signal so GreptimeDB flattens span attrs.
    OTEL_TRACES_PIPELINE_NAME: str = Field(default="greptime_trace_v1")
    # Extra header injected on the logs signal so GreptimeDB writes to this table.
    OTEL_LOGS_TABLE_NAME: str = Field(default="otel_logs")
    # Master switch for visitor Web SDK event ingest. The endpoint still
    # accepts valid requests when disabled, but skips log emission.
    TELEMETRY_ENABLED: bool = Field(default=True)

    model_config = SettingsConfigDict(
        env_file=_server_env_file_paths(),
        env_file_encoding="utf-8",
    )

    @property
    def cors_origins(self) -> list[str]:
        """Parsed CORS allowlist. ``["*"]`` means allow any origin."""
        raw = self.CORS_ALLOW_ORIGINS.strip()
        if raw == "*" or not raw:
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]


settings = Settings()

# Environments treated as production-like, where booting with an insecure
# default SECRET_KEY is refused. "dev"/"test"/"local" keep the default.
_PRODUCTION_ENVS = {"prod", "production", "staging"}


def assert_safe_production_config() -> None:
    """Refuse to start a production deployment that still uses the default SECRET_KEY.

    ``SECRET_KEY`` signs every JWT, so leaving it at "change-me" in production
    lets tokens be forged. ``DEFAULT_ADMIN_PASSWORD`` is intentionally not
    checked here: it only seeds the first admin when the tenants table is empty
    and is a no-op once any tenant exists, so an already-provisioned deployment
    is unaffected by its value.
    """
    if ENV.lower() not in _PRODUCTION_ENVS:
        return
    if settings.SECRET_KEY == "change-me":
        raise RuntimeError(
            f"Refusing to start in '{ENV}': SECRET_KEY is still the default "
            "'change-me'. Set a strong random SECRET_KEY via environment "
            "variables before deploying."
        )
    if settings.cors_origins == ["*"]:
        logger.warning(
            "Running in '%s' with CORS_ALLOW_ORIGINS='*' (any origin allowed). "
            "Set CORS_ALLOW_ORIGINS to an explicit comma-separated allowlist of "
            "trusted browser origins to reduce CSRF/credential-abuse exposure.",
            ENV,
        )
