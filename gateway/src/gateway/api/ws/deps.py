"""WebSocket-scoped dependency accessors — mirrors `api/http/deps.py`,
adapted for `WebSocket` instead of `Request` (FastAPI resolves either,
depending on the route's transport)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, WebSocket

from gateway.application.device_registry import DeviceRegistryService
from gateway.application.subscription_service import SubscriptionManager
from gateway.bootstrap import Container


def get_container(websocket: WebSocket) -> Container:
    return websocket.app.state.container


def get_subscription_manager(
    container: Annotated[Container, Depends(get_container)],
) -> SubscriptionManager:
    return container.subscription_manager


def get_device_registry(
    container: Annotated[Container, Depends(get_container)],
) -> DeviceRegistryService:
    return container.device_registry


SubscriptionManagerDep = Annotated[SubscriptionManager, Depends(get_subscription_manager)]
DeviceRegistryWSDep = Annotated[DeviceRegistryService, Depends(get_device_registry)]
