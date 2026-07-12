/**
 * SafeGuard Helmet Firmware — Arduino UNO Q WiFi
 *
 * Reads all onboard helmet sensors and publishes a TelemetryBatch JSON
 * to the SafeGuard gateway via MQTT every BATCH_INTERVAL_MS.
 *
 * Board:      Arduino UNO Q (zephyr architecture)
 * Networking: Arduino_RouterBridge — WiFi is managed by the companion
 *             router chip; no WiFi credentials are needed in this sketch.
 *
 * ── MQTT-published sensor types (match gateway SENSOR_REGISTRY) ──────────
 *   MPU-6050  → "imu"              I2C 0x68, SDA/SCL
 *   MQ-2      → "gas_lpg"          A0, 10-bit raw ADC
 *   MQ-7      → "carbon_monoxide"  A1, 10-bit raw ADC
 *   DHT-22    → "environment"      D4
 *   Sound     → "sound_level"      A2, peak ADC over 100 ms window
 *
 * ── Sensors read locally (NOT in MQTT payload) ───────────────────────────
 *   MAX30102  → IR raw value        I2C 0x57 (shared bus, no conflict)
 *   FSR       → pressure raw ADC    A3, helmet-worn detection
 *
 *   These sensor kinds are not registered in the gateway SENSOR_REGISTRY.
 *   Including an unknown kind causes the gateway to reject the whole batch.
 *   Values are logged to Monitor for field debugging only.
 *
 * ── Required libraries (Arduino IDE → Tools → Manage Libraries) ───────────
 *   Arduino_RouterBridge    bundled with Arduino UNO Q board package
 *   PubSubClient            Nick O'Leary     ≥ 2.8
 *   ArduinoJson             Benoit Blanchon  ≥ 7.0
 *   Adafruit MPU6050        Adafruit         ≥ 2.2
 *   Adafruit Unified Sensor Adafruit         ≥ 1.1
 *   DHT sensor library      Adafruit         ≥ 1.4
 *   SparkFun MAX3010x Sensor Library  SparkFun ≥ 1.1
 *
 * ── Flash ────────────────────────────────────────────────────────────────
 *   Tools → Board → Arduino UNO Q, then Upload.
 *   Open Monitor at 115200 baud to confirm connection and batch publishes.
 */

#include <Arduino_RouterBridge.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <DHT.h>
#include <Wire.h>
#include "MAX30105.h"

// ════════════════════════════════════════════════════════════════════════════
// CONFIG — edit these values per device before flashing
// ════════════════════════════════════════════════════════════════════════════

// Device identity — must match gateway HelmetId pattern:
// [A-Za-z0-9][A-Za-z0-9_-]{0,63}
static const char* HELMET_ID = "helmet-01";

// MQTT broker:
//   Production VPS (anywhere on internet): 138.201.157.147 : 31883
//   Docker Compose, same machine:          localhost        : 1883
//   Docker Compose, Arduino on LAN:        <PC LAN IP>     : 1883
static const char* MQTT_HOST = "138.201.157.147";
static const int   MQTT_PORT = 31883;
static const char* MQTT_USER = "helmet-01";  // must equal HELMET_ID
static const char* MQTT_PASS = "";           // broker uses anonymous access

// ════════════════════════════════════════════════════════════════════════════
// Pin assignments
// ════════════════════════════════════════════════════════════════════════════

static const uint8_t PIN_MQ2   = A0;
static const uint8_t PIN_MQ7   = A1;
static const uint8_t PIN_SOUND = A2;
static const uint8_t PIN_DHT   = 4;
static const uint8_t PIN_FSR   = A3;  // local log only

// ════════════════════════════════════════════════════════════════════════════
// Timing and sizing constants
// ════════════════════════════════════════════════════════════════════════════

static const unsigned long BATCH_INTERVAL_MS  = 500;    // 2 Hz publish rate
static const unsigned long SOUND_SAMPLE_MS    = 100;    // peak-sample window
static const unsigned long NTP_SYNC_MS        = 60000;  // NTP re-sync period
static const uint16_t      MQTT_BUF_SIZE      = 1024;
static const int           FSR_WORN_THRESHOLD = 90;

// ════════════════════════════════════════════════════════════════════════════
// NTP constants
// ════════════════════════════════════════════════════════════════════════════

static const char         NTP_SERVER[]   = "pool.ntp.org";
static const unsigned int NTP_PORT       = 123;
static const unsigned int NTP_LOCAL_PORT = 8888;
static const int          NTP_PACKET_SIZE = 48;
static const unsigned long SEVENTY_YEARS = 2208988800UL;

// ════════════════════════════════════════════════════════════════════════════
// MQTT topic strings — built once in setup()
// ════════════════════════════════════════════════════════════════════════════

