"""Typed, environment-driven configuration.

Field names are matched case-insensitively against environment variables by
`pydantic-settings`, so the existing operational contract already baked into
`docker-compose.yml`, `k8s/configmap.yaml` and `gateway/Dockerfile`
(`LOG_LEVEL`, `LOG_FILE_PATH`, `PPE_URL`, `FALL_URL`, `EVENT_BUFFER`) keeps
working unchanged — this is a drop-in replacement, no deployment manifest
edits required for those five variables.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide configuration, parsed once from the environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # -- logging (wired in Phase 6) ------------------------------------
    log_level: str = "INFO"
    log_file_path: str = ""

    # -- upstream ML services (Phase 3) --------------------------------
    ppe_url: str = "http://ppe-detection:8000"
    fall_url: str = "http://fall-detection:8000"

    # -- mock ML services (light dev mode) ----------------------------
    mock_ml: bool = False
    """When `True`, the gateway uses in-process mock clients instead of
    calling real ML services. Set `MOCK_ML=true` for light dev mode
    that skips the CPU-heavy ppe-detection and fall-detection containers."""

    # -- event history hot-buffer size, used by `InMemoryEventStore`
    #    (kept as the same name/default the old gateway's in-memory
    #    deque used) --------------------------------------------------
    event_buffer: int = Field(default=200, ge=1)

    # -- telemetry validation (Phase 1: domain.telemetry.validation) ----
    telemetry_max_clock_skew_seconds: float = Field(default=30.0, gt=0)

    # -- event bus (Phase 4) --------------------------------------------
    event_bus_backend: Literal["memory", "redis"] = "redis"
    redis_url: str = "redis://redis:6379/0"
    """Only read when `event_bus_backend == "redis"`."""

    # -- event persistence (Phase 4) -------------------------------------
    event_store_backend: Literal["memory", "sqlite", "postgres"] = "postgres"
    postgres_dsn: str = "postgresql://safeguard:safeguard@postgres:5432/safeguard"
    """Only read when `event_store_backend == "postgres"`."""
    sqlite_path: str = "./data/events.db"
    """Only read when `event_store_backend == "sqlite"`."""

    # -- MQTT transport (optional — disabled when mqtt_broker_host is empty) --
    mqtt_broker_host: str = ""
    """Hostname or IP of the MQTT broker.  Empty string disables the MQTT
    ingestion and presence adapters — the gateway runs HTTP-only.
    Set to the broker service name (e.g. 'mosquitto') to enable."""
    mqtt_broker_port: int = Field(default=1883, ge=1, le=65535)
    mqtt_username: str = "gateway"
    mqtt_password: str = ""
    mqtt_topic_prefix: str = "safeguard"


def settings_for_tests(**overrides) -> Settings:
    """Zero-infrastructure settings for tests — `memory` backends
    (no Redis server, no Postgres server needed), with any field
    overridable by keyword argument so individual tests can pin a
    specific backend their assertions depend on."""
    return Settings(
        _env_file=None,
        event_bus_backend="memory",
        event_store_backend="memory",
        **overrides,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
