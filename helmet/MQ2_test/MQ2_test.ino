#define MQ7_PIN A1

void setup() {
  Serial.begin(115200);
  Serial.println("MQ-7 Sensor Test");
}

void loop() {
  int sensorValue = analogRead(MQ7_PIN);

  Serial.print("MQ-7 Analog Value: ");
  Serial.println(sensorValue);

  delay(500);
}