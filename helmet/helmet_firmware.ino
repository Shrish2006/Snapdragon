/**
 * SafeGuard Helmet Firmware — Arduino UNO Q WiFi
 *
 * Reads all onboard helmet sensors and publishes a TelemetryBatch JSON
 * to the SafeGuard gateway via MQTT every BATCH_INTERVAL_MS.
 *
 * ── MQTT-published sensor types (match gateway SENSOR_REGISTRY) ──────────
 *   MPU-6050  → "imu"              I2C 0x68, SDA/SCL
 *   MQ-2      → "gas_lpg"          A0, 10-bit raw ADC
 *   MQ-7      → "carbon_monoxide"  A1, 10-bit raw ADC
 *   DHT-22    → "environment"      D4, temp / humidity / heat-index
 *   Sound     → "sound_level"      A2, peak ADC over 100 ms window
 *
 * ── Sensors read locally (NOT in MQTT payload) ───────────────────────────
 *   MAX30102  → IR raw value        I2C 0x57 (shared bus; no addr conflict)
 *   FSR       → pressure raw ADC    A3, helmet-worn detection
 *
 *   Reason for exclusion: these sensor kinds are not registered in the
 *   gateway's SENSOR_REGISTRY (sensors.py). Including an unknown "kind"
 *   causes the gateway's Pydantic discriminated union to reject the entire
 *   batch. Readings are logged to Serial for field debugging.
 *
 * ── Required libraries (Arduino IDE → Tools → Manage Libraries) ───────────
 *   WiFiNINA                  Arduino          latest
 *   PubSubClient              Nick O'Leary     ≥ 2.8
 *   ArduinoJson               Benoit Blanchon  ≥ 7.0
 *   Adafruit MPU6050          Adafruit         ≥ 2.2
 *   Adafruit Unified Sensor   Adafruit         ≥ 1.1
 *   DHT sensor library        Adafruit         ≥ 1.4
 *   NTPClient                 Fabrice Weinberg ≥ 3.2
 *   SparkFun MAX3010x Sensor Library  SparkFun ≥ 1.1
 *
 * ── Flash ────────────────────────────────────────────────────────────────
 *   Tools → Board → Arduino UNO Q WiFi, then Upload.
 *   Monitor at 115 200 baud to confirm WiFi → MQTT connection and batch
 *   publishes.
 */

#include <WiFiNINA.h>
#include <WiFiUdp.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <DHT.h>
#include <NTPClient.h>
#include <Wire.h>
#include "MAX30105.h"

// ════════════════════════════════════════════════════════════════════════════
// CONFIG — edit these values per device before flashing
// ════════════════════════════════════════════════════════════════════════════

// Device identity — must match the MQTT username and the gateway's HelmetId
// pattern: [A-Za-z0-9][A-Za-z0-9_-]{0,63}
static const char* HELMET_ID  = "helmet-01";

static const char* WIFI_SSID  = "YOUR_SSID";
static const char* WIFI_PASS  = "YOUR_WIFI_PASSWORD";

// MQTT broker:
//   Production VPS (any internet connection): 138.201.157.147 : 31883
//   Docker Compose, same machine:             localhost        : 1883
//   Docker Compose, Arduino on LAN:           <PC LAN IP>     : 1883
static const char* MQTT_HOST  = "138.201.157.147";
static const int   MQTT_PORT  = 31883;
static const char* MQTT_USER  = "helmet-01";  // must equal HELMET_ID
static const char* MQTT_PASS  = "";           // broker uses anonymous access

// ════════════════════════════════════════════════════════════════════════════
// Pin assignments
// ════════════════════════════════════════════════════════════════════════════

static const uint8_t PIN_MQ2   = A0;  // MQ-2  gas (LPG / smoke)
static const uint8_t PIN_MQ7   = A1;  // MQ-7  carbon monoxide
static const uint8_t PIN_SOUND = A2;  // sound sensor (analog peak)
static const uint8_t PIN_DHT   = 4;   // DHT-22 data
static const uint8_t PIN_FSR   = A3;  // FSR pressure (local log only)

// ════════════════════════════════════════════════════════════════════════════
// Timing and sizing constants
// ════════════════════════════════════════════════════════════════════════════

