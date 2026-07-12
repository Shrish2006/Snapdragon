# Device Connectivity Plan

Covers transport selection for every electronic device in SafeGuard, the full
MQTT integration design, and a phased implementation plan with file-level
granularity.

---

## Table of Contents

- [Transport decisions](#transport-decisions)
- [System architecture](#system-architecture)
- [MQTT design](#mqtt-design)
  - [Topic hierarchy](#topic-hierarchy)
  - [Payload contracts](#payload-contracts)
  - [QoS & delivery guarantees](#qos--delivery-guarantees)
  - [Last Will & Testament](#last-will--testament)
  - [Authentication & ACLs](#authentication--acls)
- [Gateway-side changes](#gateway-side-changes)
- [Firmware plan](#firmware-plan)
- [Implementation phases](#implementation-phases)
- [Testing checkpoints](#testing-checkpoints)

---

## Transport decisions

| Device | Protocol | Rationale |
|--------|----------|-----------|
| **Arduino UNO Q helmet** | **MQTT** | Constrained device: 2 KB SRAM. PubSubClient library is 5–10 byte packet overhead vs 200+ byte HTTP headers. One TLS handshake for the session lifetime (not per-batch). WiFi drops gracefully — broker-side persistent session queues batches until reconnect. Built-in LWT replaces the current timer-based offline sweep with event-driven detection. Bi-directional: subscribe to `command/` topics for on-helmet buzzer alerts, config updates, OTA triggers. |
| **Next.js dashboard** | **WebSocket** ✓ already done | Native browser API; no extra library. Gateway already implements `GET /v1/ws` with server-side filtering, snapshot on connect, and heartbeat. |
| **Android app** | **WebSocket** ✓ same endpoint | Connects to the same `GET /v1/ws`. Standard Android `OkHttp WebSocket` or Ktor client — trivial integration. No protocol changes needed on the gateway side. |
| **PPE camera** | **HTTP** ✓ already done | Not a remote device — OpenCV reads the local USB camera inside the `ppe-detection` container. The gateway calls `POST {PPE_URL}/detect`. No network topology change needed. |

**Decision rule:**
- Embedded / battery-powered / intermittently-connected → **MQTT**.
- Browser / mobile app consuming real-time server-push → **WebSocket**.
- Synchronous request-response to a sidecar service → **HTTP**.

---

## System architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Helmet (Arduino UNO Q)                                              │
│  MPU-6050 · MQ-2 · MQ-7 · DHT-22 · Sound sensor                    │
│                                                                      │
│  PubSubClient (WiFi)                                                 │
│   PUBLISH  safeguard/telemetry/{helmet_id}  QoS 1                   │
│   PUBLISH  safeguard/status/{helmet_id}     QoS 0  (LWT + online)   │
│   SUBSCRIBE safeguard/command/{helmet_id}/+ QoS 1                   │
└─────────────────────┬──────────────────────────────┬────────────────┘
                      │ MQTT :1883 (TLS :8883)        │ commands back
                      ▼                               │
           ┌──────────────────────┐                   │
           │  Mosquitto Broker    │ ◄─────────────────┘
           │  :1883 / :8883       │
           └──────────┬───────────┘
                      │ aiomqtt subscribe
                      ▼
           ┌──────────────────────────────────────────────────────────┐
           │  Gateway (FastAPI :8080)                                  │
           │                                                           │
           │  MqttIngestionAdapter   ─► IngestionService.ingest()     │
           │  MqttPresenceAdapter    ─► DeviceRegistryService         │
           │  MqttCommandPublisher   ◄─ (future: alert triggers)      │
           │                                                           │
           │  EventBus (Redis Streams  gateway:events)                │
           │    │  group: processing  ─► PersistenceProcessor         │
           │    │                          ─► PostgresEventStore       │
           │    └  group: websocket   ─► SubscriptionManager          │
           │                               ─► per-client queues       │
           │                                  ─► GET /v1/ws           │
           └──────────────────────────┬───────────────────────────────┘
                                      │ WebSocket
                     ┌────────────────┴──────────────────┐
                     │                                   │
              ┌──────┴──────┐                   ┌────────┴──────┐
              │  Next.js    │                   │  Android App  │
              │  dashboard  │                   │               │
              │  :3000      │                   │               │
              └─────────────┘                   └───────────────┘
```

---

## MQTT design

### Topic hierarchy

```
safeguard/
├── telemetry/{helmet_id}
│   Helmet PUBLISHES, gateway SUBSCRIBES
│   Payload: TelemetryBatch JSON (same schema as POST /v1/telemetry)
│   QoS: 1 (at-least-once; duplicate rejection is handled by sequence number)
│   Retain: false
│
├── status/{helmet_id}
│   Helmet PUBLISHES (LWT + explicit online/offline), gateway SUBSCRIBES
│   Payload: {"status": "online"} | {"status": "offline"}
│   QoS: 0  (heartbeat — missing one is not critical)
│   Retain: true  (broker caches last known status per helmet)
│
└── command/{helmet_id}/{command}
    Gateway PUBLISHES, helmet SUBSCRIBES
    Payload: command-specific JSON
    QoS: 1
    Retain: false
    Commands:
      alert   → {"buzzer": true, "duration_ms": 3000}
      config  → {"max_clock_skew_seconds": 30, "sample_interval_ms": 500}
      ota     → {"url": "https://…/firmware.bin", "sha256": "…"}
```

The `{helmet_id}` segment uses the same `[A-Za-z0-9][A-Za-z0-9_-]{0,63}` pattern enforced by `domain/common/identifiers.py` — validated by `parse_helmet_id()` when extracting from a topic.

### Payload contracts

**`safeguard/telemetry/{helmet_id}`** — identical to the existing HTTP body:

```json
{
  "helmet_id": "helmet-01",
  "sequence": 42,
  "sent_at": "2026-07-12T10:30:00Z",
  "readings": [
    {
      "sensor_type": "imu",
      "timestamp": "2026-07-12T10:30:00Z",
      "value": {
        "accel_x_g": 0.03, "accel_y_g": -0.01, "accel_z_g": 1.02,
        "gyro_x_dps": 1.5, "gyro_y_dps": -0.2, "gyro_z_dps": 0.1
      }
    }
  ]
}
```

The gateway cross-checks `{helmet_id}` in the topic against `helmet_id` in the payload. A mismatch is logged and the message is dropped.

**`safeguard/status/{helmet_id}`** — LWT payload the broker sends on disconnect:

```json
{"status": "offline"}
```

Helmet publishes `{"status": "online"}` with `retain=true` immediately after connecting.

### QoS & delivery guarantees

| Topic | QoS | Why |
|-------|-----|-----|
| `telemetry/{id}` | 1 (at-least-once) | Sequence-number deduplication in `DeviceStateManager` handles re-deliveries at zero cost. No batch is silently lost. |
| `status/{id}` | 0 (at-most-once) | Individual LWT heartbeats are low-value. The offline sweep (`DeviceRegistryService.sweep_offline`) is the safety net. |
| `command/{id}/+` | 1 (at-least-once) | Alerts and config changes must reach the device. Helmet firmware must handle duplicate commands idempotently (buzzer re-trigger is safe; config overwrite is idempotent). |

### Last Will & Testament

LWT replaces the current 60-second staleness sweep with event-driven presence for most failures:

| Scenario | Old (sweep) | New (LWT + sweep) |
|----------|-------------|-------------------|
| WiFi drop | Detected after 60 s poll | Broker sends LWT immediately on TCP keepalive timeout (~30 s configurable) |
| Clean disconnect | Same 60 s | Helmet publishes `{"status":"offline"}` then disconnects → LWT fires immediately |
| Battery out | 60 s | LWT fires within TCP keepalive window |
| Gateway restart | State lost (in-memory only) | Retained `status` topic re-read on re-subscribe |

The `MqttPresenceAdapter` subscribes to `safeguard/status/+` and calls `DeviceRegistryService.mark_offline(helmet_id)` directly — no timer needed.

### Authentication & ACLs

**Broker: Mosquitto 2.x**

```
# mosquitto.conf
listener 1883
listener 8883
certfile  /certs/broker.crt
keyfile   /certs/broker.key
cafile    /certs/ca.crt
require_certificate false   # username/password auth (simpler for Arduino)
allow_anonymous false
acl_file /etc/mosquitto/acl.conf
password_file /etc/mosquitto/passwd
```

```
# acl.conf
# Gateway: full access
user gateway
topic readwrite safeguard/#

# Per-device: publish own telemetry/status only; subscribe own commands only
# Pattern: %u expands to the connecting client's MQTT username
user helmet-01
topic write safeguard/telemetry/helmet-01
topic write safeguard/status/helmet-01
topic read  safeguard/command/helmet-01/#

# … repeat per helmet, or use a pattern-based ACL plugin
```

For hackathon scope: shared `helmet` username + per-device ACL is acceptable. For production with hundreds of helmets: use EMQX's built-in HTTP auth/ACL plugin driven by a database.

---

## Gateway-side changes

### New configuration (`config.py`)

```python
# -- MQTT transport (optional — disabled when mqtt_broker_url is empty)
mqtt_broker_url: str = ""
"""e.g. 'mqtt://mosquitto:1883'. Empty string disables the MQTT adapter.
Only read when non-empty."""
mqtt_username: str = "gateway"
mqtt_password: str = ""
mqtt_topic_prefix: str = "safeguard"
```

MQTT is **opt-in**: an empty `MQTT_BROKER_URL` leaves the gateway in pure HTTP mode. This means the change is fully backwards-compatible — existing dev environments without a broker keep working.

### New infrastructure modules

```
gateway/src/gateway/infrastructure/mqtt/
├── __init__.py
├── adapter.py            MqttIngestionAdapter
│                           subscribes to safeguard/telemetry/+
│                           parses topic → helmet_id via parse_helmet_id()
│                           parses payload → TelemetryBatch
│                           calls IngestionService.ingest(batch)
│
├── presence.py           MqttPresenceAdapter
│                           subscribes to safeguard/status/+
│                           on {"status":"offline"} → DeviceRegistryService.mark_offline()
│                           on {"status":"online"}  → no-op (telemetry arrival handles this)
│
└── command_publisher.py  MqttCommandPublisher
                            publish(helmet_id, command, payload) → MQTT QoS 1
                            used by future alert-dispatch use-case
```

**`adapter.py` sketch** (no pseudocode — this is the actual intended implementation):

```python
import json
import logging

import aiomqtt

from gateway.application.ingestion_service import IngestionService
from gateway.domain.common.identifiers import parse_helmet_id
from gateway.domain.common.errors import InvalidHelmetIdError
from gateway.domain.telemetry.models import TelemetryBatch

logger = logging.getLogger("gateway.mqtt.ingestion")


class MqttIngestionAdapter:
    def __init__(
        self,
        ingestion_service: IngestionService,
        *,
        broker_url: str,
        username: str,
        password: str,
        topic_prefix: str = "safeguard",
    ) -> None:
        self._service = ingestion_service
        self._broker_url = broker_url
        self._username = username
        self._password = password
        self._telemetry_topic = f"{topic_prefix}/telemetry/+"

    async def run(self) -> None:
        # aiomqtt auto-reconnects on network failure
        async with aiomqtt.Client(
            self._broker_url,
            username=self._username,
            password=self._password,
        ) as client:
            await client.subscribe(self._telemetry_topic, qos=1)
            async for message in client.messages:
                await self._handle(message)

    async def _handle(self, message: aiomqtt.Message) -> None:
        # Topic: safeguard/telemetry/{helmet_id}
        topic_parts = str(message.topic).split("/")
        raw_id = topic_parts[-1] if len(topic_parts) >= 3 else ""
        try:
            topic_helmet_id = parse_helmet_id(raw_id)
        except InvalidHelmetIdError:
            logger.warning("mqtt: invalid helmet_id in topic %s", message.topic)
            return

        try:
            batch = TelemetryBatch.model_validate_json(message.payload)
        except Exception:
            logger.warning("mqtt: malformed payload from topic %s", message.topic)
            return

        if batch.helmet_id != topic_helmet_id:
            logger.warning(
                "mqtt: topic helmet_id %r != payload helmet_id %r — dropped",
                topic_helmet_id, batch.helmet_id,
            )
            return

        await self._service.ingest(batch)
```

**`presence.py` sketch**:

```python
class MqttPresenceAdapter:
    def __init__(
        self,
        registry: DeviceRegistryService,
        *,
        broker_url: str,
        username: str,
        password: str,
        topic_prefix: str = "safeguard",
    ) -> None:
        ...

    async def run(self) -> None:
        async with aiomqtt.Client(...) as client:
            await client.subscribe(f"{self._prefix}/status/+", qos=0)
            async for message in client.messages:
                payload = json.loads(message.payload)
                if payload.get("status") == "offline":
                    topic_parts = str(message.topic).split("/")
                    helmet_id = parse_helmet_id(topic_parts[-1])
                    await self._registry.mark_offline(helmet_id)
```

### Changes to existing files

**`pyproject.toml`**: add `"aiomqtt>=2.0"` to `dependencies`.

**`config.py`**: add the four `mqtt_*` fields above.

**`bootstrap.py`**: `build_container()` conditionally creates `MqttIngestionAdapter` and `MqttPresenceAdapter` when `settings.mqtt_broker_url` is non-empty. Passes `settings.mqtt_username`, `settings.mqtt_password`, `settings.mqtt_topic_prefix`. Neither adapter is added to `Container` (they run independently, not injected into API routes).

**`main.py`**: `_lifespan` already uses `_run_background_tasks(*coroutines)`. Extend it to optionally add the MQTT adapter coroutines:

```python
# in _lifespan, after building the container:
tasks: list[Callable[[], Awaitable[None]]] = [
    container.processing_pipeline.run,
    container.subscription_manager.run,
]
if container.mqtt_ingestion_adapter is not None:
    tasks.append(container.mqtt_ingestion_adapter.run)
if container.mqtt_presence_adapter is not None:
    tasks.append(container.mqtt_presence_adapter.run)

async with _run_background_tasks(*tasks):
    yield
```

The `Container` dataclass gains two optional fields:

```python
@dataclass(frozen=True, slots=True)
class Container:
    ...
    mqtt_ingestion_adapter: MqttIngestionAdapter | None = None
    mqtt_presence_adapter:  MqttPresenceAdapter  | None = None
```

### Broker config files

```
gateway/mosquitto/
├── mosquitto.conf    # listener, auth, ACL, logging
├── acl.conf          # topic-level ACLs per username
└── passwd            # (gitignored) hashed credentials; use mosquitto_passwd to generate
```

---

## Firmware plan

**File**: `helmet/helmet_firmware.ino`

**Libraries required** (install via Arduino Library Manager):
- `WiFiNINA` or `WiFi` (board-specific; Arduino UNO Q WiFi uses `WiFiNINA`)
- `PubSubClient` (MQTT — Nick O'Leary, v2.8+)
- `ArduinoJson` (JSON serialisation, v7+)
- `MPU6050` (MPU-6050 IMU)
- `DHT sensor library` (DHT-22)

**Loop design**:

```
Setup:
  1. Init all sensors
  2. Connect WiFi (block until connected)
  3. Set MQTT LWT: safeguard/status/{HELMET_ID} → {"status":"offline"}, retain=true
  4. Connect MQTT broker (block until connected)
  5. Publish: safeguard/status/{HELMET_ID} → {"status":"online"}, retain=true
  6. Subscribe: safeguard/command/{HELMET_ID}/+
  7. sequence = 0

Loop (runs every BATCH_INTERVAL_MS):
  1. mqttClient.loop()  ← process incoming command messages
  2. Reconnect WiFi + MQTT if dropped (non-blocking check)
  3. Read sensors into local structs
  4. Build JSON:
       {"helmet_id":"...", "sequence":seq++, "sent_at":"<UTC>", "readings":[...]}
  5. Publish to safeguard/telemetry/{HELMET_ID}, QoS 1
  6. Delay(BATCH_INTERVAL_MS)

Callback (incoming command):
  topic = safeguard/command/{HELMET_ID}/alert → trigger buzzer
  topic = safeguard/command/{HELMET_ID}/config → update local params
```

**Key constants**:

```cpp
const char* HELMET_ID      = "helmet-01";   // unique per device
const char* WIFI_SSID      = "...";
const char* WIFI_PASS      = "...";
const char* MQTT_HOST      = "192.168.x.x"; // or k8s LB / compose hostname
const int   MQTT_PORT      = 1883;          // 8883 for TLS
const char* MQTT_USER      = "helmet-01";
const char* MQTT_PASS      = "...";
const long  BATCH_INTERVAL = 500;           // ms — 2 Hz; sensors fire on own cadence
```

**Clock source**: Arduino UNO Q has no RTC. Use NTP (`WiFiUDP` + `NTPClient` library) to set the epoch once at startup; track elapsed millis for per-reading timestamps. `sent_at` is UTC ISO 8601.

---

## Infrastructure

### Docker Compose addition

```yaml
# docker-compose.yml — add to services:
mqtt:
  image: eclipse-mosquitto:2
  container_name: safeguard-mqtt
  restart: unless-stopped
  networks:
    - safeguard
  ports:
    - "1883:1883"   # MQTT
    - "9001:9001"   # MQTT-over-WebSocket (optional, browser MQTT clients)
  volumes:
    - ./gateway/mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
    - ./gateway/mosquitto/acl.conf:/mosquitto/config/acl.conf:ro
    - ./gateway/mosquitto/passwd:/mosquitto/config/passwd:ro
  healthcheck:
    test: ["CMD", "mosquitto_sub", "-t", "$$SYS/#", "-C", "1", "-i", "healthcheck"]
    interval: 10s
    timeout: 5s
    retries: 3
```

Add `mqtt` to the gateway's `depends_on`:
```yaml
gateway:
  depends_on:
    mqtt:
      condition: service_healthy
    ...
```

Add MQTT env to gateway:
```yaml
gateway:
  environment:
    MQTT_BROKER_URL: mqtt://mqtt:1883
    MQTT_USERNAME: gateway
    MQTT_PASSWORD: ${MQTT_GATEWAY_PASSWORD:-changeme}
    MQTT_TOPIC_PREFIX: safeguard
```

### Kubernetes additions

Two new manifests:

**`k8s/mosquitto-deployment.yaml`**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mosquitto
  namespace: safeguard
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: mosquitto
  template:
    metadata:
      labels:
        app.kubernetes.io/name: mosquitto
    spec:
      containers:
        - name: mosquitto
          image: eclipse-mosquitto:2
          ports:
            - containerPort: 1883
          volumeMounts:
            - name: config
              mountPath: /mosquitto/config
          resources:
            requests: { memory: "32Mi", cpu: "50m" }
            limits:   { memory: "64Mi", cpu: "200m" }
          readinessProbe:
            tcpSocket: { port: 1883 }
            initialDelaySeconds: 3
            periodSeconds: 5
      volumes:
        - name: config
          configMap:
            name: mosquitto-config
```

**`k8s/mosquitto-service.yaml`**:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: mosquitto
  namespace: safeguard
spec:
  type: ClusterIP          # internal only; devices hit via NodePort/LB if external
  selector:
    app.kubernetes.io/name: mosquitto
  ports:
    - name: mqtt
      port: 1883
      targetPort: 1883
```

For devices on the physical network (not inside the cluster), expose via `LoadBalancer` or `NodePort` and point `MQTT_HOST` at the cluster's external IP.

**`k8s/kustomization.yaml`** additions:
```yaml
resources:
  - mosquitto-deployment.yaml
  - mosquitto-service.yaml
```

**`k8s/configmap.yaml`** additions:
```yaml
data:
  MQTT_BROKER_URL: "mqtt://mosquitto:1883"
  MQTT_USERNAME: "gateway"
  MQTT_TOPIC_PREFIX: "safeguard"
```

**`k8s/secret.example.yaml`** additions:
```yaml
stringData:
  MQTT_GATEWAY_PASSWORD: "REPLACE_ME"
  MQTT_HELMET_PASSWORD: "REPLACE_ME"
```

---

## Implementation phases

Work is grouped so each phase leaves the system in a working, testable state.

### Phase 1 — Mosquitto broker

**Goal**: running broker; gateway still uses HTTP only.

| # | File | Action |
|---|------|--------|
| 1.1 | `gateway/mosquitto/mosquitto.conf` | Create — listener 1883, password_file, acl_file, logging |
| 1.2 | `gateway/mosquitto/acl.conf` | Create — gateway full access; per-device topic ACLs |
| 1.3 | `gateway/mosquitto/passwd` | Create (gitignored) — `mosquitto_passwd -c passwd gateway` |
| 1.4 | `docker-compose.yml` | Add `mqtt` service with healthcheck |
| 1.5 | `.gitignore` | Add `gateway/mosquitto/passwd` |

**Checkpoint**: `docker compose up mqtt` → `mosquitto_pub -h localhost -t test/1 -m hello -u gateway -P changeme` succeeds.

─────────────────────────────────────────────────

### Phase 2 — Gateway MQTT adapter

**Goal**: gateway ingests telemetry from MQTT topics through the same validation + event pipeline as HTTP.

| # | File | Action |
|---|------|--------|
| 2.1 | `gateway/pyproject.toml` | Add `"aiomqtt>=2.0"` |
| 2.2 | `gateway/src/gateway/config.py` | Add `mqtt_broker_url`, `mqtt_username`, `mqtt_password`, `mqtt_topic_prefix` |
| 2.3 | `gateway/src/gateway/infrastructure/mqtt/__init__.py` | Create (empty) |
| 2.4 | `gateway/src/gateway/infrastructure/mqtt/adapter.py` | Create `MqttIngestionAdapter` |
| 2.5 | `gateway/src/gateway/infrastructure/mqtt/presence.py` | Create `MqttPresenceAdapter` |
| 2.6 | `gateway/src/gateway/infrastructure/mqtt/command_publisher.py` | Create `MqttCommandPublisher` (publish-only, thin wrapper) |

**Checkpoint**: Unit test `MqttIngestionAdapter._handle()` with a mock `IngestionService` — valid message → `ingest()` called; mismatched helmet_id → dropped; malformed JSON → dropped.

─────────────────────────────────────────────────

### Phase 3 — Wire into gateway process

**Goal**: MQTT adapters start automatically when `MQTT_BROKER_URL` is set; nothing changes when it is not.

| # | File | Action |
|---|------|--------|
| 3.1 | `gateway/src/gateway/bootstrap.py` | Add `mqtt_ingestion_adapter: MqttIngestionAdapter \| None` and `mqtt_presence_adapter: MqttPresenceAdapter \| None` to `Container`; build them in `build_container()` when `settings.mqtt_broker_url` is non-empty |
| 3.2 | `gateway/src/gateway/main.py` | Extend `_lifespan` to include MQTT adapter `run()` coroutines alongside `ProcessingPipeline` and `SubscriptionManager` when the adapters are non-`None` |
| 3.3 | `docker-compose.yml` | Add `MQTT_BROKER_URL`, `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_TOPIC_PREFIX` to `gateway` env |
| 3.4 | `gateway/example.env` | Document the four new MQTT vars |

**Checkpoint**: `docker compose up` → `docker compose logs gateway` shows MQTT subscription started. Publish a test batch via `mosquitto_pub` → `GET /v1/helmets` returns the helmet.

─────────────────────────────────────────────────

### Phase 4 — Firmware

**Goal**: Arduino helmet publishes real sensor data over MQTT.

| # | File | Action |
|---|------|--------|
| 4.1 | `helmet/helmet_firmware.ino` | Implement full WiFi + MQTT loop (see [Firmware plan](#firmware-plan)) |
| 4.2 | `helmet/README.md` | Add flashing instructions, library list, `HELMET_ID` / WiFi / broker constants |

**Checkpoint**: Upload firmware → `mosquitto_sub -h localhost -t 'safeguard/telemetry/#' -v` streams live batches. `GET /v1/helmets` shows the helmet online with real sensor readings.

─────────────────────────────────────────────────

### Phase 5 — K8s manifests

**Goal**: production deployment includes Mosquitto with correct config and secrets.

| # | File | Action |
|---|------|--------|
| 5.1 | `k8s/mosquitto-deployment.yaml` | Create |
| 5.2 | `k8s/mosquitto-service.yaml` | Create |
| 5.3 | `k8s/mosquitto-configmap.yaml` | Create — mosquitto.conf + acl.conf as ConfigMap data |
| 5.4 | `k8s/kustomization.yaml` | Add the three new manifests |
| 5.5 | `k8s/configmap.yaml` | Add `MQTT_BROKER_URL`, `MQTT_USERNAME`, `MQTT_TOPIC_PREFIX` |
| 5.6 | `k8s/secret.example.yaml` | Add `MQTT_GATEWAY_PASSWORD`, `MQTT_HELMET_PASSWORD` |

**Checkpoint**: `kubectl apply -k k8s/` → `kubectl get pods -n safeguard` shows mosquitto Running. Helmet (on physical network) connects to `<cluster-lb>:1883` → batches appear in `GET /v1/events`.

─────────────────────────────────────────────────

### Phase 6 — Tests + docs

| # | File | Action |
|---|------|--------|
| 6.1 | `tests/gateway/infrastructure/test_mqtt_adapter.py` | Unit tests: valid message, mismatched topic/payload id, malformed JSON, QoS 1 duplicate (same sequence → `accepted=False` from `IngestionService`) |
| 6.2 | `tests/gateway/test_end_to_end_pipeline.py` | Extend with MQTT ingestion path using an in-process aiomqtt test broker or mock |
| 6.3 | `docs/gateway-mqtt.md` | Already updated (Redis Streams, CRITICAL queue, Redis ephemeral, TLS issuer) — verify references align with new adapter names |

---

## Testing checkpoints (summary)

| Phase | What to run | Expected result |
|-------|-------------|----------------|
| 1 | `docker compose up mqtt` | Broker healthy |
| 1 | `mosquitto_pub -h localhost -t test/1 -m hi -u gateway -P changeme` | No error |
| 2 | `pytest tests/gateway/infrastructure/test_mqtt_adapter.py` | All pass |
| 3 | `docker compose up` then `mosquitto_pub -h localhost -t safeguard/telemetry/h1 -m '{"helmet_id":"h1","sequence":1,"sent_at":"<now>","readings":[...]}' -u helmet-01 -P changeme -q 1` | `GET /v1/helmets` → `[{helmet_id: "h1", status: "online"}]` |
| 3 | `GET /v1/events?event_type=telemetry.received` | Event present |
| 3 | `GET /v1/ws` (wscat) | `snapshot` message includes `h1` |
| 4 | Upload firmware to Arduino | `mosquitto_sub -t 'safeguard/telemetry/#' -v` shows live batches |
| 5 | `kubectl apply -k k8s/` | `kubectl get pods -n safeguard` — mosquitto Running |
| 6 | `pytest tests/gateway/` | All pass |
