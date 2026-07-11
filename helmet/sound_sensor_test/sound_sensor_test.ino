const int soundPin = A0;

void setup() {
  Serial.begin(115200);
}

void loop() {
  int peak = 0;

  unsigned long startTime = millis();

  while (millis() - startTime < 100) {   // Sample for 100 ms
    int value = analogRead(soundPin);

    if (value > peak) {
      peak = value;
    }
  }

  Serial.print("Peak Sound Level: ");
  Serial.println(peak);

  delay(100);
}