static const unsigned long BATCH_INTERVAL_MS = 500;    // 2 Hz publish rate
static const unsigned long NTP_SYNC_INTERVAL = 60000;  // NTP re-sync period (ms)
static const unsigned long SOUND_SAMPLE_MS   = 100;    // peak-sample window (ms)

// Worst-case serialised JSON ≈ 750 bytes; MQTT fixed+variable header ≈ 38 bytes.
// Buffer must be large enough for the full PUBLISH packet.
static const uint16_t MQTT_BUF_SIZE = 1024;

// FSR ADC reading above which the helmet is considered worn (fsr_test.ino).
static const int FSR_WORN_THRESHOLD = 90;

// ════════════════════════════════════════════════════════════════════════════
// MQTT topic strings — built once in setup()
// ════════════════════════════════════════════════════════════════════════════

static char TOPIC_TELEMETRY[80];
static char TOPIC_STATUS[80];
static char TOPIC_COMMAND[80];

// ════════════════════════════════════════════════════════════════════════════
// Peripheral instances
// ════════════════════════════════════════════════════════════════════════════

static WiFiClient       netClient;
static PubSubClient     mqtt(netClient);
static WiFiUDP          ntpUdp;
static NTPClient        ntp(ntpUdp, "pool.ntp.org", 0, NTP_SYNC_INTERVAL);
static Adafruit_MPU6050 mpuSensor;
static DHT              dhtSensor(PIN_DHT, DHT22);
static MAX30105         maxSensor;

// ════════════════════════════════════════════════════════════════════════════
// Runtime state
// ════════════════════════════════════════════════════════════════════════════

static uint32_t txSequence  = 0;      // monotonically increasing per device
static uint32_t lastBatchMs = 0;      // millis() of last successful publish
static bool     mpuOk       = false;  // set true when MPU-6050 initialises
static bool     maxOk       = false;  // set true when MAX30102 initialises

// ════════════════════════════════════════════════════════════════════════════
// Utility helpers
// ════════════════════════════════════════════════════════════════════════════

/**
 * Writes an ISO 8601 UTC timestamp ("YYYY-MM-DDTHH:MM:SSZ") for a Unix
 * epoch value into buf.  Valid for all dates in 1970–2099.
 */
static void epochToIso8601(unsigned long epoch, char* buf, size_t len) {
  unsigned long ss   = epoch % 60;
  unsigned long mm   = (epoch / 60) % 60;
  unsigned long hh   = (epoch / 3600) % 24;
  unsigned long days = epoch / 86400;

  int year = 1970;
  for (;;) {
    bool leap = (year % 4 == 0) && (year % 100 != 0 || year % 400 == 0);
    unsigned long diy = leap ? 366UL : 365UL;
    if (days < diy) break;
    days -= diy;
    ++year;
  }
  static const uint8_t DIM[] = {31,28,31,30,31,30,31,31,30,31,30,31};
  bool leap = (year % 4 == 0) && (year % 100 != 0 || year % 400 == 0);
  int month = 0;
  for (; month < 12; ++month) {
    uint8_t d = DIM[month] + (month == 1 && leap ? 1 : 0);
    if (days < d) break;
    days -= d;
  }
  snprintf(buf, len, "%04d-%02d-%02dT%02d:%02d:%02dZ",
           year, month + 1, (int)days + 1, (int)hh, (int)mm, (int)ss);
}

/**
 * Samples the sound sensor ADC continuously for SOUND_SAMPLE_MS and returns
 * the peak (highest) value observed.  Mirrors sound_sensor_test.ino.
 */
static int sampleSoundPeak() {
  int peak = 0;
  unsigned long start = millis();
  while (millis() - start < SOUND_SAMPLE_MS) {
    int v = analogRead(PIN_SOUND);
    if (v > peak) peak = v;
  }
  return peak;
}

/**
 * Publishes a retained status JSON message to TOPIC_STATUS.
 * Used for "online" (on connect) and by the LWT for "offline".
 */
static void publishStatus(const char* statusStr) {
  char buf[32];
  snprintf(buf, sizeof(buf), "{\"status\":\"%s\"}", statusStr);
  mqtt.publish(TOPIC_STATUS, reinterpret_cast<const uint8_t*>(buf),
               strlen(buf), /*retained=*/true);
}

