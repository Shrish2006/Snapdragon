"""Event taxonomy.

Each member is grounded as follows:

- `TELEMETRY_RECEIVED` — emitted for every accepted `TelemetryBatch`
  (Phase 2 ingestion).
- `VALIDATION_FAILED` — emitted when `domain.telemetry.validation` rejects
  a reading/batch. The taxonomy slot exists in Phase 1 alongside the
  validation layer that produces the underlying `ValidationResult`; the
  concrete `DomainEvent` subclass is added in Phase 4 when the processing
  pipeline actually publishes it.
- `HELMET_ONLINE` / `HELMET_OFFLINE` — device-registry presence, required
  by "maintain real-time state for each helmet" (Phase 2).
- `PPE_DETECTION` — wraps the real `PPEDetectionResult` from ppe-detection.
- `ML_RESULT` — generic wrapper for any ML service output without a typed
  event of its own yet (today: only fall-detection, which has no output
  contract at all — see `domain.detection.models.MLServiceResult`). New ML
  services plug in here with zero taxonomy changes until they earn a typed
  event.
"""

from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    TELEMETRY_RECEIVED = "telemetry.received"
    VALIDATION_FAILED = "telemetry.validation_failed"
    HELMET_ONLINE = "helmet.online"
    HELMET_OFFLINE = "helmet.offline"
    PPE_DETECTION = "ml.ppe_detection"
    ML_RESULT = "ml.result"


class Severity(str, Enum):
    """Coarse severity for UI treatment (e.g. WS client badge color,
    alert routing). Kept to three levels deliberately — finer-grained risk
    scoring is a domain concern for the future fusion/processing pipeline,
    not the event envelope."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
