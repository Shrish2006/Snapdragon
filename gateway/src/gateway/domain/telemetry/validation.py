"""Business-rule validation for telemetry, distinct from Pydantic's
structural/type validation.

Pydantic (`SensorReading`, `TelemetryBatch`) already guarantees a payload is
well-formed JSON of the right shape and type. This module checks whether a
*well-formed* reading is *plausible*: an accelerometer sample of 400g is
structurally valid (it's a float) but physically nonsensical for this
hardware. Keeping that check here — driven by the single `SENSOR_REGISTRY`
— rather than as `Field(ge=..., le=...)` constraints on the models keeps
bounds in one auditable place and keeps the models themselves free of
sensor-specific policy.

Functions here are pure: no I/O, no global state. They return a
`ValidationResult` rather than raising, so callers (the ingestion layer,
Phase 2) decide what to do with an invalid batch — reject, quarantine, or
accept-with-a-flag.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from gateway.domain.telemetry.models import SensorReading, TelemetryBatch
from gateway.domain.telemetry.sensors import SENSOR_REGISTRY

DEFAULT_MAX_CLOCK_SKEW = timedelta(seconds=30.0)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One plausibility violation."""

    field: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """The outcome of validating a reading or a batch."""

    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        return not self.issues


def validate_reading(reading: SensorReading) -> ValidationResult:
    """Check one reading's numeric fields against its sensor's plausible
    bounds, as declared in `SENSOR_REGISTRY`."""
    spec = SENSOR_REGISTRY[reading.sensor_type]
    issues: list[ValidationIssue] = []
    for field_name, bounds in spec.fields.items():
        value = getattr(reading.value, field_name, None)
        if value is None:
            continue
        if not (bounds.minimum <= value <= bounds.maximum):
            issues.append(
                ValidationIssue(
                    field=field_name,
                    message=(
                        f"{value} {bounds.unit.value} outside plausible range "
                        f"[{bounds.minimum}, {bounds.maximum}] for "
                        f"{spec.sensor_type.value}"
                    ),
                )
            )
    return ValidationResult(tuple(issues))


def validate_batch(
    batch: TelemetryBatch,
    *,
    previous_sequence: int | None = None,
    max_clock_skew: timedelta = DEFAULT_MAX_CLOCK_SKEW,
    now: datetime | None = None,
) -> ValidationResult:
    """Batch-level checks that need context beyond a single reading:

    - Monotonic sequence numbers per helmet (out-of-order/replayed/duplicate
      packets are rejected). `previous_sequence` is supplied by the caller —
      tracking "the last accepted sequence per helmet" is the device
      registry's job (Phase 2), not this pure function's.
    - Sender clock skew, bounded by `max_clock_skew`
      (`Settings.telemetry_max_clock_skew_seconds` in production).

    Every reading in the batch is also validated individually; issues are
    aggregated into one result.
    """
    now = now or datetime.now(timezone.utc)
    issues: list[ValidationIssue] = []

    if previous_sequence is not None and batch.sequence <= previous_sequence:
        issues.append(
            ValidationIssue(
                field="sequence",
                message=(
                    f"non-monotonic sequence {batch.sequence} "
                    f"(last accepted was {previous_sequence})"
                ),
            )
        )

    skew = abs(now - batch.sent_at)
    if skew > max_clock_skew:
        issues.append(
            ValidationIssue(
                field="sent_at",
                message=f"clock skew {skew} exceeds max {max_clock_skew}",
            )
        )

    for reading in batch.readings:
        issues.extend(validate_reading(reading).issues)

    return ValidationResult(tuple(issues))