// ════════════════════════════════════════════════════════════════════════════
// MQTT command callback  (gateway → helmet)
// ════════════════════════════════════════════════════════════════════════════

static void onCommand(const char* topic, byte* payload, unsigned int length) {
  JsonDocument cmd;
  if (deserializeJson(cmd, payload, length) != DeserializationError::Ok) return;

  if (strstr(topic, "/alert")) {
    int dur = cmd["duration_ms"] | 1000;
    // Wire a buzzer to a PWM pin and un-comment the line below.
    // tone(9, 2000, dur);
    Serial.print(F("CMD alert "));
    Serial.print(dur);
    Serial.println(F("ms"));
  } else if (strstr(topic, "/config")) {
    Serial.println(F("CMD config (not yet applied)"));
  } else if (strstr(topic, "/ota")) {
    Serial.println(F("CMD ota (not implemented)"));
  }
}

// ════════════════════════════════════════════════════════════════════════════
// Network
// ════════════════════════════════════════════════════════════════════════════

static void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.print(F("WiFi → "));
  Serial.print(WIFI_SSID);
  while (WiFi.begin(WIFI_SSID, WIFI_PASS) != WL_CONNECTED) {
    Serial.print('.');
    delay(3000);
  }
  Serial.print(F(" OK "));
  Serial.println(WiFi.localIP());
}

static void connectMqtt() {
  while (!mqtt.connected()) {
    Serial.print(F("MQTT → "));
    char clientId[40];
    snprintf(clientId, sizeof(clientId), "safeguard-%s", HELMET_ID);

    // LWT: broker broadcasts this payload to TOPIC_STATUS if the TCP session
    // drops without a clean DISCONNECT (power loss, WiFi drop, etc.).
    bool ok = mqtt.connect(
      clientId,
      MQTT_USER, MQTT_PASS,
      TOPIC_STATUS, /*lwt qos*/ 0, /*lwt retain*/ true,
      "{\"status\":\"offline\"}"
    );

    if (ok) {
      Serial.println(F("connected"));
      publishStatus("online");
      mqtt.subscribe(TOPIC_COMMAND, /*qos*/ 1);
    } else {
      Serial.print(F("rc="));
      Serial.print(mqtt.state());
      Serial.println(F(" retry 5s"));
      delay(5000);
    }
  }
}

// ════════════════════════════════════════════════════════════════════════════
// Sensor value structs
// ════════════════════════════════════════════════════════════════════════════

struct ImuData {
  float ax, ay, az, mag;  // g
  float gx, gy, gz;       // deg/s
};

struct EnvData {
  float temp_c;
  float humidity_pct;
  float heat_index_c;
};

// ════════════════════════════════════════════════════════════════════════════
// Sensor read functions
// ════════════════════════════════════════════════════════════════════════════

static ImuData readImu() {
  sensors_event_t a, g, tmp;
  mpuSensor.getEvent(&a, &g, &tmp);

  ImuData d;
  // Adafruit driver returns m/s²; gateway schema requires g (÷ 9.80665).
  d.ax  = a.acceleration.x / 9.80665f;
  d.ay  = a.acceleration.y / 9.80665f;
  d.az  = a.acceleration.z / 9.80665f;
  d.mag = sqrtf(d.ax * d.ax + d.ay * d.ay + d.az * d.az);
  // Adafruit driver returns rad/s; gateway schema requires deg/s (× 180/π).
  d.gx  = g.gyro.x * (180.0f / (float)M_PI);
  d.gy  = g.gyro.y * (180.0f / (float)M_PI);
  d.gz  = g.gyro.z * (180.0f / (float)M_PI);
  return d;
}

static EnvData readEnv() {
  EnvData d;
  d.humidity_pct = dhtSensor.readHumidity();
  d.temp_c       = dhtSensor.readTemperature();
  if (isnan(d.temp_c) || isnan(d.humidity_pct)) {
    d.heat_index_c = NAN;
  } else {
    d.heat_index_c = dhtSensor.computeHeatIndex(d.temp_c, d.humidity_pct, false);
  }
  return d;
}

// ════════════════════════════════════════════════════════════════════════════
// Telemetry batch publish
// ════════════════════════════════════════════════════════════════════════════

