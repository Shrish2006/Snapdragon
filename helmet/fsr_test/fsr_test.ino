// DF-90 FSR Test Code
// Arduino UNO Q

const int fsrPin = A0;   // Analog output connected to A0

void setup() {
  Serial.begin(115200);
  Serial.println("DF-90 FSR Test");
}

void loop() {
  int sensorValue = analogRead(fsrPin);

  Serial.print("Raw Value: ");
  Serial.print(sensorValue);

  // Simple pressure indication
  if (sensorValue < 50) {
    Serial.println("  --> No Pressure");
  }
  else if (sensorValue < 200) {
    Serial.println("  --> Light Pressure");
  }
  else if (sensorValue < 500) {
    Serial.println("  --> Medium Pressure");
  }
  else {
    Serial.println("  --> Heavy Pressure");
  }

  delay(100);
}