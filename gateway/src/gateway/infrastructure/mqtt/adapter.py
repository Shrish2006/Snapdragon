"""MQTT telemetry ingestion adapter — transport peer of `api/http/telemetry.py`.

Subscribes to `{topic_prefix}/telemetry/+` (QoS 1) and calls
`IngestionService.ingest()` for every well-formed, topic-consistent message.
The adapter is intentionally thin: validation, state mutation, and event
publishing all live in `IngestionService`, unchanged from the HTTP path.

Lifecycle: `run()` is designed to be started as a background asyncio task
(`main.py` lifespan) and run for the process lifetime.  `aiomqtt.Client`
reconnects automatically on network failure.
"""

from __future__ import annotations

import logging

import aiomqtt

from gateway.application.ingestion_service import IngestionService
from gateway.domain.common.errors import InvalidHelmetIdError
from gateway.domain.common.identifiers import parse_helmet_id
from gateway.domain.telemetry.models import TelemetryBatch

logger = logging.getLogger("gateway.mqtt.ingestion")


class MqttIngestionAdapter:
    """Consumes `safeguard/telemetry/+` and forwards to `IngestionService`."""

    def __init__(
        self,
        ingestion_service: IngestionService,
        *,
        broker_host: str,
        broker_port: int = 1883,
        username: str = "",
        password: str = "",
        topic_prefix: str = "safeguard",
    ) -> None:
        self._service = ingestion_service
        self._broker_host = broker_host
        self._broker_port = broker_port
        self._username = username or None
        self._password = password or None
        self._telemetry_topic = f"{topic_prefix}/telemetry/+"

    async def run(self) -> None:
        async with aiomqtt.Client(
            self._broker_host,
            port=self._broker_port,
            username=self._username,
            password=self._password,
        ) as client:
            await client.subscribe(self._telemetry_topic, qos=1)
            logger.info("subscribed topic=%s", self._telemetry_topic)
            async for message in client.messages:
                await self._handle(message)

    async def _handle(self, message: aiomqtt.Message) -> None:
        topic_str = str(message.topic)
        # Expected shape: {prefix}/telemetry/{helmet_id}
        parts = topic_str.split("/")
        raw_id = parts[-1] if len(parts) >= 3 else ""
        try:
            topic_helmet_id = parse_helmet_id(raw_id)
        except InvalidHelmetIdError:
            logger.warning("invalid helmet_id in topic=%r — dropped", topic_str)
            return

        try:
            batch = TelemetryBatch.model_validate_json(message.payload)
        except Exception as exc:
            logger.warning(
                "malformed payload on topic=%r: %s — dropped", topic_str, exc
            )
            return

        if batch.helmet_id != topic_helmet_id:
            logger.warning(
                "topic helmet_id=%r != payload helmet_id=%r — dropped",
                topic_helmet_id,
                batch.helmet_id,
            )
            return

        result = await self._service.ingest(batch)
        if not result.accepted:
            logger.info(
                "batch from helmet_id=%r seq=%s rejected: %s",
                batch.helmet_id,
                batch.sequence,
                [i.message for i in result.issues],
            )
