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
/*MQ-7 Analog Value: 66
MQ-7 Analog Value: 66
MQ-7 Analog Value: 67
MQ-7 Analog Value: 66
MQ-7 Analog Value: 65
MQ-7 Analog Value: 66
MQ-7 Analog Value: 67
MQ-7 Analog Value: 67
MQ-7 Analog Value: 66
MQ-7 Analog Value: 69
MQ-7 Analog Value: 73
MQ-7 Analog Value: 71*/