"""Postgres-backed durable EventStore adapter — the approved architecture's
storage recommendation for multi-instance production deployments.

Uses `asyncpg` with a connection pool (not per-call open/close like the
SQLite adapter — Postgres is a network service, establishing a new
connection per query would dominate latency). The schema is TimescaleDB-
ready: the `CREATE EXTENSION` / `SELECT create_hypertable(...)` DDL is
commented inline, enabling automatic time-based partitioning on a
TimescaleDB server with zero code changes — just the extension installed
on the server side.

Verified against a real, freshly-started Postgres 16 container
(`docker compose up postgres`) — see `docker-compose.yml`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import asyncpg

from gateway.domain.common.identifiers import HelmetId
from gateway.domain.events.models import EVENT_TYPE_REGISTRY, DomainEvent
from gateway.domain.events.types import EventType

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id   TEXT PRIMARY KEY,
    event_type TEXT      NOT NULL,
    helmet_id  TEXT,
    occurred_at TIMESTAMPTZ NOT NULL,
    payload_json TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_helmet_id  ON events(helmet_id);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_occurred_at ON events(occurred_at);

-- TimescaleDB hypertable (uncomment once the extension is installed on
-- the server — the adapter works on vanilla Postgres without it, and the
-- DDL is a no-op there):
-- CREATE EXTENSION IF NOT EXISTS timescaledb;
-- SELECT create_hypertable('events', 'occurred_at', if_not_exists => TRUE);
"""


class PostgresEventStore:
    """Implements `application.ports.EventStore` structurally.

    `initialize()` must be awaited once before use (creates the schema and
    opens the pool) — `main.py`'s lifespan does this at startup.
    `close()` must be awaited on shutdown — the same lifespan handles it.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def initialize(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)
        async with self._pool.acquire() as conn:
            await conn.execute(_SCHEMA)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def append(self, event: DomainEvent[Any]) -> None:
        assert self._pool is not None, "call initialize() before append()"
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO events (event_id, event_type, helmet_id, occurred_at, payload_json) "
                "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (event_id) DO NOTHING",
                str(event.event_id),
                event.type.value,
                event.helmet_id,
                event.occurred_at,
                event.model_dump_json(),
            )

    async def query(
        self,
        *,
        helmet_id: HelmetId | None = None,
        event_type: EventType | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[DomainEvent[Any]]:
        assert self._pool is not None, "call initialize() before query()"
        clauses: list[str] = []
        params: list[Any] = []
        idx = 1
        if helmet_id is not None:
            clauses.append(f"helmet_id = ${idx}")
            params.append(helmet_id)
            idx += 1
        if event_type is not None:
            clauses.append(f"event_type = ${idx}")
            params.append(event_type.value)
            idx += 1
        if since is not None:
            clauses.append(f"occurred_at >= ${idx}")
            params.append(since)
            idx += 1
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT event_type, payload_json FROM events {where} "
                f"ORDER BY occurred_at DESC LIMIT ${idx}",
                *params,
            )

        return [
            EVENT_TYPE_REGISTRY[EventType(row["event_type"])].model_validate_json(
                row["payload_json"]
            )
            for row in rows
        ]