static void publishBatch() {
  ntp.update();
  unsigned long epoch = ntp.getEpochTime();
  char ts[24];
  epochToIso8601(epoch, ts, sizeof(ts));

  // ── Read all sensors before building JSON ──────────────────────────────
  // Reading upfront keeps captured_at consistent across every reading in
  // the batch and avoids interleaving I²C traffic with JSON serialisation.

  ImuData imu       = mpuOk ? readImu() : ImuData{};
  int     mq2Raw    = analogRead(PIN_MQ2);
  int     mq7Raw    = analogRead(PIN_MQ7);
  EnvData env       = readEnv();
  int     soundPeak = sampleSoundPeak();  // 100 ms blocking peak-sample

  // Local-only sensors — read but not included in the MQTT payload.
  int  fsrRaw = analogRead(PIN_FSR);
  long irRaw  = maxOk ? maxSensor.getIR() : -1L;

  // ── Serial diagnostic line ─────────────────────────────────────────────
  Serial.print(ts);
  Serial.print(F("  seq=")); Serial.print(txSequence + 1);
  Serial.print(F("  MQ2=")); Serial.print(mq2Raw);
  Serial.print(F("  MQ7=")); Serial.print(mq7Raw);
  Serial.print(F("  SND=")); Serial.print(soundPeak);
  if (mpuOk) {
    Serial.print(F("  AZ="));  Serial.print(imu.az, 2);
  }
  if (!isnan(env.temp_c)) {
    Serial.print(F("  T="));   Serial.print(env.temp_c, 1);
    Serial.print(F("°C  H=")); Serial.print(env.humidity_pct, 1);
    Serial.print('%');
  }
  Serial.print(F("  FSR=")); Serial.print(fsrRaw);
  Serial.print(fsrRaw >= FSR_WORN_THRESHOLD ? F("(worn)") : F("(off)"));
  if (maxOk) {
    Serial.print(F("  IR=")); Serial.print(irRaw);
  }
  Serial.println();

  // ── Build TelemetryBatch JSON (ArduinoJson v7) ─────────────────────────
  JsonDocument doc;
  doc["helmet_id"] = HELMET_ID;
  doc["sequence"]  = ++txSequence;
  doc["sent_at"]   = ts;

  JsonArray readings = doc["readings"].to<JsonArray>();

  // IMU — only included when the sensor initialised successfully.
  if (mpuOk) {
    JsonObject r = readings.add<JsonObject>();
    r["captured_at"] = ts;
    JsonObject v = r["value"].to<JsonObject>();
    v["kind"]              = "imu";
    v["accel_x_g"]         = imu.ax;
    v["accel_y_g"]         = imu.ay;
    v["accel_z_g"]         = imu.az;
    v["accel_magnitude_g"] = imu.mag;
    v["gyro_x_dps"]        = imu.gx;
    v["gyro_y_dps"]        = imu.gy;
    v["gyro_z_dps"]        = imu.gz;
  }

  // MQ-2 (LPG / smoke)
  {
    JsonObject r = readings.add<JsonObject>();
    r["captured_at"] = ts;
    JsonObject v = r["value"].to<JsonObject>();
    v["kind"]    = "gas_lpg";
    v["adc_raw"] = mq2Raw;
  }

  // MQ-7 (carbon monoxide)
  {
    JsonObject r = readings.add<JsonObject>();
    r["captured_at"] = ts;
    JsonObject v = r["value"].to<JsonObject>();
    v["kind"]    = "carbon_monoxide";
    v["adc_raw"] = mq7Raw;
  }

  // DHT-22 (environment) — omit when sensor returns NaN to avoid gateway
  // validation rejection.  The sensor needs ~2 s after power-on to settle;
  // NaN reads during that window are silently skipped.
  if (!isnan(env.temp_c) && !isnan(env.humidity_pct)) {
    JsonObject r = readings.add<JsonObject>();
    r["captured_at"] = ts;
    JsonObject v = r["value"].to<JsonObject>();
    v["kind"]          = "environment";
    v["temperature_c"] = env.temp_c;
    v["humidity_pct"]  = env.humidity_pct;
    v["heat_index_c"]  = env.heat_index_c;
  }

  // Sound sensor (peak ADC over 100 ms)
  {
    JsonObject r = readings.add<JsonObject>();
    r["captured_at"] = ts;
    JsonObject v = r["value"].to<JsonObject>();
    v["kind"]    = "sound_level";
    v["adc_raw"] = soundPeak;
  }

  // ── Serialise and publish ──────────────────────────────────────────────
  char buf[MQTT_BUF_SIZE];
  size_t len = serializeJson(doc, buf, sizeof(buf));

  // PubSubClient v2.8 only supports QoS 0 for PUBLISH.  The gateway's
  // monotonic sequence-number check handles any lost packets; the broker
  // handles re-delivered packets that arrive out of order.
  bool ok = mqtt.publish(TOPIC_TELEMETRY,
                         reinterpret_cast<const uint8_t*>(buf), len,
                         /*retained=*/false);
  if (!ok) {
    Serial.print(F("publish failed len="));
    Serial.println(len);
  }
}

