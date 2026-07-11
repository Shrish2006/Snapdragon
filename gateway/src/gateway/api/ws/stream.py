"""WebSocket streaming — `GET /v1/ws`, the single endpoint dashboard
clients connect to for real-time updates.

Mirrors the old gateway's `WS /ws` (connect, receive every event) but
adds server-side filtering (a client can send `SubscribeMessage` any time)
instead of broadcasting everything to everyone, and per-connection
backpressure via `SubscriptionManager`'s bounded queues instead of a
blocking `await ws.send_json` loop over every subscriber (the old
gateway's `_broadcast`, which stalled the whole broadcast on one slow
client).

Two concurrent tasks per connection — a reader (client -> filter updates)
and a writer (queue -> client, with a heartbeat fallback) — so a slow or
silent client on one direction never blocks the other.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from gateway.api.ws.deps import DeviceRegistryWSDep, SubscriptionManagerDep
from gateway.api.ws.protocol import (
    ErrorMessage,
    EventMessage,
    HeartbeatMessage,
    SnapshotMessage,
    SubscribeMessage,
)
from gateway.application.subscription_service import Subscriber, SubscriptionManager
from gateway.infrastructure.metrics.registry import ws_connections

logger = logging.getLogger("gateway.access")

router = APIRouter()

_HEARTBEAT_INTERVAL_SECONDS = 20.0


@router.websocket("/v1/ws")
async def stream(
    websocket: WebSocket,
    manager: SubscriptionManagerDep,
    registry: DeviceRegistryWSDep,
) -> None:
    await websocket.accept()
    subscriber = await manager.register()
    ws_connections.inc()
    logger.info("ws connect subscriber_id=%s", subscriber.id)
    try:
        helmets = await registry.list_all()
        await websocket.send_json(SnapshotMessage.from_helmets(helmets).model_dump(mode="json"))

        reader = asyncio.create_task(_read_client_messages(websocket, manager, subscriber.id))
        writer = asyncio.create_task(_write_events(websocket, subscriber))
        _done, pending = await asyncio.wait({reader, writer}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
    finally:
        await manager.unregister(subscriber.id)
        ws_connections.dec()
        logger.info("ws disconnect subscriber_id=%s", subscriber.id)


async def _read_client_messages(
    websocket: WebSocket, manager: SubscriptionManager, subscriber_id: str
) -> None:
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = SubscribeMessage.model_validate_json(raw)
            except ValueError as exc:
                await websocket.send_json(ErrorMessage(detail=str(exc)).model_dump(mode="json"))
                continue
            await manager.update_filter(subscriber_id, message.filter)
    except WebSocketDisconnect:
        pass


async def _write_events(websocket: WebSocket, subscriber: Subscriber) -> None:
    try:
        while True:
            try:
                event = await asyncio.wait_for(
                    subscriber.queue.get(), timeout=_HEARTBEAT_INTERVAL_SECONDS
                )
            except asyncio.TimeoutError:
                await websocket.send_json(HeartbeatMessage().model_dump(mode="json"))
                continue
            await websocket.send_json(EventMessage.from_domain_event(event).model_dump(mode="json"))
    except WebSocketDisconnect:
        pass
