/**
 * SafeGuard Helmet Firmware — Arduino UNO Q (WiFiNINA)
 *
 * Reads MPU-6050 (IMU), MQ-2 (LPG/smoke), MQ-7 (CO), DHT-22
 * (temperature/humidity), and the sound sensor, then publishes a
 * TelemetryBatch JSON to the SafeGuard gateway via MQTT.
 *
 * Required libraries (install via Arduino Library Manager):
 *   - WiFiNINA          (board-specific WiFi; swap for WiFi.h on older UNOs)
 *   - PubSubClient      (Nick O'Leary, v2.8+)
 *   - ArduinoJson       (Benoit Blanchon, v7+)
 *   - Adafruit MPU6050  (Adafruit, v2.2+)  requires Adafruit_Sensor
 *   - DHT sensor library (Adafruit, v1.4+)
 *   - NTPClient         (Fabrice Weinberg, v3.2+) for UTC timestamps
 *   - WiFiUdp           (bundled with WiFiNINA)
 *
 * Configuration: edit the constants in the CONFIG section below.
 * Flash: select "Arduino UNO Q WiFi" in the Arduino IDE and upload.
 */

// ── Libraries ────────────────────────────────────────────────────────────────
#include <WiFiNINA.h>
#include <WiFiUdp.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <DHT.h>
#include <NTPClient.h>

// ── CONFIG — edit these per device ───────────────────────────────────────────

// Device identity — must match the MQTT ACL username and the gateway's
// HelmetId pattern: [A-Za-z0-9][A-Za-z0-9_-]{0,63}
static const char* HELMET_ID   = "helmet-01";

// WiFi
static const char* WIFI_SSID   = "YOUR_SSID";
static const char* WIFI_PASS   = "YOUR_WIFI_PASSWORD";

// MQTT broker — deployed VPS at 138.201.157.147:31883 (NodePort).
// For local dev: localhost:1883. Anonymous access, no password required.
static const char* MQTT_HOST   = "138.201.157.147";
static const int   MQTT_PORT   = 31883;
static const char* MQTT_USER   = "helmet-01";      // must equal HELMET_ID
static const char* MQTT_PASS   = "";               // anonymous access

// Sensor pins
static const int   MQ2_PIN     = A0;   // MQ-2 gas sensor (LPG / smoke)
static const int   MQ7_PIN     = A1;   // MQ-7 CO sensor
static const int   SOUND_PIN   = A2;   // sound sensor (peak ADC)
static const int   DHT_PIN     = 4;    // DHT-22 data pin
static const uint8_t DHT_TYPE  = DHT22;

// Timing
static const unsigned long BATCH_INTERVAL_MS  = 500;   // 2 Hz batch publish rate
static const unsigned long NTP_SYNC_INTERVAL  = 60000; // re-sync NTP every 60 s

// ── Topics ───────────────────────────────────────────────────────────────────
// Built at runtime using HELMET_ID so the topic always matches the payload.
static char TOPIC_TELEMETRY[80];
static char TOPIC_STATUS[80];
static char TOPIC_COMMAND[80];

// ── Globals ──────────────────────────────────────────────────────────────────
WiFiClient     wifiClient;
PubSubClient   mqttClient(wifiClient);
WiFiUDP        ntpUdp;
NTPClient      ntpClient(ntpUdp, "pool.ntp.org", 0, NTP_SYNC_INTERVAL);
Adafruit_MPU6050 mpu;
DHT            dht(DHT_PIN, DHT_TYPE);

static uint32_t sequence      = 0;
static uint32_t lastBatchMs   = 0;
static bool     mpuOk         = false;
static bool     dhtOk         = false;

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Format epoch seconds as ISO 8601 UTC: "2026-07-12T10:30:00Z" */
static void epochToIso8601(unsigned long epoch, char* buf, size_t len) {
  unsigned long ss = epoch % 60;
  unsigned long mm = (epoch / 60) % 60;
  unsigned long hh = (epoch / 3600) % 24;
  unsigned long days = epoch / 86400;
  // Simplified Gregorian calendar (good until 2100)
  int year = 1970;
  while (true) {
    bool leap = (year % 4 == 0 && (year % 100 != 0 || year % 400 == 0));
    unsigned long diy = leap ? 366 : 365;
    if (days < diy) break;
    days -= diy;
    year++;
  }
  static const uint8_t dim[] = {31,28,31,30,31,30,31,31,30,31,30,31};
  bool leap = (year % 4 == 0 && (year % 100 != 0 || year % 400 == 0));
  int month = 0;
  for (month = 0; month < 12; month++) {
    uint8_t d = dim[month] + (month == 1 && leap ? 1 : 0);
    if (days < d) break;
    days -= d;
  }
  snprintf(buf, len, "%04d-%02d-%02dT%02d:%02d:%02dZ",
           year, month + 1, (int)days + 1, (int)hh, (int)mm, (int)ss);
}

