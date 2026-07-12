"""MQTT presence adapter — event-driven offline detection via Last Will & Testament.

Subscribes to `{topic_prefix}/status/+` (QoS 0).  When a helmet's TCP
connection drops, the broker publishes its pre-registered LWT payload
`{"status": "offline"}` to `safeguard/status/{helmet_id}`.  This adapter
receives it and calls `DeviceRegistryService.mark_offline()` immediately,
instead of waiting up to 60 s for the staleness sweep.

Helmets publish `{"status": "online", retain: true}` on connect so the
retained message reflects last-known state even while the gateway is down.
"""

from __future__ import annotations

import json
import logging

import aiomqtt

from gateway.application.device_registry import DeviceRegistryService
from gateway.domain.common.errors import InvalidHelmetIdError
from gateway.domain.common.identifiers import parse_helmet_id

logger = logging.getLogger("gateway.mqtt.presence")


class MqttPresenceAdapter:
    """Consumes `safeguard/status/+` and applies LWT-driven offline transitions."""

    def __init__(
        self,
        registry: DeviceRegistryService,
        *,
        broker_host: str,
        broker_port: int = 1883,
        username: str = "",
        password: str = "",
        topic_prefix: str = "safeguard",
    ) -> None:
        self._registry = registry
        self._broker_host = broker_host
        self._broker_port = broker_port
        self._username = username or None
        self._password = password or None
        self._status_topic = f"{topic_prefix}/status/+"

    async def run(self) -> None:
        async with aiomqtt.Client(
            self._broker_host,
            port=self._broker_port,
            username=self._username,
            password=self._password,
        ) as client:
            await client.subscribe(self._status_topic, qos=0)
            logger.info("subscribed topic=%s", self._status_topic)
            async for message in client.messages:
                await self._handle(message)

    async def _handle(self, message: aiomqtt.Message) -> None:
        topic_str = str(message.topic)
        parts = topic_str.split("/")
        raw_id = parts[-1] if len(parts) >= 3 else ""
        try:
            helmet_id = parse_helmet_id(raw_id)
        except InvalidHelmetIdError:
            logger.warning("invalid helmet_id in status topic=%r", topic_str)
            return

        try:
            payload = json.loads(message.payload)
        except Exception:
            logger.warning("malformed status payload on topic=%r", topic_str)
            return

        if payload.get("status") == "offline":
            state = await self._registry.mark_offline(helmet_id)
            if state is not None:
                logger.info("helmet_id=%r marked offline via LWT", helmet_id)