// ════════════════════════════════════════════════════════════════════════════
// Arduino entry points
// ════════════════════════════════════════════════════════════════════════════

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000) {}

  // Build topic strings once; they are fixed for the device lifetime.
  snprintf(TOPIC_TELEMETRY, sizeof(TOPIC_TELEMETRY),
           "safeguard/telemetry/%s", HELMET_ID);
  snprintf(TOPIC_STATUS,    sizeof(TOPIC_STATUS),
           "safeguard/status/%s",    HELMET_ID);
  snprintf(TOPIC_COMMAND,   sizeof(TOPIC_COMMAND),
           "safeguard/command/%s/#", HELMET_ID);

  Serial.print(F("SafeGuard helmet firmware — id="));
  Serial.println(HELMET_ID);

  // ── MPU-6050 (I2C 0x68, SDA/SCL) ───────────────────────────────────────
  if (mpuSensor.begin()) {
    mpuOk = true;
    mpuSensor.setAccelerometerRange(MPU6050_RANGE_2_G);
    mpuSensor.setGyroRange(MPU6050_RANGE_250_DEG);
    mpuSensor.setFilterBandwidth(MPU6050_BAND_21_HZ);
    Serial.println(F("[OK]  MPU-6050"));
  } else {
    Serial.println(F("[--]  MPU-6050 not found — IMU readings omitted from payload"));
  }

  // ── DHT-22 (D4) ─────────────────────────────────────────────────────────
  // begin() does not perform a sensor read.  The NaN guard in publishBatch()
  // silently drops the environment reading during the sensor's ~2 s settling
  // window after power-on; subsequent reads are fine.
  dhtSensor.begin();
  Serial.println(F("[OK]  DHT-22 started (first valid read expected after ~2 s)"));

  // ── MAX30102 (I2C 0x57, shared bus — no address conflict with MPU-6050) ─
  if (maxSensor.begin(Wire, I2C_SPEED_FAST)) {
    maxOk = true;
    maxSensor.setup();
    maxSensor.setPulseAmplitudeRed(0x7F);
    maxSensor.setPulseAmplitudeIR(0x7F);
    Serial.println(F("[OK]  MAX30102 (IR values logged to Serial; not published to MQTT)"));
  } else {
    Serial.println(F("[--]  MAX30102 not found (IR column shows -1 in Serial log)"));
  }

  // Passive analog sensors need no initialisation.
  Serial.println(F("[OK]  MQ-2 A0  MQ-7 A1  Sound A2  FSR A3 (FSR local-log only)"));

  // ── MQTT client — configure once; reconnect loop reuses these settings ───
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onCommand);
  mqtt.setKeepAlive(30);
  mqtt.setBufferSize(MQTT_BUF_SIZE);

  // ── Network bring-up ─────────────────────────────────────────────────────
  connectWifi();
  ntp.begin();
  ntp.update();
  connectMqtt();

  Serial.println(F("SafeGuard helmet ready"));
}

void loop() {
  // Reconnect WiFi and MQTT if the connection was lost.
  if (WiFi.status() != WL_CONNECTED) connectWifi();
  if (!mqtt.connected())             connectMqtt();

  // Process incoming command messages and send MQTT keep-alive PINGs.
  mqtt.loop();

  // Publish one TelemetryBatch per interval.
  unsigned long now = millis();
  if (now - lastBatchMs >= BATCH_INTERVAL_MS) {
    lastBatchMs = now;
    publishBatch();
  }
}
