# SafeGuard — Architecture Diagrams

High-level block diagrams of the SafeGuard industrial worker safety system, at
three levels of technical depth. All render as Mermaid.

SafeGuard fuses two streams into a unified risk score: a sensor-equipped smart
helmet (Arduino UNO Q) streaming telemetry over MQTT, and a fixed camera feed
running computer-vision PPE / fall detection. Alerts surface on a Next.js
dashboard and can buzz the helmet back.

---

## 1. Less technical — plain-language / stakeholder view

What it does, no jargon.

```mermaid
flowchart LR
    Worker(["Worker wearing<br/>smart helmet"])
    Camera(["Site camera"])
    Brain(["SafeGuard<br/>safety brain"])
    Phone(["Supervisor<br/>dashboard"])

    Worker -->|"body & air readings<br/>(heart rate, gas, motion)"| Brain
    Camera -->|"live video<br/>(is gear worn?)"| Brain
    Brain -->|"combines both,<br/>scores the danger"| Phone
    Phone -->|"buzz the helmet<br/>on danger"| Worker

    classDef people fill:#e3f2fd,stroke:#1565c0,color:#0d1b2a;
    classDef core fill:#fff3e0,stroke:#e65100,color:#0d1b2a;
    class Worker,Camera,Phone people;
    class Brain core;
```

---

## 2. Medium technical — component / data-flow view

Named components, real protocols, the two fused streams.

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

---

## 3. Highly technical — system architecture view

Deployment topology, gateway hexagonal layers, data stores, protocols.

```mermaid
flowchart TB
    subgraph Field["Field / Edge"]
        HW["Helmet FW<br/>Arduino UNO Q + WiFiNINA<br/>2 Hz TelemetryBatch (JSON)"]
        CAM["USB Camera"]
    end

    MQTT["Mosquitto Broker<br/>MQTT :1883 / NodePort :31883<br/>topics: telemetry · status(LWT) · command"]

    subgraph GW["Gateway — FastAPI (hexagonal)"]
        API["API layer<br/>HTTP /v1/* · WS /v1/ws · /metrics"]
        APP["Application<br/>ingestion · detection · subscription<br/>device registry · state manager · ports"]
        WRK["Workers<br/>processing pipeline<br/>+ persistence processor"]
        INFRA["Infrastructure adapters<br/>MQTT adapter · presence · cmd publisher<br/>ml_clients · bus · persistence · metrics"]
        DOM["Domain<br/>telemetry · helmets · events · detection"]
        API --> APP --> DOM
        APP --> INFRA
        APP --> WRK
        WRK --> INFRA
    end

    subgraph MLsvc["AI/ML services (FastAPI)"]
        PPE["ppe-detection :8000<br/>YOLOv8n-pose ONNX<br/>/detect · /stream · virtual fencing"]
        FALL["fall-detection :8000"]
    end

    subgraph Data["Stateful backends"]
        PG[("PostgreSQL 16<br/>event store")]
        RD[("Redis 7<br/>Streams event bus")]
    end

    UI["Next.js dashboard<br/>standalone build :3000"]

    HW -->|"MQTT pub QoS1"| MQTT
    MQTT -->|"subscribe"| INFRA
    INFRA -.->|"MQTT command<br/>buzzer/config"| MQTT --> HW
    CAM --> PPE
    CAM --> FALL
    INFRA -->|"HTTP client"| PPE
    INFRA -->|"HTTP client"| FALL
    INFRA -->|"asyncpg"| PG
    INFRA -->|"XADD / XREAD"| RD
    UI -->|"REST + WebSocket"| API

    classDef field fill:#e8f5e9,stroke:#2e7d32,color:#0d1b2a;
    classDef broker fill:#e0f7fa,stroke:#00838f,color:#0d1b2a;
    classDef gw fill:#fff3e0,stroke:#e65100,color:#0d1b2a;
    classDef ml fill:#f3e5f5,stroke:#6a1b9a,color:#0d1b2a;
    classDef data fill:#fce4ec,stroke:#ad1457,color:#0d1b2a;
    class HW,CAM field;
    class MQTT broker;
    class API,APP,WRK,INFRA,DOM gw;
    class PPE,FALL ml;
    class PG,RD data;
```
