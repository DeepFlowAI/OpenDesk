import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    DATABASE_URL: str = Field(default="postgresql+asyncpg://localhost:5432/opendesk")
    AUTO_MIGRATE: bool = Field(default=True, description="Run alembic upgrade head on startup")

    REDIS_URL: str | None = Field(default=None)

    # Message Queue
    MESSAGE_QUEUE_PROVIDER: str = Field(default="redis_streams")

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
    JWT_EXPIRE_HOURS: int = Field(default=24)

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
    DEFAULT_ADMIN_PASSWORD: str = Field(default="admin123")

    # Tenant Platform API Key — only used by the closed-source tenants
    # extension (private/extensions/server/tenants). Open-source builds
    # never read it.
    TENANT_API_KEY: str = Field(default="change-me-tenant-api-key")

    # Storage / OSS
    STORAGE_PROVIDER: str = Field(default="aliyun_oss")
    OSS_ACCESS_KEY: str = Field(default="")
    OSS_SECRET_KEY: str = Field(default="")
    OSS_ADDR: str = Field(default="", description="Public access URL prefix, e.g. https://bucket.oss-cn-beijing.aliyuncs.com")
    OSS_URL: str = Field(default="", description="OSS endpoint, e.g. https://oss-cn-beijing.aliyuncs.com")
    OSS_BUCKET: str = Field(default="")

    model_config = SettingsConfigDict(
        env_file=_server_env_file_paths(),
        env_file_encoding="utf-8",
    )


settings = Settings()