static char TOPIC_TELEMETRY[80];
static char TOPIC_STATUS[80];
static char TOPIC_COMMAND[80];

// ════════════════════════════════════════════════════════════════════════════
// Sensor value structs — defined before any function so Arduino IDE prototype
// injection does not generate readImu() / readEnv() before these types exist.
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
// Peripheral instances
// ════════════════════════════════════════════════════════════════════════════

static BridgeTCPClient<>  netClient(Bridge);  // TCP transport for PubSubClient
static PubSubClient       mqtt(netClient);
static BridgeUDP<4096>    ntpUdp(Bridge);     // UDP transport for NTP
static Adafruit_MPU6050   mpuSensor;
static DHT                dhtSensor(PIN_DHT, DHT22);
static MAX30105           maxSensor;

// ════════════════════════════════════════════════════════════════════════════
// Runtime state
// ════════════════════════════════════════════════════════════════════════════

static uint32_t      txSequence   = 0;
static uint32_t      lastBatchMs  = 0;
static bool          mpuOk        = false;
static bool          maxOk        = false;
static unsigned long cachedEpoch  = 0;  // last NTP epoch (Unix seconds)
static unsigned long epochMillis  = 0;  // millis() at the time cachedEpoch was set
static unsigned long lastNtpSync  = 0;  // millis() of last successful NTP sync

// ════════════════════════════════════════════════════════════════════════════
// NTP — manual implementation using BridgeUDP (NTPClient library is not
// compatible with BridgeUDP; the UDP_NTP_client board example does it manually)
// ════════════════════════════════════════════════════════════════════════════

// Sends one NTP request and returns the Unix epoch, or 0 on failure.
static unsigned long fetchNtpTime() {
  byte buf[NTP_PACKET_SIZE];
  memset(buf, 0, NTP_PACKET_SIZE);
  buf[0]  = 0b11100011;  // LI=3, Version=4, Mode=3 (client)
  buf[1]  = 0;
  buf[2]  = 6;
  buf[3]  = 0xEC;
  buf[12] = 49;
  buf[13] = 0x4E;
  buf[14] = 49;
  buf[15] = 52;

  if (!ntpUdp.beginPacket(NTP_SERVER, NTP_PORT)) return 0;
  ntpUdp.write(buf, NTP_PACKET_SIZE);
  ntpUdp.endPacket();

  ntpUdp.setTimeout(2000);
  if (!ntpUdp.parsePacket()) return 0;

  ntpUdp.read(buf, NTP_PACKET_SIZE);
  unsigned long hi = word(buf[40], buf[41]);
  unsigned long lo = word(buf[42], buf[43]);
  return (hi << 16 | lo) - SEVENTY_YEARS;
}

// Returns the current Unix epoch, re-syncing NTP every NTP_SYNC_MS.
// Between syncs, time is derived from the cached value + elapsed millis().
static unsigned long getEpochTime() {
  unsigned long now = millis();
  if (cachedEpoch == 0 || now - lastNtpSync >= NTP_SYNC_MS) {
    unsigned long t = fetchNtpTime();
    if (t > 0) {
      cachedEpoch = t;
      epochMillis = now;
      lastNtpSync = now;
    }
  }
  if (cachedEpoch == 0) return 0;
  return cachedEpoch + (millis() - epochMillis) / 1000;
}

// ════════════════════════════════════════════════════════════════════════════
// Utility helpers
// ════════════════════════════════════════════════════════════════════════════

// Writes an ISO 8601 UTC timestamp ("YYYY-MM-DDTHH:MM:SSZ") into buf.
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

// Samples the sound sensor for SOUND_SAMPLE_MS and returns the peak ADC value.
static int sampleSoundPeak() {
  int peak = 0;
  unsigned long start = millis();
  while (millis() - start < SOUND_SAMPLE_MS) {
    int v = analogRead(PIN_SOUND);
    if (v > peak) peak = v;
  }
  return peak;
}

// Publishes a retained JSON status message to TOPIC_STATUS.
static void publishStatus(const char* statusStr) {
  char buf[32];
  snprintf(buf, sizeof(buf), "{\"status\":\"%s\"}", statusStr);
  mqtt.publish(TOPIC_STATUS, reinterpret_cast<const uint8_t*>(buf),
               strlen(buf), /*retained=*/true);
}

// ════════════════════════════════════════════════════════════════════════════
// MQTT command callback  (gateway → helmet)
// ════════════════════════════════════════════════════════════════════════════

static void onCommand(char* topic, byte* payload, unsigned int length) {
  JsonDocument cmd;
  if (deserializeJson(cmd, payload, length) != DeserializationError::Ok) return;

  if (strstr(topic, "/alert")) {
    int dur = cmd["duration_ms"] | 1000;
    // Wire a buzzer to a PWM pin and un-comment: tone(9, 2000, dur);
    Monitor.print(F("CMD alert "));
    Monitor.print(dur);
    Monitor.println(F("ms"));
  } else if (strstr(topic, "/config")) {
    Monitor.println(F("CMD config (not yet applied)"));
  } else if (strstr(topic, "/ota")) {
    Monitor.println(F("CMD ota (not implemented)"));
  }
}

