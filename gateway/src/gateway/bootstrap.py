"""Composition root: wires concrete adapters into application services.

Kept separate from `main.py` so the dependency graph — which adapter
implements which port, and what depends on what — lives in one place, and
grows in one place as later phases add WebSocket fan-out. `main.py` stays
a thin ASGI wiring file; route handlers never construct a service
themselves, they only read `Container` off `app.state` (see
`api/http/deps.py`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gateway.infrastructure.mqtt.adapter import MqttIngestionAdapter
    from gateway.infrastructure.mqtt.presence import MqttPresenceAdapter


from dataclasses import dataclass
from datetime import timedelta

import httpx

from gateway.application.detection_service import PPEDetectionService
from gateway.application.device_registry import DeviceRegistryService
from gateway.application.device_state_manager import DeviceStateManager
from gateway.application.ingestion_service import IngestionService
from gateway.application.ports import EventBus, EventStore
from gateway.application.service_health import ServiceHealthService
from gateway.application.subscription_service import SubscriptionManager
from gateway.config import Settings
from gateway.infrastructure.bus.in_memory import InMemoryEventBus
from gateway.infrastructure.ml_clients.fall_client import FallDetectionHttpClient
from gateway.infrastructure.ml_clients.mock_fall_client import MockFallDetectionClient
from gateway.infrastructure.ml_clients.mock_ppe_client import MockPPEDetectionClient
from gateway.infrastructure.ml_clients.ppe_client import PPEDetectionHttpClient
from gateway.infrastructure.persistence.in_memory import InMemoryEventStore
from gateway.infrastructure.registry.in_memory import InMemoryHelmetRepository
from gateway.workers.pipeline import EventProcessor, ProcessingPipeline
from gateway.workers.processors.fall_detection_processor import FallDetectionProcessor
from gateway.workers.processors.persistence_processor import PersistenceProcessor

_HTTP_CLIENT_TIMEOUT_SECONDS = 30.0
"""Matches the old gateway's `httpx.AsyncClient(timeout=30.0)` — generous
enough for PPE inference on a cold/CPU-only model."""


@dataclass(frozen=True, slots=True)
class Container:
    """Every application-layer singleton the API layer depends on."""

    device_registry: DeviceRegistryService
    device_state_manager: DeviceStateManager
    ingestion_service: IngestionService
    ppe_detection_service: PPEDetectionService
    service_health: ServiceHealthService
    event_bus: EventBus
    event_store: EventStore
    processing_pipeline: ProcessingPipeline
    subscription_manager: SubscriptionManager
    http_client: httpx.AsyncClient
    """Owned here so `main.py`'s lifespan can `aclose()` it on shutdown —
    one of two resources in this container that aren't just disposable
    in-process state (the other being `event_store`, when it's the SQLite
    backend — see that adapter's `initialize()`)."""
    mqtt_ingestion_adapter: MqttIngestionAdapter | None = None
    mqtt_presence_adapter: MqttPresenceAdapter | None = None


def build_container(settings: Settings) -> Container:
    # Single shared repository: DeviceRegistryService and
    # DeviceStateManager are peers over the same store, not a wrapper
    # relationship (see each module's docstring for why they're split).
    repository = InMemoryHelmetRepository()
    http_client = httpx.AsyncClient(timeout=_HTTP_CLIENT_TIMEOUT_SECONDS)

    event_bus = _build_event_bus(settings)
    event_store = _build_event_store(settings)

    device_registry = DeviceRegistryService(repository)
    device_state_manager = DeviceStateManager(repository)
    ingestion_service = IngestionService(
        device_state_manager,
        event_bus,
        max_clock_skew=timedelta(seconds=settings.telemetry_max_clock_skew_seconds),
    )

    if settings.mock_ml:
        ppe_client = MockPPEDetectionClient()
        fall_client = MockFallDetectionClient()
    else:
        ppe_client = PPEDetectionHttpClient(
            base_url=settings.ppe_url, http_client=http_client
        )
        fall_client = FallDetectionHttpClient(
            base_url=settings.fall_url, http_client=http_client
        )
    ppe_detection_service = PPEDetectionService(ppe_client, event_bus)
    service_health = ServiceHealthService(
        {"ppe-detection": ppe_client, "fall-detection": fall_client}
    )

    processors: list[EventProcessor] = [
        PersistenceProcessor(event_store),
        FallDetectionProcessor(fall_client, event_bus),
    ]
    processing_pipeline = ProcessingPipeline(event_bus, processors)
    subscription_manager = SubscriptionManager(event_bus)

    mqtt_ingestion, mqtt_presence = _build_mqtt_adapters(
        settings, ingestion_service, device_registry
    )
    return Container(
        device_registry=device_registry,
        device_state_manager=device_state_manager,
        ingestion_service=ingestion_service,
        ppe_detection_service=ppe_detection_service,
        service_health=service_health,
        event_bus=event_bus,
        event_store=event_store,
        processing_pipeline=processing_pipeline,
        subscription_manager=subscription_manager,
        http_client=http_client,
        mqtt_ingestion_adapter=mqtt_ingestion,
        mqtt_presence_adapter=mqtt_presence,
    )


def _build_event_bus(settings: Settings) -> EventBus:
    if settings.event_bus_backend == "redis":
        # Imported lazily: `redis` is a real dependency (see
        # pyproject.toml), but importing it eagerly at module load would
        # make every deployment pay for it even on the default backend.
        from redis.asyncio import Redis

        from gateway.infrastructure.bus.redis_streams import RedisStreamsEventBus

        return RedisStreamsEventBus(Redis.from_url(settings.redis_url))
    return InMemoryEventBus()


def _build_event_store(settings: Settings) -> EventStore:
    if settings.event_store_backend == "postgres":
        from gateway.infrastructure.persistence.postgres import PostgresEventStore

        return PostgresEventStore(settings.postgres_dsn)
    if settings.event_store_backend == "sqlite":
        from gateway.infrastructure.persistence.sqlite import SQLiteEventStore

        return SQLiteEventStore(settings.sqlite_path)
    return InMemoryEventStore(max_size=settings.event_buffer)


def _build_mqtt_adapters(
    settings: Settings,
    ingestion_service: IngestionService,
    registry: DeviceRegistryService,
) -> tuple[MqttIngestionAdapter | None, MqttPresenceAdapter | None]:
    """Build MQTT ingestion + presence adapters when `mqtt_broker_host` is set.

    Imported lazily so the `aiomqtt` dependency is only loaded when MQTT is
    actually enabled — mirrors the lazy-import pattern used for Redis and
    the Postgres/SQLite backends.
    """
    if not settings.mqtt_broker_host:
        return None, None
    from gateway.infrastructure.mqtt.adapter import MqttIngestionAdapter
    from gateway.infrastructure.mqtt.presence import MqttPresenceAdapter

    kwargs = {
        "broker_host": settings.mqtt_broker_host,
        "broker_port": settings.mqtt_broker_port,
        "username": settings.mqtt_username,
        "password": settings.mqtt_password,
        "topic_prefix": settings.mqtt_topic_prefix,
    }
    return (
        MqttIngestionAdapter(ingestion_service, **kwargs),
        MqttPresenceAdapter(registry, **kwargs),
    )
