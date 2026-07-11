"""FastAPI dependency accessors — bridge the `Container` (built once by
`gateway.bootstrap` and attached to `app.state` in `main.py`) into route
handlers via `Depends`."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from gateway.application.detection_service import PPEDetectionService
from gateway.application.device_registry import DeviceRegistryService
from gateway.application.ingestion_service import IngestionService
from gateway.application.ports import EventStore
from gateway.application.service_health import ServiceHealthService
from gateway.bootstrap import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_ingestion_service(
    container: Annotated[Container, Depends(get_container)],
) -> IngestionService:
    return container.ingestion_service


def get_device_registry(
    container: Annotated[Container, Depends(get_container)],
) -> DeviceRegistryService:
    return container.device_registry


def get_ppe_detection_service(
    container: Annotated[Container, Depends(get_container)],
) -> PPEDetectionService:
    return container.ppe_detection_service


def get_service_health(
    container: Annotated[Container, Depends(get_container)],
) -> ServiceHealthService:
    return container.service_health


def get_event_store(container: Annotated[Container, Depends(get_container)]) -> EventStore:
    return container.event_store


IngestionServiceDep = Annotated[IngestionService, Depends(get_ingestion_service)]
DeviceRegistryDep = Annotated[DeviceRegistryService, Depends(get_device_registry)]
PPEDetectionServiceDep = Annotated[PPEDetectionService, Depends(get_ppe_detection_service)]
ServiceHealthDep = Annotated[ServiceHealthService, Depends(get_service_health)]
EventStoreDep = Annotated[EventStore, Depends(get_event_store)]
