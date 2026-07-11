"""Tests for `GET /health` and `GET /ready`."""

from __future__ import annotations

import dataclasses

import fakeredis.aioredis
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from gateway.config import Settings, settings_for_tests
from gateway.infrastructure.bus.redis_streams import RedisStreamsEventBus
from gateway.main import create_app


def test_health_is_always_ok_even_before_lifespan_runs() -> None:
    client = TestClient(create_app(Settings(_env_file=None)))  # no "with" — no lifespan
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_is_503_before_the_lifespan_has_started_background_tasks() -> None:
    client = TestClient(create_app(Settings(_env_file=None)))  # no "with" — no lifespan
    response = client.get("/ready")
    assert response.status_code == 503


def test_ready_is_ok_once_the_lifespan_has_run() -> None:
    with TestClient(create_app(settings_for_tests())) as client:
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_ready_is_503_when_the_redis_backend_is_unreachable() -> None:
    app = create_app(settings_for_tests())
    # Swap in a Redis event bus pointed at a port nothing is listening on —
    # `/ready` must reflect that without the app having ever connected.
    app.state.container = dataclasses.replace(
        app.state.container,
        event_bus=RedisStreamsEventBus(
            redis=Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2, socket_timeout=0.2)
        ),
    )
    with TestClient(app) as client:
        response = client.get("/ready")
        assert response.status_code == 503


def test_ready_is_ok_when_the_redis_backend_is_reachable() -> None:
    app = create_app(settings_for_tests())
    app.state.container = dataclasses.replace(
        app.state.container,
        event_bus=RedisStreamsEventBus(redis=fakeredis.aioredis.FakeRedis()),
    )
    with TestClient(app) as client:
        response = client.get("/ready")
        assert response.status_code == 200
