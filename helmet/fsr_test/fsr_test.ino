// Helmet Wear Detection using FSR
// Arduino UNO Q

const int FSR_PIN = A0;
const int THRESHOLD = 90;

void setup() {
  Serial.begin(115200);
  Serial.println("Helmet Wear Detection Started");
}

void loop() {
  long sum = 0;

  // Take 10 readings and average them
  for (int i = 0; i < 10; i++) {
    sum += analogRead(FSR_PIN);
    delay(5);
  }

  int fsrValue = sum / 10;

  Serial.print("FSR Value: ");
  Serial.print(fsrValue);

  if (fsrValue >= THRESHOLD) {
    Serial.println("  --> Helmet Worn");
  } else {
    Serial.println("  --> Helmet Not Worn");
  }

  delay(200);
}
/*
FSR Value: 62  --> Helmet Not Worn
FSR Value: 94  --> Helmet Not Worn
FSR Value: 102  --> Helmet Not Worn
FSR Value: 97  --> Helmet Not Worn
FSR Value: 125  --> Helmet Not Worn
*/