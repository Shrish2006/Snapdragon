# SafeGuard

> AI-Powered Industrial Worker Safety System
> Snapdragon Multiverse Hackathon 2026, Bangalore

## Links

[![Website](https://img.shields.io/badge/Website-snapdragon.upayan.dev-1565c0?style=flat-square)](https://snapdragon.upayan.dev)
[![Docs](https://img.shields.io/badge/Docs-snapdragon.upayan.dev%2Fdocs-2e7d32?style=flat-square)](https://snapdragon.upayan.dev/docs)
[![Figma](https://img.shields.io/badge/Design-Figma-6a1b9a?style=flat-square&logo=figma&logoColor=white)](https://www.figma.com/design/xhDEKBv90xZaSRzgfoD8gZ/SafeGuard?node-id=33-2)

## Overview

SafeGuard is an AI-powered system that helps keep industrial workers safe in
real time. It pairs a sensor-equipped smart helmet with a camera-based vision
system to watch over each worker on site. The helmet tracks a worker's
surroundings and wellbeing, while the vision system checks that safety gear is
worn and spots dangerous situations. Both streams come together into a single,
easy-to-read measure of risk. When something goes wrong, supervisors are alerted
instantly on a live dashboard and the worker's helmet can respond on the spot.
The goal is simple: catch hazards early and keep people safe.

## Architecture

```mermaid
flowchart TB
    subgraph Edge["Edge devices"]
        Helmet["Smart Helmet<br/>(Arduino UNO Q)<br/>IMU · gas · CO · temp · sound"]
        Cam["USB Camera<br/>(fixed mount)"]
    end

    subgraph AI["AI / CV services"]
        PPE["PPE Detection<br/>(YOLOv8 pose)"]
        Fall["Fall Detection"]
    end

    subgraph Core["Gateway (FastAPI)"]
        Ingest["Telemetry ingestion"]
        Fusion["Sensor fusion<br/>+ risk scoring"]
        Events["Event bus"]
    end

    Dash["Dashboard<br/>(Next.js)"]

    Helmet -->|"MQTT telemetry<br/>safeguard/telemetry/{id}"| Ingest
    Cam --> PPE
    Cam --> Fall
    PPE -->|detections| Fusion
    Fall -->|detections| Fusion
    Ingest --> Fusion
    Fusion --> Events
    Events -->|"WebSocket / REST"| Dash
    Fusion -.->|"MQTT command<br/>buzzer alert"| Helmet

    classDef edge fill:#e8f5e9,stroke:#2e7d32,color:#0d1b2a;
    classDef ai fill:#f3e5f5,stroke:#6a1b9a,color:#0d1b2a;
    classDef core fill:#fff3e0,stroke:#e65100,color:#0d1b2a;
    class Helmet,Cam edge;
    class PPE,Fall ai;
    class Ingest,Fusion,Events core;
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Helmet firmware | Arduino UNO Q, MQTT |
| Vision / AI | YOLOv8 pose (ONNX), FastAPI |
| Gateway | Python, FastAPI, Mosquitto, Redis, PostgreSQL |
| Dashboard | Next.js |
| Infra | Docker, Kubernetes, GitHub Actions (GHCR) |

## Team

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/Shrish2006">
        <img src="https://avatars.githubusercontent.com/u/105660739?v=4" width="80" height="80" alt="Shrish Makwana"><br/>
        <sub><b>Shrish Makwana</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/ankitagrawal282">
        <img src="https://avatars.githubusercontent.com/u/182234554?v=4" width="80" height="80" alt="Ankit Agrawal"><br/>
        <sub><b>Ankit Agrawal</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/namanch6">
        <img src="https://avatars.githubusercontent.com/u/255293838?v=4" width="80" height="80" alt="Naman Chauhan"><br/>
        <sub><b>Naman Chauhan</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/upayanmazumder">
        <img src="https://avatars.githubusercontent.com/u/143063269?v=4" width="80" height="80" alt="Upayan Mazumder"><br/>
        <sub><b>Upayan Mazumder</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/Cheetos-gif">
        <img src="https://avatars.githubusercontent.com/u/182199486?v=4" width="80" height="80" alt="Chitrita Gahlot"><br/>
        <sub><b>Chitrita Gahlot</b></sub>
      </a>
    </td>
  </tr>
</table>

## License

Released under the [MIT License](LICENSE).
