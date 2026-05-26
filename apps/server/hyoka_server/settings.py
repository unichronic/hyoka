from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HYOKA_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./.hyoka/hyoka.db"
    artifact_root: Path = Path("./.hyoka/artifacts")
    artifact_backend: str = "local"
    artifact_s3_bucket: str | None = None
    artifact_s3_prefix: str = "hyoka/artifacts"
    artifact_s3_region: str | None = None
    artifact_s3_endpoint_url: str | None = None
    auto_migrate: bool = False
    inline_worker: bool = False
    worker_lease_seconds: int = 300
    self_improvement_lease_seconds: int = 1800
    worker_max_attempts: int = 3
    require_api_key: bool = False
    api_keys: str = ""
    cors_allow_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    manifest_secret: str = Field(default="local-dev-secret", min_length=8)
    max_request_bytes: int = 10 * 1024 * 1024
    enable_http_replay: bool = False
    http_replay_allowed_hosts: str = ""
    replay_timeout_seconds: float = 30.0
    service_host: str = "0.0.0.0"
    service_port: int = 8686
    log_level: str = "info"

    @property
    def allowed_api_keys(self) -> set[str]:
        return {key.strip() for key in self.api_keys.split(",") if key.strip()}

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def allowed_replay_hosts(self) -> set[str]:
        return {host.strip().lower() for host in self.http_replay_allowed_hosts.split(",") if host.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
