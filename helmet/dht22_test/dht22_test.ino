#include <DHT.h>

#define DHTPIN 2        // DHT22 data pin connected to D2
#define DHTTYPE DHT22   // Sensor type

DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(115200);

  Serial.println("DHT22 Test");
  dht.begin();
}

void loop() {
  float humidity = dht.readHumidity();
  float temperatureC = dht.readTemperature();
  float temperatureF = dht.readTemperature(true);

  // Check if reading failed
  if (isnan(humidity) || isnan(temperatureC) || isnan(temperatureF)) {
    Serial.println("Failed to read from DHT22!");
    delay(2000);
    return;
  }

  // Calculate Heat Index
  float heatIndexC = dht.computeHeatIndex(temperatureC, humidity, false);

  Serial.print("Temperature: ");
  Serial.print(temperatureC);
  Serial.print(" °C\t");

  Serial.print("Humidity: ");
  Serial.print(humidity);
  Serial.print(" %\t");

  Serial.print("Heat Index: ");
  Serial.print(heatIndexC);
  Serial.println(" °C");

  delay(2000);
}