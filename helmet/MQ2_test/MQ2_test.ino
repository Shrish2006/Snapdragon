// MQ-2 Gas Sensor Test

const int MQ2_PIN = A0;

void setup() {
  Serial.begin(115200);

  Serial.println("MQ-2 Gas Sensor Test");
  Serial.println("Warming up sensor...");
  delay(20000);  // 20 seconds warm-up
}

void loop() {
  int sensorValue = analogRead(MQ2_PIN);

  Serial.print("Gas Sensor Value: ");
  Serial.println(sensorValue);

  // Simple indication
  if (sensorValue < 200) {
    Serial.println("Air Quality: Clean");
  }
  else if (sensorValue < 500) {
    Serial.println("Air Quality: Moderate");
  }
  else {
    Serial.println("Air Quality: Gas/Smoke Detected!");
  }

  Serial.println("----------------------");
  delay(1000);
}