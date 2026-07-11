"""Tests for `gateway.domain.events.models`."""

import pytest
from pydantic import ValidationError

from gateway.domain.detection.models import MLServiceResult, PPEDetectionResult
from gateway.domain.events.models import (
    EVENT_TYPE_REGISTRY,
    MLResultEvent,
    PPEDetectionEvent,
    TelemetryReceivedEvent,
    ValidationFailedEvent,
    ValidationFailure,
)
from gateway.domain.events.types import EventType, Severity
from gateway.domain.telemetry.models import ImuReading, SensorReading, TelemetryBatch
from gateway.domain.telemetry.validation import ValidationIssue
from datetime import datetime, timezone

NOW = datetime(2026, 7, 12, tzinfo=timezone.utc)


def _batch() -> TelemetryBatch:
    return TelemetryBatch(
        helmet_id="HLM-0007",
        sequence=1,
        sent_at=NOW,
        readings=[
            SensorReading(
                value=ImuReading(
                    accel_x_g=0.0, accel_y_g=0.0, accel_z_g=1.0,
                    accel_magnitude_g=1.0, gyro_x_dps=0.0, gyro_y_dps=0.0, gyro_z_dps=0.0,
                ),
                captured_at=NOW,
            )
        ],
    )


def test_telemetry_received_event_defaults_its_type_and_severity() -> None:
    event = TelemetryReceivedEvent(
        helmet_id="HLM-0007", source="gateway.ingest", payload=_batch()
    )
    assert event.type is EventType.TELEMETRY_RECEIVED
    assert event.severity is Severity.INFO
    assert event.schema_version == "event.v1"
    assert event.correlation_id is None


def test_ppe_detection_event_requires_a_ppe_detection_result_payload() -> None:
    with pytest.raises(ValidationError):
        PPEDetectionEvent(
            helmet_id=None, source="ppe-detection", payload=_batch()  # wrong payload type
        )

    event = PPEDetectionEvent(
        source="ppe-detection",
        payload=PPEDetectionResult(detections=[]),
    )
    assert event.type is EventType.PPE_DETECTION


def test_ml_result_event_carries_the_generic_envelope() -> None:
    event = MLResultEvent(
        source="fall-detection",
        payload=MLServiceResult(service="fall-detection", payload={"status": "unimplemented"}),
    )
    assert event.type is EventType.ML_RESULT
    assert event.payload.service == "fall-detection"


def test_events_are_independently_identified() -> None:
    a = TelemetryReceivedEvent(source="gateway.ingest", payload=_batch())
    b = TelemetryReceivedEvent(source="gateway.ingest", payload=_batch())
    assert a.event_id != b.event_id


def test_validation_failed_event_defaults_to_warning_severity() -> None:
    event = ValidationFailedEvent(
        helmet_id="HLM-0007",
        source="gateway.ingest",
        payload=ValidationFailure(
            helmet_id="HLM-0007",
            sequence=5,
            issues=[ValidationIssue(field="sequence", message="non-monotonic")],
        ),
    )
    assert event.type is EventType.VALIDATION_FAILED
    assert event.severity is Severity.WARNING
    assert event.payload.issues[0].field == "sequence"


@pytest.mark.parametrize(
    "event_type",
    [
        EventType.TELEMETRY_RECEIVED,
        EventType.VALIDATION_FAILED,
        EventType.PPE_DETECTION,
        EventType.ML_RESULT,
    ],
)
def test_every_registered_event_type_round_trips_through_json(event_type: EventType) -> None:
    """The registry is what `SQLiteEventStore`/`RedisStreamsEventBus` rely
    on to reconstruct a typed event from a stored/wire JSON blob — prove
    every registered type actually survives that round trip."""
    model = EVENT_TYPE_REGISTRY[event_type]
    payloads = {
        EventType.TELEMETRY_RECEIVED: _batch(),
        EventType.VALIDATION_FAILED: ValidationFailure(
            helmet_id="HLM-0007", sequence=1, issues=[]
        ),
        EventType.PPE_DETECTION: PPEDetectionResult(detections=[]),
        EventType.ML_RESULT: MLServiceResult(service="fall-detection", payload={}),
    }
    original = model(source="test", payload=payloads[event_type])

    restored = model.model_validate_json(original.model_dump_json())

    assert restored == original
    assert restored.type is event_type
