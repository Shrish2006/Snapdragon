#define MQ2_PIN A1

void setup() {
  Serial.begin(115200);
  Serial.println("MQ-2 Sensor Test");
}

void loop() {
  int sensorValue = analogRead(MQ2_PIN);

  Serial.print("MQ-2 Analog Value: ");
  Serial.println(sensorValue);

  delay(500);
}