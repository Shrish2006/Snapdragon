# SafeGuard Helmet Firmware

Arduino UNO Q firmware that reads onboard sensors and streams telemetry to
the SafeGuard gateway over MQTT.

---

## Hardware

| Component | Role | Pins |
|-----------|------|------|
| Arduino UNO Q (WiFiNINA) | MCU + WiFi | — |
| MPU-6050 | Accelerometer + gyroscope | I2C (SDA/SCL) |
| MQ-2 | LPG / smoke (analog) | A0 |
| MQ-7 | Carbon monoxide (analog) | A1 |
| DHT-22 | Temperature + humidity | D4 |
| Sound sensor | Peak noise level (analog) | A2 |

---

## Required Libraries

Install all via **Arduino IDE → Tools → Manage Libraries**:

| Library | Author | Minimum version |
|---------|--------|----------------|
| `WiFiNINA` | Arduino | latest |
| `PubSubClient` | Nick O'Leary | 2.8 |
| `ArduinoJson` | Benoit Blanchon | 7.0 |
| `Adafruit MPU6050` | Adafruit | 2.2 |
| `Adafruit Unified Sensor` | Adafruit | 1.1 |
| `DHT sensor library` | Adafruit | 1.4 |
| `NTPClient` | Fabrice Weinberg | 3.2 |

---

## Configuration

Edit the **CONFIG** block at the top of `helmet_firmware.ino`:

```cpp
static const char* HELMET_ID = "helmet-01";   // unique per device
static const char* WIFI_SSID = "YOUR_SSID";
static const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
static const char* MQTT_HOST = "192.168.1.100";  // ← set from table below
static const int   MQTT_PORT = 1883;
static const char* MQTT_USER = "helmet-01";       // must equal HELMET_ID in prod
static const char* MQTT_PASS = "";                // blank if allow_anonymous
```

**What to set `MQTT_HOST` to:**

| You are running the stack on… | `MQTT_HOST` | Notes |
|-------------------------------|-------------|-------|
| **Docker Compose, same machine** | `localhost` | Broker port 1883 is forwarded to your host |
| **Docker Compose, Arduino on LAN** | Your PC's LAN IP | e.g. `192.168.1.42` — find with `ipconfig` (Win) / `hostname -I` (Linux) / `ifconfig` (Mac) |
| **Kubernetes, device on cluster network** | `mosquitto.safeguard.svc.cluster.local` | Internal ClusterIP; needs a pod on the cluster or port-forward |
| **Kubernetes, device on physical LAN** | The NodePort/LoadBalancer external IP | `kubectl get svc mosquitto -n safeguard` to find it |


---

## Flashing

1. Open `helmet_firmware.ino` in Arduino IDE.
2. Select **Tools → Board → Arduino UNO Q WiFi**.
3. Select the correct COM/tty port.
4. Click **Upload**.

Monitor output at 115200 baud to confirm WiFi → MQTT connection and batch
publishes.

---

## MQTT topics

| Direction | Topic | QoS | Content |
|-----------|-------|-----|---------|
| Helmet → Gateway | `safeguard/telemetry/{helmet_id}` | 1 | `TelemetryBatch` JSON |
| Helmet → Broker (LWT) | `safeguard/status/{helmet_id}` | 0 | `{"status":"offline"}` (retained) |
| Gateway → Helmet | `safeguard/command/{helmet_id}/alert` | 1 | `{"buzzer":true,"duration_ms":3000}` |
| Gateway → Helmet | `safeguard/command/{helmet_id}/config` | 1 | `{"sample_interval_ms":500}` |

---

## Telemetry batch format

The firmware publishes a JSON object matching the gateway's `TelemetryBatch`
schema on every `BATCH_INTERVAL_MS` (default 500 ms = 2 Hz):

```json
{
  "helmet_id": "helmet-01",
  "sequence": 42,
  "sent_at": "2026-07-12T10:30:00Z",
  "readings": [
    {
      "captured_at": "2026-07-12T10:30:00Z",
      "value": {
        "kind": "imu",
        "accel_x_g": 0.03,
        "accel_y_g": -0.01,
        "accel_z_g": 1.02,
        "accel_magnitude_g": 1.02,
        "gyro_x_dps": 1.5,
        "gyro_y_dps": -0.2,
        "gyro_z_dps": 0.1
      }
    },
    {
      "captured_at": "2026-07-12T10:30:00Z",
      "value": { "kind": "gas_lpg", "adc_raw": 312 }
    },
    {
      "captured_at": "2026-07-12T10:30:00Z",
      "value": { "kind": "carbon_monoxide", "adc_raw": 198 }
    },
    {
      "captured_at": "2026-07-12T10:30:00Z",
      "value": {
        "kind": "environment",
        "temperature_c": 28.4,
        "humidity_pct": 62.1,
        "heat_index_c": 30.2
      }
    },
    {
      "captured_at": "2026-07-12T10:30:00Z",
      "value": { "kind": "sound_level", "adc_raw": 450 }
    }
  ]
}
```

---

## Sensor test sketches

Individual sensor validation sketches (no networking, Serial.print only):

| Sketch | Sensor |
|--------|--------|
| `mpu_test.ino` | MPU-6050 IMU |
| `MQ2_test/MQ2_test.ino` | MQ-2 gas |
| `MQ7_test/MQ7_test.ino` | MQ-7 CO |
| `dht22_test/dht22_test.ino` | DHT-22 temp/humidity |
| `sound_sensor_test/sound_sensor_test.ino` | Sound sensor |
