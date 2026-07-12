# Gateway Backend & Device Connectivity

Architecture reference for the SafeGuard gateway. Covers both HTTP and MQTT
transports, the domain model, event pipeline, K8s deployment, and the WebSocket
real-time API. For a step-by-step implementation plan see
`docs/device-connectivity.md`. For a practical walkthrough, start with the
[quickstart](#quickstart-sending-telemetry) below.

---

## Table of Contents

- [Quickstart: sending telemetry](#quickstart-sending-telemetry)
- [Gateway overview](#gateway-overview)
- [Architecture (hexagonal / ports & adapters)](#architecture-hexagonal--ports--adapters)
- [Domain model](#domain-model)
- [API surface](#api-surface)
- [How devices connect](#how-devices-connect)
- [MQTT integration](#mqtt-integration)
  - [Why MQTT](#why-mqtt)
  - [Architectural readiness](#architectural-readiness)
  - [Topic hierarchy](#topic-hierarchy)
  - [Authentication \& security](#authentication--security)
  - [QoS \& delivery guarantees](#qos--delivery-guarantees)
- [Infrastructure \& deployment](#infrastructure--deployment)
  - [Docker Compose (local dev)](#docker-compose-local-dev)
  - [Kubernetes (production)](#kubernetes-production)
- [Event pipeline](#event-pipeline)
- [Real-time streaming (WebSocket)](#real-time-streaming-websocket)
- [Operational endpoints](#operational-endpoints)

---

## Gateway overview

The gateway is a **FastAPI** application (Python 3.11+, port `8080`) that is the single ingress point for all helmet telemetry. It runs as `gateway/src/gateway/main.py`, built via composition root in `gateway/src/gateway/bootstrap.py`.

| Concern | Implementation |
|---------|---------------|
| HTTP framework | FastAPI + uvicorn |
| Configuration | `pydantic-settings` (env vars, `.env` file) |
| Event bus (fan-out) | In-memory (`asyncio.Queue`) or Redis Streams (`XADD`/`XREADGROUP`, stream key `gateway:events`) |
| Event persistence | In-memory, SQLite, or PostgreSQL |
| ML clients | HTTP to `ppe-detection` + `fall-detection` services |
| Observability | Prometheus metrics (`/metrics`), structured JSON logging |

## Quickstart: sending telemetry

### 1. Start the stack

```bash
docker compose up --build
```

Wait for all services to reach healthy status. The Mosquitto broker listens on
`localhost:1883` and the gateway on `localhost:8080`.

### 2. Send a telemetry batch

Copy-paste this into a terminal once the stack is up. It publishes one
`TelemetryBatch` to the broker; the gateway picks it up and ingests it through
the same pipeline as an HTTP `POST /v1/telemetry`:

```bash
mosquitto_pub -h localhost -p 1883 \
  -t safeguard/telemetry/helmet-01 \
  -m '{
    "helmet_id": "helmet-01",
    "sequence": 1,
    "sent_at": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'",
    "readings": [
      {
        "captured_at": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'",
        "value": {
          "kind": "imu",
          "accel_x_g": 0.03, "accel_y_g": -0.01, "accel_z_g": 1.02,
          "accel_magnitude_g": 1.02,
          "gyro_x_dps": 1.5, "gyro_y_dps": -0.2, "gyro_z_dps": 0.1
        }
      },
      {
        "captured_at": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'",
        "value": { "kind": "environment", "temperature_c": 28.4, "humidity_pct": 62.1, "heat_index_c": 30.2 }
      },
      {
        "captured_at": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'",
        "value": { "kind": "gas_lpg", "adc_raw": 312 }
      },
      {
        "captured_at": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'",
        "value": { "kind": "carbon_monoxide", "adc_raw": 198 }
      },
      {
        "captured_at": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'",
        "value": { "kind": "sound_level", "adc_raw": 450 }
      }
    ]
  }' -q 1
```

On Windows (PowerShell), use this equivalent:

```powershell
$ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$body = @"
{
  "helmet_id": "helmet-01",
  "sequence": 1,
  "sent_at": "$ts",
  "readings": [
    { "captured_at": "$ts", "value": { "kind": "imu", "accel_x_g": 0.03, "accel_y_g": -0.01, "accel_z_g": 1.02, "accel_magnitude_g": 1.02, "gyro_x_dps": 1.5, "gyro_y_dps": -0.2, "gyro_z_dps": 0.1 } },
    { "captured_at": "$ts", "value": { "kind": "environment", "temperature_c": 28.4, "humidity_pct": 62.1, "heat_index_c": 30.2 } },
    { "captured_at": "$ts", "value": { "kind": "gas_lpg", "adc_raw": 312 } },
    { "captured_at": "$ts", "value": { "kind": "carbon_monoxide", "adc_raw": 198 } },
    { "captured_at": "$ts", "value": { "kind": "sound_level", "adc_raw": 450 } }
  ]
}
"@
mosquitto_pub -h localhost -p 1883 -t safeguard/telemetry/helmet-01 -m $body -q 1
```

**If you don't have `mosquitto_pub` installed**, use `pip install paho-mqtt`:

```python
import json, paho.mqtt.client as mqtt
from datetime import datetime, timezone

c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
c.connect("localhost", 1883)
ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
c.publish("safeguard/telemetry/helmet-01", json.dumps({
    "helmet_id": "helmet-01",
    "sequence": 1,
    "sent_at": ts,
    "readings": [
        {"captured_at": ts, "value": {"kind": "imu", "accel_x_g": 0.03, "accel_y_g": -0.01, "accel_z_g": 1.02, "accel_magnitude_g": 1.02, "gyro_x_dps": 1.5, "gyro_y_dps": -0.2, "gyro_z_dps": 0.1}},
        {"captured_at": ts, "value": {"kind": "environment", "temperature_c": 28.4, "humidity_pct": 62.1, "heat_index_c": 30.2}},
        {"captured_at": ts, "value": {"kind": "gas_lpg", "adc_raw": 312}},
        {"captured_at": ts, "value": {"kind": "carbon_monoxide", "adc_raw": 198}},
        {"captured_at": ts, "value": {"kind": "sound_level", "adc_raw": 450}},
    ]
}), qos=1)
c.disconnect()
```

### 3. Verify ingestion

```bash
# Check the helmet appeared in the registry
curl -s http://localhost:8080/v1/helmets | jq

# Query the event log
curl -s "http://localhost:8080/v1/events?event_type=telemetry.received&limit=3" | jq

# Watch events live over WebSocket
websocat ws://localhost:8080/v1/ws | jq .
```

All three transports — MQTT, HTTP, and WebSocket — feed the same `IngestionService`
and event pipeline. You can mix them freely: publish a batch over MQTT, verify it
appears in `GET /v1/helmets`, and see the event arrive over `GET /v1/ws`.
---

## Architecture (hexagonal / ports & adapters)

The codebase follows a **hexagonal (ports & adapters)** layering. No transport, database, or infrastructure concern leaks into the domain.

```
gateway/src/gateway/
├── domain/                 # Pure business rules — zero I/O
│   ├── common/             # HelmetId, errors
│   ├── telemetry/          # SensorReading, TelemetryBatch, validation
│   ├── helmets/            # HelmetState aggregate
│   ├── events/             # DomainEvent envelope + taxonomy
│   └── detection/          # PPEDetectionResult, MLServiceResult
│
├── application/            # Use-cases — protocol-agnostic
│   ├── ingestion_service.py      # Ingest one TelemetryBatch
│   ├── device_registry.py        # CRUD over helmet state
│   ├── device_state_manager.py   # Sequence tracking + state apply
│   ├── subscription_service.py   # Fan-out event bus → filtered client queues
│   ├── detection_service.py      # Forward frame → ML → publish result
│   ├── service_health.py         # Aggregate health across ML services
│   └── ports.py                  # Protocols: EventBus, EventStore, HelmetRepository, …
│
├── infrastructure/         # Concrete adapters
│   ├── persistence/        # InMemoryEventStore, SQLiteEventStore, PostgresEventStore
│   ├── bus/                # InMemoryEventBus, (RedisEventBus)
│   ├── registry/           # InMemoryHelmetRepository
│   ├── ml_clients/         # PPEDetectionHttpClient, FallDetectionHttpClient, mocks
│   └── metrics/            # Prometheus counters + histograms
│
├── api/                    # Transport layer
│   ├── http/               # REST endpoints
│   │   ├── telemetry.py    # POST /v1/telemetry
│   │   ├── helmets.py      # GET /v1/helmets, /v1/helmets/{id}
│   │   ├── events.py       # GET /v1/events, /v1/helmets/{id}/events
│   │   ├── detections.py   # POST /v1/detections/ppe
│   │   ├── status.py       # GET /v1/status
│   │   ├── health.py       # GET /health, /ready
│   │   └── metrics.py      # GET /metrics
│   └── ws/                 # WebSocket
│       ├── stream.py       # GET /v1/ws (live event fan-out)
│       └── protocol.py     # SubscribeMessage, EventMessage, SnapshotMessage, …
│
└── workers/
    ├── pipeline.py         # EventProcessor → ProcessingPipeline (background task)
    ├── processor_worker.py # Standalone process entry point (for Redis bus)
    └── processors/
        └── persistence_processor.py  # Writes events to EventStore
```

### Key design decisions

1. **Transport-agnostic ingestion.** `IngestionService.ingest()` takes and returns plain domain types. `api/http/telemetry.py` is one concrete transport caller. Adding MQTT means writing a new caller of the same class — not changing the ingestion logic.

2. **Immutable aggregates.** `HelmetState` is a `frozen=True` Pydantic model. Every mutation returns a new instance via `model_copy(update={…})`. Safe to hand to WebSocket subscribers without defensive copying.

3. **One bus subscription, many client queues.** `SubscriptionManager` subscribes to the event bus once (important: Redis consumer groups are server-side resources) and fans events to per-client `asyncio.Queue`s with server-side filtering. A slow client never blocks other subscribers.

---

## Domain model

### Telemetry batch (device → gateway)

```python
# POST /v1/telemetry body
{
  "helmet_id": "helmet-01",       # [A-Za-z0-9][A-Za-z0-9_-]{0,63}
  "sequence": 42,                 # monotonically increasing per helmet
  "sent_at": "2026-07-12T10:30:00Z",  # ISO 8601, UTC
  "readings": [
    {
      "sensor_type": "imu",
      "timestamp": "2026-07-12T10:30:00Z",
      "value": {
        "accel_x_g": 0.03,
        "accel_y_g": -0.01,
        "accel_z_g": 1.02,
        "gyro_x_dps": 1.5,
        "gyro_y_dps": -0.2,
        "gyro_z_dps": 0.1
      }
    }
    // … more readings; min 1 per batch
  ]
}
```

### Sensor types (extensible registry)

| `sensor_type` | Physical sensor | Arduino test sketch | Value fields |
|---------------|----------------|---------------------|--------------|
| `imu` | MPU-6050 | `mpu_test.ino` | `accel_x_g`, `accel_y_g`, `accel_z_g`, `gyro_x_dps`, `gyro_y_dps`, `gyro_z_dps` |
| `gas_lpg` | MQ-2 | `MQ2_test.ino` | `adc_raw` (0–1023) |
| `carbon_monoxide` | MQ-7 | `MQ7_test.ino` | `adc_raw` (0–1023) |
| `environment` | DHT-22 | `dht22_test.ino` | `temperature_c`, `humidity_pct`, `heat_index_c` |
| `sound_level` | Sound sensor | `sound_sensor_test.ino` | `adc_raw` (0–1023) |

Adding a new sensor means: add a `SensorType` enum member, add a value model, register a `SensorSpec` in `domain/telemetry/sensors.py`. Nothing else in the pipeline changes — the registry is the Open/Closed extension point.

### Helmet state (aggregate)

```python
# Returned by GET /v1/helmets/{helmet_id}
{
  "helmet_id": "helmet-01",
  "status": "online",                    # "online" | "offline"
  "first_seen_at": "2026-07-12T08:00:00Z",
  "last_seen_at": "2026-07-12T10:30:00Z",
  "last_sequence": 42,
  "latest_readings": {
    "imu": { … },                        # most recent per sensor type
    "environment": { … }
  }
}
```

Status is **telemetry-derived**: "online" means we received a batch recently enough (staleness threshold: 30 s). There is no separate heartbeat/LWT signal. A background sweep (`DeviceRegistryService.sweep_offline`) transitions stale helmets to "offline".

### Event taxonomy

| `event_type` | Emitted when | Severity |
|-------------|-------------|----------|
| `telemetry.received` | A valid batch is accepted | `info` |
| `telemetry.validation_failed` | A batch fails validation | `warning` |
| `helmet.online` | A helmet transitions to online | `info` |
| `helmet.offline` | A helmet is swept as stale | `warning` |
| `ml.ppe_detection` | PPE detection returns a result | `info`/`warning`/`critical` |
| `ml.result` | Any other ML service outputs data | `info` |

### Validation rules

Every batch is validated by `domain/telemetry/validation.py` before state mutation:

- **Helmet ID**: `[A-Za-z0-9][A-Za-z0-9_-]{0,63}` — safe as an MQTT topic segment, URL path segment, and dict key.
- **Sequence number**: must be strictly greater than the previous accepted sequence for that helmet (no duplicates, no reordering).
- **Clock skew**: `sent_at` must be within ±30 s (configurable) of server UTC.
- **Sensor values**: each field must fall within `SensorSpec.field_bounds` (e.g. IMU acceleration between -16g and +16g, ADC raw between 0 and 1023).

Rejected batches are **not** applied to state but do emit a `telemetry.validation_failed` event for observability.

---

## API surface

### REST (JSON)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/telemetry` | Ingest one telemetry batch. Returns `202` (accepted) or `422` (rejected with issues list). |
| `GET` | `/v1/helmets` | List all known helmets. |
| `GET` | `/v1/helmets/{helmet_id}` | Get one helmet's real-time state. `404` if never seen. |
| `GET` | `/v1/events` | Query event history. Filters: `helmet_id`, `event_type`, `since` (ISO 8601), `limit` (default 50). |
| `GET` | `/v1/helmets/{helmet_id}/events` | Same as `/v1/events` scoped to one helmet. |
| `POST` | `/v1/detections/ppe` | Forward an image frame for PPE detection (calls the PPE ML service). |
| `GET` | `/v1/status` | Aggregated health of all dependent ML services. |

### WebSocket

| Path | Description |
|------|-------------|
| `GET /v1/ws` | Persistent bi-directional connection for real-time event streaming. |

**Client → Server** (JSON, sendable any time after connect):

```json
{"action": "subscribe", "filter": {"helmet_ids": ["helmet-01"], "event_types": ["telemetry.received", "ml.ppe_detection"], "min_severity": "warning"}}
```

Every filter field is optional — omit or set to `null` to match everything. Send a new `subscribe` message any time to update the filter; the next matching event respects it immediately.

**Server → Client** (JSON, pushed as events arrive):

| `type` | When | Payload |
|--------|------|---------|
| `"snapshot"` | Immediately after connect | `{"helmets": […]}` — current helmet roster |
| `"event"` | A matching domain event is published | `{"event": {…}}` — the full event envelope |
| `"heartbeat"` | No events for 20 s | `{}` — keep-alive |
| `"error"` | Client sent a malformed message | `{"detail": "…"}` |

The WebSocket runs **two concurrent tasks per connection** — a reader (parses `subscribe` messages) and a writer (drains the per-client queue with heartbeat fallback). A slow reader never blocks the writer, and vice versa.

---

## How devices connect

### MQTT (helmets — primary transport)

```
[Arduino UNO Q helmet]
        │
        │  WiFi  PUBLISH safeguard/telemetry/{id}  QoS 1
        │  LWT   PUBLISH safeguard/status/{id}     QoS 0
        ▼
[Mosquitto :1883]
        │  gateway subscribes
        ▼
[Gateway :8080]
        │
        ├── MqttIngestionAdapter → IngestionService.ingest(batch)
        ├── MqttPresenceAdapter  → DeviceRegistryService.mark_offline(id)
        ├── validate + update HelmetState
        ├── publish TelemetryReceivedEvent → event bus
        │       │
        │       ├── PersistenceProcessor → Postgres
        │       └── SubscriptionManager → WebSocket fan-out → dashboard
        │
        ▼
[Dashboard :3000]
   real-time WebSocket updates
```

Enabled by setting `MQTT_BROKER_HOST` (to `mqtt` in Compose, `mosquitto` in K8s).
Disabled by leaving it empty — gateway runs HTTP-only without any code change.

### HTTP (alternative / testing)

```
[Any HTTP client / seed script]
        │  POST /v1/telemetry  (JSON body: TelemetryBatch)
        ▼
[Gateway :8080]
        │  same IngestionService.ingest() path as MQTT
        ▼
  [same pipeline as above]
```

`IngestionService` is transport-agnostic — both transports call the same method.
HTTP remains useful for tooling, the `scripts/seed.py` seeder, and environments
without a broker.

### Firmware contract

`helmet/helmet_firmware.ino` implements the full MQTT loop. Key requirements:

1. Connect to WiFi.
2. Set LWT on `safeguard/status/{helmet_id}` → `{"status":"offline"}` (retain=true).
3. Publish `{"status":"online"}` to `safeguard/status/{helmet_id}` on connect.
4. Subscribe to `safeguard/command/{helmet_id}/#` for gateway commands.
5. Read all sensors; accumulate into a `TelemetryBatch` JSON (see [Domain model](#domain-model)).
6. Publish to `safeguard/telemetry/{helmet_id}` at QoS 1 every `BATCH_INTERVAL_MS`.
7. Increment a monotonic sequence number; use NTP for the UTC `sent_at` timestamp.

See `helmet/README.md` for the library list, pinout, and flash instructions.

---

## MQTT integration

### Why MQTT

MQTT is the right transport for the helmet fleet because:

| Concern | HTTP | MQTT |
|---------|---------------|----------------|
| Protocol overhead | ~200–800 bytes of headers per batch | 2-byte fixed header |
| Connection model | Request-response (client opens, sends, closes) | Persistent TCP, broker-mediated |
| Power efficiency | TLS handshake per batch | One TLS handshake, then lightweight publishes |
| Intermittent connectivity | No built-in store-and-forward | QoS 1/2, persistent sessions, offline queuing |
| Scale (hundreds of helmets) | Gateway must handle many concurrent HTTP connections | Broker handles fan-in; gateway subscribes to topics |
| Last Will & Testament | N/A | Built-in — helmet disconnect → immediate `offline` event |

### Architectural readiness

The gateway was designed for this from day one. Adding MQTT **touches zero existing domain or application code**. Here is what already exists:

1. **`IngestionService` is transport-agnostic.** Its `ingest()` method takes a `TelemetryBatch` and returns an `IngestResult` — no HTTP, no FastAPI. `api/http/telemetry.py` is one caller. An MQTT subscriber becomes a second caller.

2. **`parse_helmet_id()`** (`domain/common/identifiers.py`) exists specifically "for extracting a helmet ID from an MQTT topic" (see its docstring). The helmet ID charset was chosen to be safe as an MQTT topic segment.

3. **The event bus already supports Redis.** With Redis backing, multiple gateway replicas (K8s runs 2) share one event stream — an MQTT subscriber on instance A publishes an event that instance B's WebSocket subscribers see.

4. **The `ProcessingPipeline` already runs as a background asyncio task.** An MQTT subscriber is just another asyncio coroutine started in the same lifespan, calling the same `IngestionService`.

### Topic hierarchy (proposed)

The canonical MQTT topic structure, consistent with the existing domain model:

```
safeguard/                                   ← root
├── telemetry/{helmet_id}                    ← device → gateway: publish TelemetryBatch
│   e.g. safeguard/telemetry/helmet-01
│
├── command/{helmet_id}/config               ← gateway → device: push config changes
│   e.g. safeguard/command/helmet-01/config
│
├── command/{helmet_id}/ota                  ← gateway → device: firmware update trigger
│   e.g. safeguard/command/helmet-01/ota
│
└── status/{helmet_id}                       ← device → gateway (optional): LWT / heartbeat
    e.g. safeguard/status/helmet-01
```

**Telemetry topic payload** — exactly a JSON `TelemetryBatch`, same as the HTTP body today:

```json
{
  "helmet_id": "helmet-01",
  "sequence": 42,
  "sent_at": "2026-07-12T10:30:00Z",
  "readings": [ … ]
}
```

The `helmet_id` in the topic segment is cross-checked against the `helmet_id` in the JSON payload by `parse_helmet_id()` — a mismatch is a validation rejection.

### Authentication & security

| Layer | Mechanism |
|-------|----------|
| Transport | TLS 1.3 (broker enforces; devices present client certificate or username/password) |
| Client auth | Per-device username/password or X.509 client certificates provisioned at manufacturing |
| Topic ACL | Each device can `PUBLISH` only `safeguard/telemetry/{its_own_id}` and `safeguard/status/{its_own_id}`; `SUBSCRIBE` only `safeguard/command/{its_own_id}/#` |
| Gateway auth | The gateway connects as a privileged client with publish/subscribe access to all topics |

Broker choice: **EMQX** or **Mosquitto** (both support TLS, ACLs, and clustering). For K8s, EMQX has a well-maintained operator.

### QoS & delivery guarantees

| Topic | QoS | Rationale |
|-------|-----|-----------|
| `telemetry/{id}` | **QoS 1** (at least once) | The gateway's sequence-number deduplication handles duplicates. No telemetry batch is silently lost. |
| `command/{id}/#` | **QoS 1** | Config/OTA commands must reach the device. |
| `status/{id}` | **QoS 0** (at most once) | LWT heartbeats are low-value individually; missing a few is fine. |

The gateway already deduplicates by sequence number (`device_state_manager.py` checks `batch.sequence > previous_sequence`) — QoS 1 duplicates are handled without any new code.

### Implementation plan

The integration path, consistent with the existing architecture's design notes:

#### Step 1: Add MQTT dependencies

```toml
# gateway/pyproject.toml
"aiomqtt>=2.0",
```

#### Step 2: Add broker to infrastructure

```yaml
# docker-compose.yml
mqtt:
  image: eclipse-mosquitto:2
  ports:
    - "1883:1883"
    - "9001:9001"   # WebSocket (optional, for browser-based MQTT)
```

```yaml
# k8s/ — new manifest
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mosquitto
  namespace: safeguard
spec:
  replicas: 1
  …
```

#### Step 3: Implement `MqttIngestionAdapter`

A new module `gateway/src/gateway/infrastructure/mqtt/adapter.py`:

```python
# Pseudocode — follows the exact same pattern as api/http/telemetry.py
class MqttIngestionAdapter:
    def __init__(self, ingestion_service: IngestionService, broker_url: str):
        self._service = ingestion_service
        self._broker_url = broker_url

    async def run(self) -> None:
        async with aiomqtt.Client(self._broker_url) as client:
            await client.subscribe("safeguard/telemetry/+", qos=1)
            async for message in client.messages:
                helmet_id = parse_helmet_id_from_topic(message.topic)
                batch = TelemetryBatch.model_validate_json(message.payload)
                result = await self._service.ingest(batch)
                # QoS 1 ack is automatic; could send nack on validation failure
```

This adapter is started as a **third background task** in `main.py`'s lifespan, alongside `ProcessingPipeline` and `SubscriptionManager`.

#### Step 4: Wire Last Will & Testament

The MQTT client sets an LWT message on `safeguard/status/{helmet_id}` with payload `{"status": "offline"}`. The gateway subscribes to `safeguard/status/+` and calls `DeviceRegistryService.mark_offline()` directly — no polling, no staleness sweep. This replaces the current timer-based offline detection with event-driven transitions.

#### Step 5: Device firmware

The Arduino firmware uses a library like `PubSubClient` (ESP8266) or `AsyncMqttClient` (ESP32) to:

```
1. Connect to WiFi
2. Connect to MQTT broker (TLS, device certificate)
3. Set LWT: safeguard/status/helmet-01 = {"status":"offline"}
4. Publish retained: safeguard/status/helmet-01 = {"status":"online"}
5. Loop:
   a. Read sensors
   b. Build JSON TelemetryBatch
   c. Publish to safeguard/telemetry/helmet-01 (QoS 1)
   d. Sleep per sampling interval
```

---

## Infrastructure & deployment

### Docker Compose (local dev)

```
compose.override.yml (dev)
        │
        ▼
docker-compose.yml (base)
        │
        ├── app          :3000  (Next.js dashboard, hot-reload)
        ├── gateway      :8080  (FastAPI, --reload)
        ├── ppe-detection:8001  (YOLO PPE, --reload)
        ├── fall-detection:8002 (stub, --reload)
        ├── postgres     :5432  (PostgreSQL 16)
        └── redis        :6379  (Redis 7)
```

Key gateway env vars in `docker-compose.yml`:

| Variable | Compose value | Role |
|----------|--------------|------|
| `EVENT_BUS_BACKEND` | `redis` | Multi-service event bus |
| `REDIS_URL` | `redis://redis:6379/0` | |
| `EVENT_STORE_BACKEND` | `postgres` | Durable event history |
| `POSTGRES_DSN` | `postgresql://safeguard:safeguard@postgres:5432/safeguard` | |
| `PPE_URL` | `http://ppe-detection:8000` | Upstream ML |
| `FALL_URL` | `http://fall-detection:8000` | Upstream ML |

### Kubernetes (production)

Deployed via `kubectl apply -k k8s/` into the `safeguard` namespace.

```
[Traefik Ingress]
        │
        ├── snapdragon.upayan.dev        → app:3000          (dashboard)
        ├── api-snapdragon.upayan.dev    → gateway:8080      (API)
        ├── ppe-snapdragon.upayan.dev    → ppe-detection:8000
        └── fall-snapdragon.upayan.dev   → fall-detection:8000
```

**Gateway Deployment** (`k8s/gateway-deployment.yaml`):

| Setting | Value | Rationale |
|---------|-------|-----------|
| `replicas` | 2 | High availability |
| `strategy` | `RollingUpdate`, `maxUnavailable: 0` | Zero-downtime deploys |
| `resources.requests` | 128 Mi mem, 100 m CPU | Conservative baseline |
| `resources.limits` | 256 Mi mem, 500 m CPU | Burst headroom |
| `readinessProbe` | `GET /ready` every 10 s | Gates traffic until background tasks + event bus are up |
| `livenessProbe` | `GET /health` every 30 s | Restarts hung processes |
| `securityContext` | `runAsNonRoot: true`, `runAsUser: 1000`, `drop: [ALL]` | Least privilege |
| `envFrom` | `configMapRef: safeguard-config` + `secretRef: safeguard-secrets` (optional) | |

Config is split across two resources:

- **ConfigMap** (`safeguard-config`): non-sensitive values — `LOG_LEVEL`, `EVENT_BUS_BACKEND`, `REDIS_URL`, `POSTGRES_DSN` (with `$(POSTGRES_PASSWORD)` substitution), ML service URLs.
- **Secret** (`safeguard-secrets`, optional): `POSTGRES_PASSWORD`, `HF_TOKEN`. Created manually; excluded from kustomization to prevent overwrites.

**Other K8s resources** (all in `safeguard` namespace):

| Resource | Purpose |
|----------|---------|
| `app-deployment.yaml` | Next.js dashboard (RollingUpdate) |
| `ppe-deployment.yaml` | PPE detection (Recreate — single GPU) |
| `fall-deployment.yaml` | Fall detection (RollingUpdate) |
| `postgres-deployment.yaml` | PostgreSQL 16 (Recreate, PVC) |
| `redis-deployment.yaml` | Redis 7 (Recreate, **no PVC** — stream is ephemeral; Postgres is the durable record) |
| `ingress.yaml` | Traefik ingress with host-based routing |
| `certificate.yaml` | cert-manager TLS via Cloudflare DNS-01 (`letsencrypt-cloudflare` ClusterIssuer) |
| `namespace.yaml` | `safeguard` namespace |
| `*-service.yaml` | ClusterIP services for each deployment |
| `*-pvc.yaml` | PersistentVolumeClaims for Postgres + logs |

---

## Event pipeline

Every accepted telemetry batch flows through this path:

```
POST /v1/telemetry  (or MQTT subscriber, in the future)
        │
        ▼
IngestionService.ingest(batch)
        │
        ├── validate_batch(batch, previous_sequence, max_clock_skew, now)
        │       │
        │       ├── passes → DeviceStateManager.apply_batch(batch)
        │       │                │
        │       │                └── HelmetState.apply_batch(batch) → new HelmetState
        │       │
        │       └── fails  → publish ValidationFailedEvent → return 422 / nack
        │
        ├── publish TelemetryReceivedEvent → EventBus
        │
        ▼
EventBus
        │
        ├── ProcessingPipeline (background asyncio task)
        │       │
        │       └── PersistenceProcessor → EventStore.insert(event)
        │              (InMemoryEventStore | SQLiteEventStore | PostgresEventStore)
        │
        └── SubscriptionManager (background asyncio task)
                │
                ├── filter per client (helmet_ids, event_types, min_severity)
                ├── enqueue into bounded asyncio.Queue (default 100)
                └── WebSocket writer drains queue → client
```

---

## Real-time streaming (WebSocket)

The `GET /v1/ws` endpoint is the live feed for dashboards. Key behaviors:

- **Snapshot on connect**: the client immediately receives the current helmet roster (`SnapshotMessage`) so the UI has something to render before the first live event.
- **Server-side filtering**: clients send `SubscribeMessage` to declare what they want. The `SubscriptionManager` applies the filter in-process — only matching events enter the client's queue.
- **Bounded queues** (default 100 events): `INFO`/`WARNING` events are dropped when a client's queue is full — the client falls behind but never blocks other subscribers. `CRITICAL` events are never dropped; a full queue evicts its own oldest entry to make room instead.
- **Heartbeat** every 20 s of silence, so load balancers and proxies don't close idle connections.
- **Per-connection concurrency**: reader task (parse incoming `subscribe` messages) and writer task (drain queue → WebSocket) run independently.

---

## Operational endpoints

| Endpoint | Method | Response | Used by |
|----------|--------|----------|---------|
| `/health` | `GET` | `{"status":"ok"}` 200 | K8s liveness probe, Docker HEALTHCHECK |
| `/ready` | `GET` | `{"status":"ok"}` 200 or 503 | K8s readiness probe |
| `/metrics` | `GET` | Prometheus text format | Prometheus scrape |

`/ready` returns 503 until all background tasks (`ProcessingPipeline`, `SubscriptionManager`) are running, and again if the Redis event bus backend becomes unreachable. This gates traffic in K8s — the Service won't route to a pod that hasn't finished starting or has lost its Redis connection.

`/metrics` exposes:

- `http_requests_total{method, path, status}` — counter
- `http_request_duration_seconds{method, path}` — histogram
- `ws_connections` — gauge (current WebSocket connection count)

---

## Summary

MQTT is implemented. Both HTTP and MQTT transports are live simultaneously.
The transport-agnostic `IngestionService`, MQTT-safe `HelmetId` charset,
`parse_helmet_id()`, and Redis Streams event bus were all built with MQTT in mind.

| What was added | File |
|----------------|------|
| Mosquitto broker | `gateway/mosquitto/mosquitto.conf`, `docker-compose.yml`, `k8s/mosquitto-*.yaml` |
| MQTT config | `config.py` — `mqtt_broker_host/port/username/password/topic_prefix` |
| Ingestion adapter | `infrastructure/mqtt/adapter.py` — `MqttIngestionAdapter` |
| Presence adapter | `infrastructure/mqtt/presence.py` — `MqttPresenceAdapter` (LWT → offline) |
| Command publisher | `infrastructure/mqtt/command_publisher.py` — `MqttCommandPublisher` |
| Registry method | `application/device_registry.py` — `mark_offline(helmet_id)` |
| Lifespan wiring | `bootstrap.py` + `main.py` — optional background tasks |
| Firmware | `helmet/helmet_firmware.ino` — full WiFi+MQTT loop (was a stub) |
| Tests | `tests/gateway/infrastructure/test_mqtt_adapter.py` (7 unit) + e2e extension |

HTTP remains available as a parallel transport for tooling and environments
without a broker. Zero existing domain, application, or API code changed.
