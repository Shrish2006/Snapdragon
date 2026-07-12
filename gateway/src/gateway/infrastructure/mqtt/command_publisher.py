"""MQTT command publisher — gateway-to-device downlink.

Publishes JSON commands to `{topic_prefix}/command/{helmet_id}/{command}` at
QoS 1 so the broker guarantees delivery when the device is online.  Each
command is fire-and-forget from the gateway's perspective; the device is
responsible for idempotent handling (e.g. buzzer re-trigger is safe, config
overwrite is idempotent, OTA install is guarded by SHA-256 verification).

Current command set:

  alert   {"buzzer": true, "duration_ms": 3000}
  config  {"max_clock_skew_seconds": 30, "sample_interval_ms": 500}
  ota     {"url": "https://…/firmware.bin", "sha256": "…"}

Extend by adding a new command name and calling `publish(helmet_id, name, payload)`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import aiomqtt

logger = logging.getLogger("gateway.mqtt.commands")


class MqttCommandPublisher:
    """Thin async wrapper that publishes a command to one helmet."""

    def __init__(
        self,
        *,
        broker_host: str,
        broker_port: int = 1883,
        username: str = "",
        password: str = "",
        topic_prefix: str = "safeguard",
    ) -> None:
        self._broker_host = broker_host
        self._broker_port = broker_port
        self._username = username or None
        self._password = password or None
        self._prefix = topic_prefix

    async def publish(
        self,
        helmet_id: str,
        command: str,
        payload: dict[str, Any],
    ) -> None:
        """Publish one command to `{prefix}/command/{helmet_id}/{command}`.

        Opens a transient client per call — commands are infrequent enough
        that a persistent connection isn't worth the added lifecycle
        complexity here.  Switch to a shared persistent client if command
        volume grows.
        """
        topic = f"{self._prefix}/command/{helmet_id}/{command}"
        raw = json.dumps(payload)
        async with aiomqtt.Client(
            self._broker_host,
            port=self._broker_port,
            username=self._username,
            password=self._password,
        ) as client:
            await client.publish(topic, payload=raw, qos=1)
            logger.info(
                "published command=%r to helmet_id=%r (%d bytes)",
                command,
                helmet_id,
                len(raw),
            )