/** Publish the MQTT status retained message. */
static void publishStatus(const char* status) {
  StaticJsonDocument<64> doc;
  doc["status"] = status;
  char buf[64];
  serializeJson(doc, buf);
  mqttClient.publish(TOPIC_STATUS, buf, /*retain=*/true);
}

/** Called by PubSubClient for incoming command messages. */
static void onCommand(const char* topic, byte* payload, unsigned int length) {
  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  if (err) return;

  // safeguard/command/{id}/alert
  if (strstr(topic, "/alert")) {
    bool buzzer = doc["buzzer"] | false;
    int  dur    = doc["duration_ms"] | 1000;
    if (buzzer) {
      // TODO: wire a buzzer to a PWM pin and drive it for `dur` ms.
      // Example: tone(BUZZER_PIN, 2000, dur);
      Serial.print(F("ALERT: buzzer for "));
      Serial.print(dur);
      Serial.println(F(" ms"));
    }
  }
  // safeguard/command/{id}/config
  else if (strstr(topic, "/config")) {
    // Future: apply runtime config overrides from the gateway.
    Serial.println(F("CONFIG received (not yet applied)"));
  }
  // safeguard/command/{id}/ota
  else if (strstr(topic, "/ota")) {
    Serial.println(F("OTA trigger received (not implemented)"));
  }
}

// ── WiFi ──────────────────────────────────────────────────────────────────────

static void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.print(F("Connecting WiFi "));
  Serial.print(WIFI_SSID);
  while (WiFi.begin(WIFI_SSID, WIFI_PASS) != WL_CONNECTED) {
    Serial.print('.');
    delay(3000);
  }
  Serial.print(F(" OK, IP="));
  Serial.println(WiFi.localIP());
}

// ── MQTT ──────────────────────────────────────────────────────────────────────

static void connectMqtt() {
  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setCallback(onCommand);
  mqttClient.setKeepAlive(30);
  mqttClient.setBufferSize(512);

  // LWT: broker publishes this if the TCP connection drops ungracefully.
  StaticJsonDocument<64> lwt;
  lwt["status"] = "offline";
  char lwtBuf[64];
  serializeJson(lwt, lwtBuf);

  while (!mqttClient.connected()) {
    Serial.print(F("Connecting MQTT..."));
    char clientId[32];
    snprintf(clientId, sizeof(clientId), "safeguard-%s", HELMET_ID);
    bool ok = mqttClient.connect(
      clientId,
      MQTT_USER, MQTT_PASS,
      TOPIC_STATUS,  // LWT topic
      0,             // LWT QoS
      true,          // LWT retain
      lwtBuf         // LWT payload
    );
    if (ok) {
      Serial.println(F(" connected"));
      publishStatus("online");
      mqttClient.subscribe(TOPIC_COMMAND, 1);  // QoS 1 for commands
    } else {
      Serial.print(F(" failed rc="));
      Serial.print(mqttClient.state());
      Serial.println(F(" retry in 5s"));
      delay(5000);
    }
  }
}

// ── Sensors ───────────────────────────────────────────────────────────────────

struct ImuData {
  float accel_x_g, accel_y_g, accel_z_g, accel_magnitude_g;
  float gyro_x_dps, gyro_y_dps, gyro_z_dps;
};

struct EnvData {
  float temperature_c, humidity_pct, heat_index_c;
};

static ImuData readImu() {
  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);
  ImuData d;
  // MPU-6050 accel in m/s²  → divide by g (9.80665)
  d.accel_x_g = a.acceleration.x / 9.80665f;
  d.accel_y_g = a.acceleration.y / 9.80665f;
  d.accel_z_g = a.acceleration.z / 9.80665f;
  d.accel_magnitude_g = sqrt(
    d.accel_x_g * d.accel_x_g +
    d.accel_y_g * d.accel_y_g +
    d.accel_z_g * d.accel_z_g
  );
  // Gyro in rad/s → degrees/s
  d.gyro_x_dps = g.gyro.x * (180.0f / M_PI);
  d.gyro_y_dps = g.gyro.y * (180.0f / M_PI);
  d.gyro_z_dps = g.gyro.z * (180.0f / M_PI);
  return d;
}

static EnvData readEnv() {
  EnvData d;
  d.humidity_pct   = dht.readHumidity();
  d.temperature_c  = dht.readTemperature();
  d.heat_index_c   = dht.computeHeatIndex(d.temperature_c, d.humidity_pct, false);
  return d;
}

// ── Telemetry publish ─────────────────────────────────────────────────────────

