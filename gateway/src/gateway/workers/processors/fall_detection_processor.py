"""Fall detection processor: per-helmet circular buffer + debounce.

Sits in the ProcessingPipeline alongside PersistenceProcessor. For every
TelemetryReceivedEvent that contains IMU readings, it:

  1. Appends the new samples to a per-helmet deque(maxlen=200).
  2. Every STRIDE new samples, sends the full 200-sample window to the
     fall-detection service for inference.
  3. Debounces the result: fires a CRITICAL MLResultEvent only when
     DEBOUNCE consecutive windows both exceed the probability threshold.

The fall-detection service is stateless — it receives a complete window
and returns a probability. All buffer and debounce state lives here,
in the gateway, alongside the rest of the helmet state.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Any

from gateway.application.ports import EventPublisher, FallDetectionClient
from gateway.domain.detection.models import FallDetectionResult, MLServiceResult
from gateway.domain.events.models import DomainEvent, MLResultEvent
from gateway.domain.events.types import EventType, Severity
from gateway.domain.telemetry.sensors import SensorType
from gateway.infrastructure.ml_clients.errors import (
    MLServiceResponseError,
    MLServiceUnavailableError,
)

logger = logging.getLogger(__name__)

WINDOW    = 200   # samples — must match training window
STRIDE    = 50    # run inference every N new samples (75% overlap)
THRESHOLD = 0.70  # sigmoid probability above which a window is "fall"
DEBOUNCE  = 2     # consecutive windows required before firing an alert


class FallDetectionProcessor:
    """Implements `workers.pipeline.EventProcessor` structurally."""

    def __init__(
        self,
        client: FallDetectionClient,
        event_publisher: EventPublisher,
    ) -> None:
        self._client    = client
        self._publisher = event_publisher

        # per-helmet circular buffers: helmet_id → deque of [ax, ay, az, gx, gy, gz]
        self._buf: dict[str, deque[list[float]]] = defaultdict(
            lambda: deque(maxlen=WINDOW)
        )
        # how many new samples have arrived since the last inference run
        self._new_since: dict[str, int]  = defaultdict(int)
        # how many consecutive windows have exceeded THRESHOLD
        self._consec:    dict[str, int]  = defaultdict(int)
        # latch: True while a fall episode is active (prevents duplicate alerts)
        self._in_fall:   dict[str, bool] = defaultdict(bool)

    async def process(self, event: DomainEvent[Any]) -> None:
        if event.type != EventType.TELEMETRY_RECEIVED:
            return

        batch = event.payload
        helmet_id = str(batch.helmet_id)

        imu_readings = [
            r.value
            for r in batch.readings
            if r.sensor_type == SensorType.IMU
        ]
        if not imu_readings:
            return

        buf = self._buf[helmet_id]
        for r in imu_readings:
            # accel_magnitude_g is excluded — the model uses 6 channels only
            buf.append([r.accel_x_g, r.accel_y_g, r.accel_z_g,
                        r.gyro_x_dps, r.gyro_y_dps, r.gyro_z_dps])
        self._new_since[helmet_id] += len(imu_readings)

        # belt not full yet — not enough history to classify
        if len(buf) < WINDOW:
            return

        # haven't accumulated enough new samples to warrant re-running inference
        if self._new_since[helmet_id] < STRIDE:
            return

        self._new_since[helmet_id] = 0
        window = list(buf)  # snapshot: list of 200 x [ax, ay, az, gx, gy, gz]

        try:
            result: FallDetectionResult = await self._client.ingest(helmet_id, window)
        except (MLServiceUnavailableError, MLServiceResponseError) as exc:
            logger.warning("fall-detection unavailable for %s: %s", helmet_id, exc)
            return

        await self._handle_result(helmet_id, result, batch.helmet_id)

    async def _handle_result(
        self,
        helmet_id: str,
        result: FallDetectionResult,
        typed_id: Any,
    ) -> None:
        if result.probability >= THRESHOLD:
            self._consec[helmet_id] += 1
            if self._consec[helmet_id] >= DEBOUNCE and not self._in_fall[helmet_id]:
                self._in_fall[helmet_id]  = True
                self._consec[helmet_id]   = 0
                logger.warning(
                    "FALL DETECTED  helmet=%s  prob=%.3f",
                    helmet_id, result.probability,
                )
                await self._publisher.publish(
                    MLResultEvent(
                        helmet_id=typed_id,
                        source="fall-detection",
                        severity=Severity.CRITICAL,
                        payload=MLServiceResult(
                            service="fall-detection",
                            payload=result.model_dump(),
                        ),
                    )
                )
        else:
            self._consec[helmet_id] = max(0, self._consec[helmet_id] - 1)
            # clear the latch once two consecutive sub-threshold windows pass
            if self._in_fall[helmet_id] and self._consec[helmet_id] == 0:
                self._in_fall[helmet_id] = False
                logger.info("Fall episode cleared  helmet=%s", helmet_id)