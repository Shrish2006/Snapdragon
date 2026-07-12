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
| 5 | Chitrita Gahlot | chitrita.gahlot2024@vitstudent.ac.in |

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

## Quickstart (Docker Compose)

Requires Docker with Compose v2.

```bash
git clone https://github.com/Shrish2006/Snapdragon.git
cd Snapdragon
cp .env.example .env          # optional — sensible defaults apply without it
docker compose up --build
```

| Service | URL | Endpoints |
|---------|-----|-----------|
| app (dashboard) | http://localhost:3000 | Next.js UI, `/api/health` |
| gateway | http://localhost:8080 | `/v1/telemetry`, `/v1/helmets`, `/v1/detections/ppe`, `/v1/status`, `/v1/events`, `/v1/ws` (WebSocket), `/health`, `/ready`, `/metrics` |
| ppe_detection | http://localhost:8001 | `/health`, `/ready`, `/detect`, `/stream` |
| fall_detection | http://localhost:8002 | `/health` |

`docker compose up` runs the hot-reload dev stack (see `compose.override.yml`). For a
production-like run without overrides: `docker compose -f docker-compose.yml up --build`.

The PPE service runs CPU-only by default and downloads its model from HuggingFace on
first start. GPU + camera are opt-in — see the commented block in `docker-compose.yml`.

### Hardware / models (optional)

- Flash the helmet firmware: open `helmet/helmet_firmware.ino` in the Arduino IDE,
  select **Arduino UNO Q**, and upload.
- Model weights are pulled automatically at runtime; `models/download_models.sh` is a
  placeholder for pre-fetching them.

---

## Deployment

Full instructions: [docs/deployment.md](docs/deployment.md). Summary:

- **Images** are published to GHCR by CI:
  `ghcr.io/shrish2006/snapdragon/{app,gateway,ppe-detection,fall-detection}`.
- **Kubernetes:** `kubectl apply -k k8s/` deploys the whole stack to the `safeguard`
  namespace behind an Ingress at `snapdragon.upayan.dev` (app),
  `api-snapdragon.upayan.dev` (gateway), `ppe-snapdragon.upayan.dev`, and
  `fall-snapdragon.upayan.dev`.
- **Versioning:** push a `vX.Y.Z` tag to publish `X.Y.Z` / `X.Y` / `X` / `latest` images.

---

## Project Structure

```
Snapdragon/
├── app/                       # Next.js dashboard (standalone build, Dockerfile)
│   └── src/app/api/health/    # health endpoint for container probes
├── gateway/                   # FastAPI gateway (Dockerfile)
│   └── src/gateway/           # domain / application / infrastructure / api / workers layers
├── ai_ml/
│   ├── config.py              # shared JSON logging setup
│   ├── ppe_detection/         # FastAPI + YOLO PPE detection (Dockerfile)
│   └── fall_detection/        # FastAPI fall detection service (Dockerfile)
├── k8s/                       # Kubernetes manifests (kustomize)
├── .github/workflows/         # CI (lint/test/build) + CD (GHCR publish)
├── helmet/                    # Arduino UNO Q firmware
├── models/                    # model download helper
├── tests/                     # test suite (wired into CI)
├── docs/                      # documentation
├── docker-compose.yml         # local / single-host stack
└── compose.override.yml       # dev hot-reload overrides
```

---

## License

MIT License — see [LICENSE](LICENSE)