// ════════════════════════════════════════════════════════════════════════════
// MQTT connection
// ════════════════════════════════════════════════════════════════════════════

static void connectMqtt() {
  while (!mqtt.connected()) {
    Monitor.print(F("MQTT → "));
    char clientId[40];
    snprintf(clientId, sizeof(clientId), "safeguard-%s", HELMET_ID);

    // LWT: broker sends this if the TCP session drops ungracefully.
    bool ok = mqtt.connect(
      clientId,
      MQTT_USER, MQTT_PASS,
      TOPIC_STATUS, /*lwt qos*/ 0, /*lwt retain*/ true,
      "{\"status\":\"offline\"}"
    );

    if (ok) {
      Monitor.println(F("connected"));
      publishStatus("online");
      mqtt.subscribe(TOPIC_COMMAND, /*qos*/ 1);
    } else {
      Monitor.print(F("rc="));
      Monitor.print(mqtt.state());
      Monitor.println(F(" retry 5s"));
      delay(5000);
    }
  }
}

// ════════════════════════════════════════════════════════════════════════════
// Sensor read functions
// ════════════════════════════════════════════════════════════════════════════

static ImuData readImu() {
  sensors_event_t a, g, tmp;
  mpuSensor.getEvent(&a, &g, &tmp);
  ImuData d;
  // Adafruit driver returns m/s²; gateway schema requires g.
  d.ax  = a.acceleration.x / 9.80665f;
  d.ay  = a.acceleration.y / 9.80665f;
  d.az  = a.acceleration.z / 9.80665f;
  d.mag = sqrtf(d.ax * d.ax + d.ay * d.ay + d.az * d.az);
  // Adafruit driver returns rad/s; gateway schema requires deg/s.
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
  unsigned long epoch = getEpochTime();
  char ts[24];
  if (epoch > 0) {
    epochToIso8601(epoch, ts, sizeof(ts));
  } else {
    // NTP not yet synced — gateway will reject for clock skew; batch is
    // still sent so sequence numbers stay monotonic once NTP recovers.
    snprintf(ts, sizeof(ts), "1970-01-01T00:00:00Z");
  }

  // ── Read all sensors before building JSON ─────────────────────────────
  ImuData imu       = mpuOk ? readImu() : ImuData{};
  int     mq2Raw    = analogRead(PIN_MQ2);
  int     mq7Raw    = analogRead(PIN_MQ7);
  EnvData env       = readEnv();
  int     soundPeak = sampleSoundPeak();  // 100 ms peak-sample window

  // Local-only sensors — not published to MQTT.
  int  fsrRaw = analogRead(PIN_FSR);
  long irRaw  = maxOk ? maxSensor.getIR() : -1L;

  // ── Diagnostic line ───────────────────────────────────────────────────
  Monitor.print(ts);
  Monitor.print(F("  seq=")); Monitor.print(txSequence + 1);
  Monitor.print(F("  MQ2=")); Monitor.print(mq2Raw);
  Monitor.print(F("  MQ7=")); Monitor.print(mq7Raw);
  Monitor.print(F("  SND=")); Monitor.print(soundPeak);
  if (mpuOk) { Monitor.print(F("  AZ=")); Monitor.print(imu.az, 2); }
  if (!isnan(env.temp_c)) {
    Monitor.print(F("  T="));  Monitor.print(env.temp_c, 1);
    Monitor.print(F("C H=")); Monitor.print(env.humidity_pct, 1);
    Monitor.print('%');
  }
  Monitor.print(F("  FSR=")); Monitor.print(fsrRaw);
  Monitor.print(fsrRaw >= FSR_WORN_THRESHOLD ? F("(worn)") : F("(off)"));
  if (maxOk) { Monitor.print(F("  IR=")); Monitor.print(irRaw); }
  Monitor.println();

  // ── Build TelemetryBatch JSON (ArduinoJson v7) ─────────────────────────
  JsonDocument doc;
  doc["helmet_id"] = HELMET_ID;
  doc["sequence"]  = ++txSequence;
  doc["sent_at"]   = ts;

  JsonArray readings = doc["readings"].to<JsonArray>();

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

  {
    JsonObject r = readings.add<JsonObject>();
    r["captured_at"] = ts;
    JsonObject v = r["value"].to<JsonObject>();
    v["kind"]    = "gas_lpg";
    v["adc_raw"] = mq2Raw;
  }

  {
    JsonObject r = readings.add<JsonObject>();
    r["captured_at"] = ts;
    JsonObject v = r["value"].to<JsonObject>();
    v["kind"]    = "carbon_monoxide";
    v["adc_raw"] = mq7Raw;
  }

  // DHT-22: omit if NaN to avoid gateway validation rejection.
  if (!isnan(env.temp_c) && !isnan(env.humidity_pct)) {
    JsonObject r = readings.add<JsonObject>();
    r["captured_at"] = ts;
    JsonObject v = r["value"].to<JsonObject>();
    v["kind"]          = "environment";
    v["temperature_c"] = env.temp_c;
    v["humidity_pct"]  = env.humidity_pct;
    v["heat_index_c"]  = env.heat_index_c;
  }

  {
    JsonObject r = readings.add<JsonObject>();
    r["captured_at"] = ts;
    JsonObject v = r["value"].to<JsonObject>();
    v["kind"]    = "sound_level";
    v["adc_raw"] = soundPeak;
  }

  // ── Serialise and publish ─────────────────────────────────────────────
  char buf[MQTT_BUF_SIZE];
  size_t len = serializeJson(doc, buf, sizeof(buf));

  bool ok = mqtt.publish(TOPIC_TELEMETRY,
                         reinterpret_cast<const uint8_t*>(buf), len,
                         /*retained=*/false);
  if (!ok) {
    Monitor.print(F("publish failed len="));
    Monitor.println(len);
  }
}

