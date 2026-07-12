// Pure mapping functions: gateway sensor readings -> the exact prop
// shapes the existing dashboard cards already accept. This is the one
// place that knows about raw ADC thresholds, unit conversions, and
// "what counts as a warning" — cards stay presentational, hooks stay
// about data flow, and this module is unit-testable in isolation.
//
// Calibration caveat (see gateway/src/gateway/domain/telemetry/sensors.py):
// gas_lpg, carbon_monoxide, and sound_level are all raw, uncalibrated
// 10-bit ADC samples (0-1023) — no firmware-side ppm/dB conversion
// exists. Thresholds below are relative to that raw range, not a
// physical unit, and are intentionally conservative until a calibrated
// sensor curve exists.

import type {
  AnalogGasReading,
  DomainEvent,
  EnvironmentReading,
  GatewayStatusResponse,
  ImuReading,
  MLServiceResult,
  PPEDetectionResult,
  SensorReading,
  SensorType,
  SoundLevelReading,
  ValidationFailure,
} from "../api/types";
import type { SensorStatus } from "../../app/components/tokens";

const ADC_MAX = 1023;

// -- Sound (StatusStrip "Sound" pill) -----------------------------------

const SOUND_WARNING_RATIO = 0.55; // ~563/1023
const SOUND_DANGER_RATIO = 0.75; // ~767/1023

export interface SoundReadingView {
  value: string;
  status: SensorStatus;
}

export function normalizeSound(reading: SoundLevelReading | undefined): SoundReadingView | null {
  if (!reading) return null;
  const ratio = reading.adc_raw / ADC_MAX;
  const status: SensorStatus = ratio >= SOUND_DANGER_RATIO ? "danger" : ratio >= SOUND_WARNING_RATIO ? "warning" : "normal";
  return { value: `${reading.adc_raw} raw`, status };
}

// -- Air quality (StatusStrip "Air quality" pill) ------------------------

const GAS_WARNING_RATIO = 0.4;
const GAS_DANGER_RATIO = 0.65;
const CO_WARNING_RATIO = 0.4;
const CO_DANGER_RATIO = 0.65;

export interface AirQualityView {
  value: string;
  status: SensorStatus;
}

export function normalizeAirQuality(
  gas: AnalogGasReading | undefined,
  co: AnalogGasReading | undefined,
): AirQualityView | null {
  if (!gas && !co) return null;

  const gasRatio = gas ? gas.adc_raw / ADC_MAX : 0;
  const coRatio = co ? co.adc_raw / ADC_MAX : 0;

  const isDanger = (gas !== undefined && gasRatio >= GAS_DANGER_RATIO) || (co !== undefined && coRatio >= CO_DANGER_RATIO);
  const isWarning = (gas !== undefined && gasRatio >= GAS_WARNING_RATIO) || (co !== undefined && coRatio >= CO_WARNING_RATIO);
  const status: SensorStatus = isDanger ? "danger" : isWarning ? "warning" : "normal";
  const value = status === "danger" ? "Toxic" : status === "warning" ? "Elevated" : "Normal";

  return { value, status };
}

// -- Motion (MotionStatusCard) -------------------------------------------

export type MotionState = "upright" | "moving" | "fall";

const MOVING_MAGNITUDE_G = 1.3; // above resting ~1g while upright
const FALL_MAGNITUDE_G = 2.5; // sudden high-g impact

/**
 * Best-effort motion classification from IMU alone. `fall` here is a
 * conservative accelerometer heuristic, not the ML fall-detection
 * service's output — `ai_ml/fall_detection` has no implemented output
 * contract yet (health-check-only stub). A future `ml.result` event from
 * that service should take precedence over this heuristic once it
 * exists; see `normalizeMlFallEvent` below.
 */
export function normalizeMotion(reading: ImuReading | undefined): MotionState | null {
  if (!reading) return null;
  const magnitude = Math.abs(reading.accel_magnitude_g);
  if (magnitude >= FALL_MAGNITUDE_G) return "fall";
  if (magnitude >= MOVING_MAGNITUDE_G) return "moving";
  return "upright";
}

/**
 * Reads a fall signal out of a generic `ml.result` event payload, for
 * the day `fall_detection.py` stops being a stub. Returns `null` for any
 * payload that doesn't (yet) carry a recognizable fall flag — never
 * throws, never fabricates a state.
 */
export function normalizeMlFallEvent(service: string, payload: Record<string, unknown>): MotionState | null {
  if (service !== "fall-detection") return null;
  if (payload.fall_detected === true) return "fall";
  if (payload.fall_detected === false) return "upright";
  return null;
}

// -- Environment (EnvironmentCard trend lines + TemperatureCard ambient) --

export interface EnvironmentPoint {
  capturedAt: string;
  gasAdcRaw: number | null;
  coAdcRaw: number | null;
  humidityPct: number | null;
}

