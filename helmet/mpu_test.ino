#include <Wire.h>
#include <math.h>

#define MPU6050_ADDR 0x68

int16_t ax, ay, az;
int16_t gx, gy, gz;

void setup()
{
    Serial.begin(115200);
    Wire.begin();

    // Wake up MPU6050
    Wire.beginTransmission(MPU6050_ADDR);
    Wire.write(0x6B);
    Wire.write(0x00);
    Wire.endTransmission();

    Serial.println("MPU6050 Ready");
}

void loop()
{

    // Read 14 bytes starting from ACCEL_XOUT_H
    Wire.beginTransmission(MPU6050_ADDR);
    Wire.write(0x3B);
    Wire.endTransmission(false);
    Wire.requestFrom(MPU6050_ADDR, 14, true);

    if (Wire.available() == 14)
    {

        // Accelerometer
        ax = (Wire.read() << 8) | Wire.read();
        ay = (Wire.read() << 8) | Wire.read();
        az = (Wire.read() << 8) | Wire.read();

        // Skip Temperature
        Wire.read();
        Wire.read();

        // Gyroscope
        gx = (Wire.read() << 8) | Wire.read();
        gy = (Wire.read() << 8) | Wire.read();
        gz = (Wire.read() << 8) | Wire.read();

        // Convert to g
        float ax_g = ax / 16384.0;
        float ay_g = ay / 16384.0;
        float az_g = az / 16384.0;

        // Convert to degrees/sec
        float gx_dps = gx / 131.0;
        float gy_dps = gy / 131.0;
        float gz_dps = gz / 131.0;

        // Total acceleration magnitude
        float accMag = sqrt(ax_g * ax_g + ay_g * ay_g + az_g * az_g);

        // Print values
        Serial.print("AX: ");
        Serial.print(ax_g, 2);

        Serial.print(" AY: ");
        Serial.print(ay_g, 2);

        Serial.print(" AZ: ");
        Serial.print(az_g, 2);

        Serial.print(" | GX: ");
        Serial.print(gx_dps, 2);

        Serial.print(" GY: ");
        Serial.print(gy_dps, 2);

        Serial.print(" GZ: ");
        Serial.print(gz_dps, 2);

        Serial.print(" | AccMag: ");
        Serial.println(accMag, 2);
    }

    delay(100);
};