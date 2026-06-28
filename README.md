# SafeGuard — AI-Powered Industrial Worker Safety System

> **Snapdragon Multiverse Hackathon 2026 · Bangalore**

---

## What is SafeGuard?

SafeGuard is a multi-device industrial safety system that combines a **sensor-equipped smart helmet** (Arduino UNO Q) with **computer vision** (Snapdragon AI PC) to provide real-time worker safety monitoring.

The helmet continuously reads environmental and biometric data — gas levels, CO, temperature, heart rate, motion, and location — and runs **edge AI anomaly detection** locally. Simultaneously, a fixed camera feed runs **PPE detection** and **danger zone monitoring** on the Snapdragon AI PC. Both streams are fused into a unified risk score that triggers alerts on the mobile dashboard.

---

## Team

| # | Name | Email |
|---|------|-------|
| 1 | Shrish Makwana | shrish.hmakwana2024@vitstudent.ac.in |
| 2 | Ankit Agrawal | Ankit.agrawal2024@vitstudent.ac.in |
| 3 | Naman Chauhan | Naman.chauhan2024@vitstudent.ac.in |
| 4 | Upayan Mazumder | upayan.mazumder2024@vitstudent.ac.in |

---

## System Architecture

```
[Arduino UNO Q Helmet]
        │
        │  sensor readings via WiFi/BLE
        ▼
[Snapdragon AI PC] ◄── [USB Camera Feed]
        │                    │
        │                    └── YOLO PPE Detection
        │
        ├── Sensor Fusion Engine
        ├── Risk Scoring
        │
        ▼
[Mobile Dashboard]
   real-time alerts + worker status
```

---

## Hardware Requirements

| Component | Purpose |
|-----------|---------|
| Snapdragon X Series Copilot+ PC | Edge AI inference + fusion engine |
| Arduino UNO Q | Helmet microcontroller |
| Qualcomm AI Cloud 100 | Cloud offload (optional) |
| Android mobile device | Alert dashboard |
| USB camera (fixed mount) | PPE + zone detection |
| MPU-6050 | Accelerometer + gyroscope (motion) |
| MQ-2 | Gas sensor (LPG, smoke, propane) |
| MQ-7 | Carbon monoxide sensor |
| DHT-22 | Temperature + humidity |
| MLX90614 | IR body temperature |
| MAX30102 | Heart rate + SpO2 |
| Sound sensor | Noise level detection |
| FSR | Helmet fit / pressure |
| Flex sensor | Head tilt detection |
| GPS module | Worker location |
| Buzzer | On-helmet alert |

---

## Setup Instructions

### 1. Clone the repo
```bash
git clone https://github.com/[your-username]/snapdragon-multiverse-safeguard
cd snapdragon-multiverse-safeguard
```

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3. Flash Arduino firmware
```
1. Open helmet/helmet_firmware.ino in Arduino IDE
2. Select board: Arduino UNO Q
3. Upload firmware
```

### 4. Download AI models
```bash
bash models/download_models.sh
```

### 5. Run the edge AI pipeline
```bash
python edge_ai/sensor_fusion.py
```

### 6. Launch mobile dashboard
```bash
python dashboard/app.py
```

---

## Usage

1. Power on the helmet
2. Run `sensor_fusion.py` on the Snapdragon AI PC
3. Open the dashboard on your mobile browser at `[IP]:5000`
4. System begins monitoring automatically

---

## Project Structure

```
snapdragon-multiverse-safeguard/
├── helmet/
│   └── helmet_firmware.ino       # Arduino UNO Q firmware
├── edge_ai/
│   ├── ppe_detection.py          # YOLO PPE detection on camera feed
│   ├── anomaly_movement.py       # IMU-based movement anomaly detection
│   └── sensor_fusion.py          # Sensor fusion + risk scoring engine
├── dashboard/
│   └── app.py                    # Mobile alert dashboard (Flask)
├── models/
│   └── download_models.sh        # Model weight download script
├── tests/
│   └── test_sensor_fusion.py
└── docs/
    └── architecture.png
```

---

## License

MIT License — see [LICENSE](LICENSE)
