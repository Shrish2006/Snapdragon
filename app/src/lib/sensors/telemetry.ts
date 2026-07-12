// TelemetryBatch <-> HelmetState folding. Mirrors
// gateway/src/gateway/domain/helmets/models.py::HelmetState.apply_batch /
// .first_contact exactly, so live WS updates merge into local state the
// same way the gateway itself merges them — this is the one place that
// logic lives on the frontend, reused by both the WS live-update path
// and the REST event-history backfill path (never duplicated per card).

import type { AnalogGasReading, EnvironmentReading, HelmetState, SensorReading, SensorType, TelemetryBatch } from "../api/types";
import { normalizeEnvironmentPoint, type EnvironmentPoint } from "./normalize";

/** First reading of a given sensor kind within one batch (a batch
 * carries at most one reading per sensor in current firmware, but this
 * doesn't assume that). */
export function pickFromBatch<T extends SensorReading["value"]>(
  batch: TelemetryBatch,
  sensorType: SensorType,
): T | undefined {
  const reading = batch.readings.find((candidate) => candidate.value.kind === sensorType);
  return reading ? (reading.value as T) : undefined;
}

/** Extracts one `EnvironmentPoint` (gas/CO/humidity) from a live batch. */
export function environmentPointFromBatch(batch: TelemetryBatch): EnvironmentPoint {
  return normalizeEnvironmentPoint({
    gas: pickFromBatch<AnalogGasReading>(batch, "gas_lpg"),
    co: pickFromBatch<AnalogGasReading>(batch, "carbon_monoxide"),
    environment: pickFromBatch<EnvironmentReading>(batch, "environment"),
    capturedAt: batch.sent_at,
  });
}

/** Mirrors `HelmetState.apply_batch`: overwrite each sensor's latest
 * reading, bump presence, go online. */
export function applyBatchToHelmetState(state: HelmetState, batch: TelemetryBatch): HelmetState {
  const mergedReadings: Partial<Record<SensorType, SensorReading>> = { ...state.latest_readings };
  for (const reading of batch.readings) {
    mergedReadings[reading.value.kind] = reading;
  }
  return {
    ...state,
    status: "online",
    last_seen_at: batch.sent_at,
    last_sequence: batch.sequence,
    latest_readings: mergedReadings,
  };
}

/** Mirrors `HelmetState.first_contact`: builds initial state for a
 * helmet the frontend hasn't fetched/seen a snapshot for yet. */
export function firstContactHelmetState(batch: TelemetryBatch): HelmetState {
  const readings: Partial<Record<SensorType, SensorReading>> = {};
  for (const reading of batch.readings) readings[reading.value.kind] = reading;
  return {
    helmet_id: batch.helmet_id,
    status: "online",
    first_seen_at: batch.sent_at,
    last_seen_at: batch.sent_at,
    last_sequence: batch.sequence,
    latest_readings: readings,
  };
}

/**
 * Reconciles a periodic `GET /v1/helmets/{id}` poll with locally
 * accumulated (WS-driven) state. Presence/offline transitions
 * (`DeviceRegistryService.sweep_offline`) are not published as events
 * yet — see `domain/events/models.py::EVENT_TYPE_REGISTRY`'s docstring —
 * so a periodic REST poll is, today, the only way the frontend can ever
 * observe a helmet going offline. Keeps whichever side has the more
 * recent readings (WS may be ahead of a REST response issued a moment
 * earlier) but always adopts the REST poll's `status`, since that's the
 * one field only the poll can update.
 */
export function reconcileWithRestPoll(current: HelmetState | null, restState: HelmetState): HelmetState {
  if (!current) return restState;
  if (new Date(current.last_seen_at) > new Date(restState.last_seen_at)) {
    return { ...current, status: restState.status };
  }
  return restState;
}
