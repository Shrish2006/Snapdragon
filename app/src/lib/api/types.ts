// Shared types — a direct TypeScript mirror of the gateway's Pydantic
// contracts. Source of truth for each type is cited so a gateway schema
// change has one obvious place to update on the frontend.
//
// gateway/src/gateway/domain/telemetry/sensors.py::SensorType
export type SensorType =
  | "imu"
  | "gas_lpg"
  | "carbon_monoxide"
  | "environment"
  | "sound_level";

// gateway/src/gateway/domain/telemetry/models.py
export interface ImuReading {
  kind: "imu";
  accel_x_g: number;
  accel_y_g: number;
  accel_z_g: number;
  accel_magnitude_g: number;
  gyro_x_dps: number;
  gyro_y_dps: number;
  gyro_z_dps: number;
}

export interface AnalogGasReading {
  kind: "gas_lpg" | "carbon_monoxide";
  adc_raw: number;
}

export interface EnvironmentReading {
  kind: "environment";
  temperature_c: number;
  humidity_pct: number;
  heat_index_c: number;
}

export interface SoundLevelReading {
  kind: "sound_level";
  adc_raw: number;
}

/** Discriminated union — mirrors `SensorValue` (discriminator: `kind`). */
export type SensorValue = ImuReading | AnalogGasReading | EnvironmentReading | SoundLevelReading;

export interface SensorReading {
  value: SensorValue;
  captured_at: string; // ISO 8601, device-reported capture time (UTC)
}

export interface TelemetryBatch {
  helmet_id: string;
  sequence: number;
  sent_at: string;
  readings: SensorReading[];
}

// gateway/src/gateway/domain/helmets/models.py::HelmetStatus
export type HelmetStatus = "online" | "offline";

// gateway/src/gateway/domain/helmets/models.py::HelmetState
export interface HelmetState {
  helmet_id: string;
  status: HelmetStatus;
  first_seen_at: string;
  last_seen_at: string;
  last_sequence: number;
  /** Most recent reading per sensor type — a batch only ever contains a
   * subset of sensors, so this is a merge across batches over time. */
  latest_readings: Partial<Record<SensorType, SensorReading>>;
}

// gateway/src/gateway/domain/events/types.py::EventType
export type EventType =
  | "telemetry.received"
  | "telemetry.validation_failed"
  | "helmet.online"
  | "helmet.offline"
  | "ml.ppe_detection"
  | "ml.result";

// gateway/src/gateway/domain/events/types.py::Severity
export type Severity = "info" | "warning" | "critical";

// gateway/src/gateway/domain/detection/models.py
export interface PPEDetectionItem {
  class_name: string;
  confidence: number;
  bbox: [number, number, number, number];
  tracker_id: number | null;
}

export interface PPEDetectionResult {
  detections: PPEDetectionItem[];
}

export interface MLServiceResult {
  service: string;
  payload: Record<string, unknown>;
}

/**
 * `event.v1` envelope (gateway/src/gateway/domain/events/models.py::DomainEvent).
 * `payload` is left as `unknown` and narrowed per `type` by the caller —
 * the gateway itself avoids one generic response_model for the same
 * reason (see `api/ws/protocol.py`'s docstring): a heterogeneous stream
 * of concrete payload shapes doesn't fit one declared type.
 */
export interface DomainEvent<TPayload = unknown> {
  schema_version: string;
  event_id: string;
  type: EventType;
  severity: Severity;
  helmet_id: string | null;
  occurred_at: string;
  source: string;
  payload: TPayload;
  correlation_id: string | null;
}

export type TelemetryReceivedEvent = DomainEvent<TelemetryBatch> & { type: "telemetry.received" };
export type MLResultEvent = DomainEvent<MLServiceResult> & { type: "ml.result" };
export type PPEDetectionEvent = DomainEvent<PPEDetectionResult> & { type: "ml.ppe_detection" };

// gateway/src/gateway/domain/telemetry/validation.py::ValidationIssue
export interface ValidationIssue {
  field: string;
  message: string;
}

// gateway/src/gateway/domain/events/models.py::ValidationFailure
export interface ValidationFailure {
  helmet_id: string;
  sequence: number;
  issues: ValidationIssue[];
}

export type ValidationFailedEvent = DomainEvent<ValidationFailure> & { type: "telemetry.validation_failed" };

// gateway/src/gateway/application/ports.py::ServiceHealth
export type ServiceHealthStatus = "ok" | "degraded" | "unreachable";

// gateway/src/gateway/api/http/status.py::StatusResponse
export interface GatewayStatusResponse {
  gateway: string;
  services: Record<string, ServiceHealthStatus>;
}

// gateway/src/gateway/application/subscription_service.py::EventFilter
export interface EventFilter {
  helmet_id?: string | null;
  event_types?: EventType[] | null;
  severities?: Severity[] | null;
}

// gateway/src/gateway/api/ws/protocol.py — client -> server
export interface SubscribeMessage {
  action: "subscribe";
  filter: EventFilter;
}

// gateway/src/gateway/api/ws/protocol.py — server -> client
export interface SnapshotMessage {
  type: "snapshot";
  helmets: HelmetState[];
}

export interface EventMessage {
  type: "event";
  event: DomainEvent;
}

export interface HeartbeatMessage {
  type: "heartbeat";
}

export interface ErrorMessage {
  type: "error";
  detail: string;
}

export type ServerMessage = SnapshotMessage | EventMessage | HeartbeatMessage | ErrorMessage;

// gateway/src/gateway/api/http/events.py — query params shared by both
// event-history endpoints. Carries an index signature deliberately: this
// DTO's sole purpose is to be flattened into a URL query string.
export interface EventQueryParams {
  [key: string]: string | number | boolean | undefined;
  event_type?: EventType;
  since?: string;
  limit?: number;
}