// ════════════════════════════════════════════════════════════════════════════
// Arduino entry points
// ════════════════════════════════════════════════════════════════════════════

void setup() {
  // Bridge.begin() connects to the companion router chip and brings up WiFi.
  // Must be called before any networking or Monitor output.
  Bridge.begin();
  Monitor.begin(115200);

  snprintf(TOPIC_TELEMETRY, sizeof(TOPIC_TELEMETRY),
           "safeguard/telemetry/%s", HELMET_ID);
  snprintf(TOPIC_STATUS,    sizeof(TOPIC_STATUS),
           "safeguard/status/%s",    HELMET_ID);
  snprintf(TOPIC_COMMAND,   sizeof(TOPIC_COMMAND),
           "safeguard/command/%s/#", HELMET_ID);

  Monitor.print(F("SafeGuard helmet firmware — id="));
  Monitor.println(HELMET_ID);

  // ── MPU-6050 (I2C 0x68) ─────────────────────────────────────────────────
  if (mpuSensor.begin()) {
    mpuOk = true;
    mpuSensor.setAccelerometerRange(MPU6050_RANGE_2_G);
    mpuSensor.setGyroRange(MPU6050_RANGE_250_DEG);
    mpuSensor.setFilterBandwidth(MPU6050_BAND_21_HZ);
    Monitor.println(F("[OK]  MPU-6050"));
  } else {
    Monitor.println(F("[--]  MPU-6050 not found — IMU readings omitted"));
  }

  // ── DHT-22 (D4) ─────────────────────────────────────────────────────────
  dhtSensor.begin();
  Monitor.println(F("[OK]  DHT-22 started (~2 s to first valid read)"));

  // ── MAX30102 (I2C 0x57, shared bus — no conflict with MPU-6050) ─────────
  if (maxSensor.begin(Wire, I2C_SPEED_FAST)) {
    maxOk = true;
    maxSensor.setup();
    maxSensor.setPulseAmplitudeRed(0x7F);
    maxSensor.setPulseAmplitudeIR(0x7F);
    Monitor.println(F("[OK]  MAX30102 (IR logged locally; not in MQTT payload)"));
  } else {
    Monitor.println(F("[--]  MAX30102 not found"));
  }

  Monitor.println(F("[OK]  MQ-2 A0  MQ-7 A1  Sound A2  FSR A3"));

  // ── NTP initial sync ─────────────────────────────────────────────────────
  ntpUdp.begin(NTP_LOCAL_PORT);
  unsigned long t = fetchNtpTime();
  if (t > 0) {
    cachedEpoch = t;
    epochMillis = millis();
    lastNtpSync = millis();
    Monitor.println(F("[OK]  NTP synced"));
  } else {
    Monitor.println(F("[--]  NTP failed — timestamps will be 1970 until next sync"));
  }

  // ── MQTT client ──────────────────────────────────────────────────────────
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onCommand);
  mqtt.setKeepAlive(30);
  mqtt.setBufferSize(MQTT_BUF_SIZE);
  connectMqtt();

  Monitor.println(F("SafeGuard helmet ready"));
}

void loop() {
  if (!mqtt.connected()) connectMqtt();
  mqtt.loop();  // process incoming commands + MQTT keep-alive PINGs

  unsigned long now = millis();
  if (now - lastBatchMs >= BATCH_INTERVAL_MS) {
    lastBatchMs = now;
    publishBatch();
  }
}
