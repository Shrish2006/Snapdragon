#include <Wire.h>
#include "MAX30105.h"

MAX30105 sensor;

#define FINGER_THRESHOLD 6000

void setup()
{
  Serial.begin(115200);
  Wire.begin();

  if (!sensor.begin(Wire, I2C_SPEED_FAST))
  {
    Serial.println("MAX30102 not found");
    while(1);
  }

  Serial.println("MAX30102 OK");

  sensor.setup();

  // Increase LED power
  sensor.setPulseAmplitudeRed(0x7F);
  sensor.setPulseAmplitudeIR(0x7F);
}

void loop()
{
  long irValue = sensor.getIR();

  Serial.print("IR: ");
  Serial.print(irValue);

  if (irValue < FINGER_THRESHOLD)
  {
    Serial.println("  -> No Finger");
  }
  else
  {
    Serial.println("  -> Finger Detected");
  }

  delay(200);
}
/*IR: 109787  -> Finger Detected
IR: 91305  -> Finger Detected
IR: 6542  -> Finger Detected
IR: 5287  -> No Finger
IR: 5630  -> No Finger
IR: 5313  -> No Finger
IR: 5393  -> No Finger*/