static void publishBatch() {
  ntpClient.update();
  unsigned long epoch = ntpClient.getEpochTime();
  char ts[24];
  epochToIso8601(epoch, ts, sizeof(ts));

  // Build the JSON document on the stack.
  // Capacity: envelope (~150) + up to 5 readings (~120 each) = ~750 bytes.
  StaticJsonDocument<900> doc;
  doc["helmet_id"] = HELMET_ID;
  doc["sequence"]  = ++sequence;
  doc["sent_at"]   = ts;

  JsonArray readings = doc.createNestedArray("readings");

  // IMU reading (always included — highest frequency sensor)
  if (mpuOk) {
    ImuData imu = readImu();
    JsonObject r = readings.createNestedObject();
    r["captured_at"] = ts;
    JsonObject v = r.createNestedObject("value");
    v["kind"]              = "imu";
    v["accel_x_g"]         = imu.accel_x_g;
    v["accel_y_g"]         = imu.accel_y_g;
    v["accel_z_g"]         = imu.accel_z_g;
    v["accel_magnitude_g"] = imu.accel_magnitude_g;
    v["gyro_x_dps"]        = imu.gyro_x_dps;
    v["gyro_y_dps"]        = imu.gyro_y_dps;
    v["gyro_z_dps"]        = imu.gyro_z_dps;
  }

  // Gas LPG / smoke (MQ-2)
  {
    JsonObject r = readings.createNestedObject();
    r["captured_at"] = ts;
    JsonObject v = r.createNestedObject("value");
    v["kind"]    = "gas_lpg";
    v["adc_raw"] = analogRead(MQ2_PIN);
  }

  // Carbon monoxide (MQ-7)
  {
    JsonObject r = readings.createNestedObject();
    r["captured_at"] = ts;
    JsonObject v = r.createNestedObject("value");
    v["kind"]    = "carbon_monoxide";
    v["adc_raw"] = analogRead(MQ7_PIN);
  }

  // Environment (DHT-22) — slower sensor, publish every batch anyway
  if (dhtOk) {
    EnvData env = readEnv();
    if (!isnan(env.temperature_c) && !isnan(env.humidity_pct)) {
      JsonObject r = readings.createNestedObject();
      r["captured_at"] = ts;
      JsonObject v = r.createNestedObject("value");
      v["kind"]          = "environment";
      v["temperature_c"] = env.temperature_c;
      v["humidity_pct"]  = env.humidity_pct;
      v["heat_index_c"]  = env.heat_index_c;
    }
  }

  // Sound level (peak ADC)
  {
    JsonObject r = readings.createNestedObject();
    r["captured_at"] = ts;
    JsonObject v = r.createNestedObject("value");
    v["kind"]    = "sound_level";
    v["adc_raw"] = analogRead(SOUND_PIN);
  }

  // Serialise and publish at QoS 1.
  char buf[900];
  size_t len = serializeJson(doc, buf);
  bool ok = mqttClient.publish(TOPIC_TELEMETRY, buf, /*retained=*/false);
  if (!ok) {
    Serial.print(F("publish failed (len="));
    Serial.print(len);
    Serial.println(')');
  }
}

// ── Setup / Loop ──────────────────────────────────────────────────────────────

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000) {}  // wait for USB serial (UNO Q)

  // Build topic strings once (avoids repeated snprintf in loop)
  snprintf(TOPIC_TELEMETRY, sizeof(TOPIC_TELEMETRY), "safeguard/telemetry/%s", HELMET_ID);
  snprintf(TOPIC_STATUS,    sizeof(TOPIC_STATUS),    "safeguard/status/%s",    HELMET_ID);
  snprintf(TOPIC_COMMAND,   sizeof(TOPIC_COMMAND),   "safeguard/command/%s/#", HELMET_ID);

  // MPU-6050
  if (mpu.begin()) {
    mpuOk = true;
    mpu.setAccelerometerRange(MPU6050_RANGE_2_G);
    mpu.setGyroRange(MPU6050_RANGE_250_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
    Serial.println(F("MPU-6050 OK"));
  } else {
    Serial.println(F("MPU-6050 not found — IMU readings omitted"));
  }

  // DHT-22
  dht.begin();
  float testH = dht.readHumidity();
  dhtOk = !isnan(testH);
  Serial.println(dhtOk ? F("DHT-22 OK") : F("DHT-22 not found — env readings omitted"));

  // Network
  connectWifi();
  ntpClient.begin();
  ntpClient.update();
  connectMqtt();

  Serial.println(F("SafeGuard helmet ready"));
}

void loop() {
  // Maintain connections
  if (WiFi.status() != WL_CONNECTED) connectWifi();
  if (!mqttClient.connected())        connectMqtt();
  mqttClient.loop();  // process incoming commands + keep-alive

  // Publish on interval
  unsigned long now = millis();
  if (now - lastBatchMs >= BATCH_INTERVAL_MS) {
    lastBatchMs = now;
    publishBatch();
  }
}