export function normalizeEnvironmentPoint(readings: {
  gas?: AnalogGasReading;
  co?: AnalogGasReading;
  environment?: EnvironmentReading;
  capturedAt: string;
}): EnvironmentPoint {
  return {
    capturedAt: readings.capturedAt,
    gasAdcRaw: readings.gas?.adc_raw ?? null,
    coAdcRaw: readings.co?.adc_raw ?? null,
    humidityPct: readings.environment?.humidity_pct ?? null,
  };
}

/** Maps a 0-1023 raw ADC series onto the card's existing 0-60 SVG viewBox
 * (`EnvironmentCard`'s `<svg viewBox="0 0 100 60">`), newest point last. */
export function toSvgPolylinePoints(values: number[], maxValue: number): string {
  if (values.length === 0) return "";
  const step = values.length > 1 ? 100 / (values.length - 1) : 0;
  return values
    .map((value, index) => {
      const x = index * step;
      const y = 60 - (Math.min(value, maxValue) / maxValue) * 60;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

// -- Shared: relative "last updated" text ---------------------------------

/** Matches the cards' existing copy style ("2 min ago", "30 sec ago", "now"). */
export function formatRelativeTime(isoTimestamp: string | null, nowMs: number = Date.now()): string {
  if (!isoTimestamp) return "—";
  const deltaMs = nowMs - new Date(isoTimestamp).getTime();
  if (deltaMs < 0) return "now";
  const seconds = Math.floor(deltaMs / 1000);
  if (seconds < 5) return "now";
  if (seconds < 60) return `${seconds} sec ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours} hr ago`;
}

/** Type-narrowing helper: extracts one sensor's reading from a
 * `HelmetState.latest_readings`-shaped map by its `SensorType` key. */
export function pickReading<T extends SensorReading["value"]>(
  latestReadings: Partial<Record<SensorType, SensorReading>>,
  sensorType: SensorType,
): T | undefined {
  const reading = latestReadings[sensorType];
  return reading ? (reading.value as T) : undefined;
}

// -- Alerts (new AlertsCard) ------------------------------------------

export interface AlertView {
  id: string;
  label: string;
  status: SensorStatus;
  occurredAt: string;
}

/**
 * Maps one `DomainEvent` to a human-readable alert row. Every branch is
 * grounded in an actual gateway payload shape (see each type's source
 * comment in `lib/api/types.ts`) — `helmet.online`/`helmet.offline` are
 * handled defensively even though the gateway doesn't publish them yet
 * (see `EVENT_TYPE_REGISTRY`'s docstring), so the alerts feed picks them
 * up automatically the day it does, with zero frontend changes.
 */
export function describeEvent(event: DomainEvent): AlertView {
  const base = { id: event.event_id, occurredAt: event.occurred_at };

  if (event.type === "telemetry.validation_failed") {
    const payload = event.payload as ValidationFailure;
    const count = payload.issues.length;
    return { ...base, label: `Telemetry rejected — ${count} issue${count === 1 ? "" : "s"}`, status: "warning" };
  }

  if (event.type === "helmet.online") {
    return { ...base, label: "Helmet back online", status: "normal" };
  }

  if (event.type === "helmet.offline") {
    return { ...base, label: "Helmet went offline", status: "danger" };
  }

  if (event.type === "ml.ppe_detection") {
    const payload = event.payload as PPEDetectionResult;
    const count = payload.detections.length;
    return { ...base, label: `PPE detection — ${count} object${count === 1 ? "" : "s"}`, status: "unknown" };
  }

  if (event.type === "ml.result") {
    const payload = event.payload as MLServiceResult;
    const fallState = normalizeMlFallEvent(payload.service, payload.payload);
    if (fallState === "fall") return { ...base, label: `Fall detected — ${payload.service}`, status: "danger" };
    return { ...base, label: `${payload.service} result`, status: "unknown" };
  }

  return { ...base, label: event.type, status: "unknown" };
}

// -- Gateway health (new StatusStrip "Gateway" pill) ---------------------

/** Worst-of aggregation across every upstream ML service, matching the
 * severity ordering `GET /v1/status` implies (`ok` < `degraded` < `unreachable`). */
export function summarizeServiceHealth(status: GatewayStatusResponse | null): { value: string; status: SensorStatus } {
  if (!status) return { value: "—", status: "unknown" };

  const serviceStatuses = Object.values(status.services);
  const okCount = serviceStatuses.filter((s) => s === "ok").length;
  const worst: SensorStatus = serviceStatuses.includes("unreachable")
    ? "danger"
    : serviceStatuses.includes("degraded")
      ? "warning"
      : "normal";

  return { value: `${okCount}/${serviceStatuses.length} OK`, status: worst };
}
