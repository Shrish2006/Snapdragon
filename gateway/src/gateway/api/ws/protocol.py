"""WebSocket message contracts.

Client -> server: `SubscribeMessage` — sendable any time after connecting
(not just once), (re)declaring which events this connection wants;
`SubscriptionManager.update_filter` applies it immediately.

Server -> client: `SnapshotMessage` (sent once, right after connecting —
the current helmet roster, so a dashboard has something to render before
the first live event arrives), `EventMessage` (a matching domain event),
`HeartbeatMessage` (sent when nothing else has been sent for a while, so
clients/load balancers can tell the connection is still alive),
`ErrorMessage` (a malformed client message).

`EventMessage.event`/`SnapshotMessage.helmets` are plain
`dict`/`list[dict]` (via `.model_dump(mode="json")`) rather than the live
typed domain objects: `DomainEvent` is generic over its payload, and
round-tripping a heterogeneous stream of concrete subclasses through one
declared field type risks pydantic serializing against the *declared*
(generic) schema instead of the *actual* subclass's — a real footgun this
module simply avoids rather than works around.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from gateway.application.subscription_service import EventFilter
from gateway.domain.events.models import DomainEvent
from gateway.domain.helmets.models import HelmetState


class SubscribeMessage(BaseModel):
    action: Literal["subscribe"] = "subscribe"
    filter: EventFilter = EventFilter()


class SnapshotMessage(BaseModel):
    type: Literal["snapshot"] = "snapshot"
    helmets: list[dict[str, Any]]

    @classmethod
    def from_helmets(cls, helmets: list[HelmetState]) -> SnapshotMessage:
        return cls(helmets=[helmet.model_dump(mode="json") for helmet in helmets])


class EventMessage(BaseModel):
    type: Literal["event"] = "event"
    event: dict[str, Any]

    @classmethod
    def from_domain_event(cls, event: DomainEvent[Any]) -> EventMessage:
        return cls(event=event.model_dump(mode="json"))


class HeartbeatMessage(BaseModel):
    type: Literal["heartbeat"] = "heartbeat"


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    detail: str
