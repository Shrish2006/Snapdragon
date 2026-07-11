"""SQLite-backed `EventStore` adapter — durable event history surviving
process restarts, with zero extra infrastructure (a file on disk, no
separate database service to provision or verify against here).

The approved architecture's storage recommendation for multi-instance
production deployments is Postgres/TimescaleDB; that adapter implements
this same `EventStore` port when that infrastructure is actually
provisioned. This one is the honestly-verifiable step up from
`InMemoryEventStore` available today — appropriate for a single gateway
instance or a small deployment, not for sharing history across replicas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import aiosqlite

from gateway.domain.common.identifiers import HelmetId
from gateway.domain.events.models import EVENT_TYPE_REGISTRY, DomainEvent
from gateway.domain.events.types import EventType

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    helmet_id TEXT,
    occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_helmet_id ON events(helmet_id);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_occurred_at ON events(occurred_at);
"""


class SQLiteEventStore:
    """Implements `application.ports.EventStore` structurally.

    `initialize()` must be awaited once before use (creates the schema if
    absent) — `main.py`'s lifespan does this at startup when this backend
    is selected.
    """

    def __init__(self, path: str) -> None:
        self._path = path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    async def close(self) -> None:
        return None

    async def append(self, event: DomainEvent[Any]) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO events "
                "(event_id, event_type, helmet_id, occurred_at, payload_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    str(event.event_id),
                    event.type.value,
                    event.helmet_id,
                    event.occurred_at.isoformat(),
                    event.model_dump_json(),
                ),
            )
            await db.commit()

    async def query(
        self,
        *,
        helmet_id: HelmetId | None = None,
        event_type: EventType | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[DomainEvent[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if helmet_id is not None:
            clauses.append("helmet_id = ?")
            params.append(helmet_id)
        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type.value)
        if since is not None:
            clauses.append("occurred_at >= ?")
            params.append(since.isoformat())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)

        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(
                f"SELECT event_type, payload_json FROM events {where} "
                f"ORDER BY occurred_at DESC LIMIT ?",
                params,
            )
            rows = await cursor.fetchall()

        return [
            EVENT_TYPE_REGISTRY[EventType(event_type_value)].model_validate_json(payload_json)
            for event_type_value, payload_json in rows
        ]
