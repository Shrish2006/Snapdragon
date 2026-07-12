#!/usr/bin/env python3
"""Seed the Safeguard Postgres event store and helmet registry with
realistic sample data for local development.

Usage
-----
    uv run --project gateway python scripts/seed.py
    uv run --project gateway python scripts/seed.py --gateway-url http://localhost:8080
    uv run --project gateway python scripts/seed.py --direct-db --dsn postgresql://safeguard:safeguard@localhost:5432/safeguard
    uv run --project gateway python scripts/seed.py --clear          # wipe then seed
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta, timezone

# ── bootstrap ───────────────────────────────────────────────────────────
# Allow importing gateway packages when run from the project root.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() or "__file__" in globals() else os.getcwd()
sys.path.insert(0, os.path.join(_SCRIPT_DIR, "..", "gateway", "src"))
# ── sample data ─────────────────────────────────────────────────────────

HELMETS = [
    "HLM-0001",
    "HLM-0002",
    "HLM-0003",
    "HLM-0004",
    "HLM-0005",
]

# How far back the first batch for each helmet starts (hours).
INITIAL_OFFSET_HOURS = 72
BATCH_INTERVAL_MINUTES = 5  # one batch every 5 min
BATCHES_PER_HELMET = 20  # number of telemetry batches per helmet

SENSOR_TYPES = ["imu", "environment", "gas_lpg", "carbon_monoxide", "sound_level"]


def _random_imu(ts: str) -> dict:
    ax = random.uniform(-2.0, 2.0)
    ay = random.uniform(-2.0, 2.0)
    az = random.uniform(0.5, 1.5)
    return {
        "kind": "imu",
        "accel_x_g": round(ax, 4),
        "accel_y_g": round(ay, 4),
        "accel_z_g": round(az, 4),
        "accel_magnitude_g": round((ax**2 + ay**2 + az**2) ** 0.5, 4),
        "gyro_x_dps": round(random.uniform(-50, 50), 2),
        "gyro_y_dps": round(random.uniform(-50, 50), 2),
        "gyro_z_dps": round(random.uniform(-50, 50), 2),
    }


def _random_environment(ts: str) -> dict:
    return {
        "kind": "environment",
        "temperature_c": round(random.uniform(20, 40), 1),
        "humidity_pct": round(random.uniform(30, 80), 1),
        "heat_index_c": round(random.uniform(20, 45), 1),
    }


def _random_gas(kind: str) -> dict:
    return {
        "kind": kind,
        "adc_raw": random.randint(0, 1023),
    }


def _random_sound() -> dict:
    return {
        "kind": "sound_level",
        "adc_raw": random.randint(0, 1023),
    }


def _pick_readings() -> list[dict]:
    """Return 2-4 sample readings, always including IMU."""
    readings = [
        {
            "value": _random_imu(""),
            "captured_at": (datetime.now(timezone.utc) - timedelta(minutes=random.randint(0, 5))).isoformat(),
        }
    ]
    kinds = random.sample(SENSOR_TYPES[1:], k=random.randint(1, 3))
    for k in kinds:
        captured = (datetime.now(timezone.utc) - timedelta(seconds=random.randint(0, 60))).isoformat()
        if k == "environment":
            readings.append({"value": _random_environment(""), "captured_at": captured})
        elif k in ("gas_lpg", "carbon_monoxide"):
            readings.append({"value": _random_gas(k), "captured_at": captured})
        elif k == "sound_level":
            readings.append({"value": _random_sound(), "captured_at": captured})
    return readings


def _build_batch(helmet_id: str, seq: int, base_time: datetime) -> dict:
    """Construct one TelemetryBatch JSON payload."""
    ts = base_time.isoformat()
    return {
        "helmet_id": helmet_id,
        "sequence": seq,
        "sent_at": ts,
        "readings": _pick_readings(),
    }


# ── API seeder ──────────────────────────────────────────────────────────

async def seed_via_api(gateway_url: str) -> None:
    """Send telemetry batches through the gateway HTTP API.

    This creates both events (in Postgres) and helmet state (in-memory
    registry), so the dashboard has data to display immediately.
    """
    import httpx

    base = gateway_url.rstrip("/")
    now = datetime.now(timezone.utc)

    print(f"Seeding {len(HELMETS)} helmets via {base}/v1/telemetry …")

    async with httpx.AsyncClient(base_url=base, timeout=30) as client:
        for helmet_id in HELMETS:
            offset = random.randint(0, INITIAL_OFFSET_HOURS)
            base_time = now - timedelta(hours=offset)
            accepted = 0
            rejected = 0

            for seq in range(1, BATCHES_PER_HELMET + 1):
                batch = _build_batch(helmet_id, seq, base_time)
                resp = await client.post("/v1/telemetry", json=batch)
                if resp.status_code == 202:
                    accepted += 1
                elif resp.status_code == 422:
                    rejected += 1
                base_time += timedelta(minutes=BATCH_INTERVAL_MINUTES)

            print(f"  {helmet_id}: {accepted} accepted, {rejected} rejected")

    print("Done — helmet state and events are populated.")


# ── Direct DB seeder ────────────────────────────────────────────────────

EVENT_TYPES = [
    "telemetry.received",
    "helmet.online",
    "helmet.offline",
    "ml.ppe_detection",
]

SAMPLE_DETECTIONS = [
    {"detections": [{"class_name": "helmet", "confidence": 0.95, "bbox": [120, 80, 300, 250], "tracker_id": 1}]},
    {"detections": [{"class_name": "vest", "confidence": 0.88, "bbox": [50, 100, 200, 300], "tracker_id": 2}]},
    {"detections": [
        {"class_name": "helmet", "confidence": 0.97, "bbox": [130, 70, 310, 260], "tracker_id": 3},
        {"class_name": "vest", "confidence": 0.91, "bbox": [40, 90, 210, 310], "tracker_id": 4},
    ]},
]


def _random_ppe_detection() -> dict:
    return random.choice(SAMPLE_DETECTIONS)


async def seed_direct_db(dsn: str, clear: bool = False) -> None:
    """Insert events directly into the Postgres event store.

    Use this when the gateway isn't running and you only need event history
    (helmet state remains empty — start the gateway and run without
    ``--direct-db`` to populate the in-memory registry).
    """
    import asyncpg
    import uuid

    conn = await asyncpg.connect(dsn)
    try:
        if clear:
            print("Clearing existing events …")
            await conn.execute("DELETE FROM events")

        count = 0
        for helmet_id in HELMETS:
            offset = random.randint(0, INITIAL_OFFSET_HOURS)
            base_time = datetime.now(timezone.utc) - timedelta(hours=offset)

            for seq in range(1, BATCHES_PER_HELMET + 1):
                occurred = base_time + timedelta(minutes=seq * BATCH_INTERVAL_MINUTES)

                # telemetry.received event
                batch = _build_batch(helmet_id, seq, occurred)
                await conn.execute(
                    "INSERT INTO events (event_id, event_type, helmet_id, occurred_at, payload_json) "
                    "VALUES ($1, $2, $3, $4, $5)",
                    str(uuid.uuid4()),
                    "telemetry.received",
                    helmet_id,
                    occurred,
                    __import__("json").dumps({"batch": batch}),
                )
                count += 1

                # Sprinkle in a PPE detection every ~5 batches
                if seq % 5 == 0:
                    await conn.execute(
                        "INSERT INTO events (event_id, event_type, helmet_id, occurred_at, payload_json) "
                        "VALUES ($1, $2, $3, $4, $5)",
                        str(uuid.uuid4()),
                        "ml.ppe_detection",
                        helmet_id,
                        occurred + timedelta(seconds=2),
                        __import__("json").dumps(_random_ppe_detection()),
                    )
                    count += 1

            # helmet.online at first event, helmet.offline at the end
            first_time = base_time + timedelta(minutes=BATCH_INTERVAL_MINUTES)
            last_time = base_time + timedelta(minutes=BATCHES_PER_HELMET * BATCH_INTERVAL_MINUTES)

            await conn.execute(
                "INSERT INTO events (event_id, event_type, helmet_id, occurred_at, payload_json) "
                "VALUES ($1, $2, $3, $4, $5)",
                str(uuid.uuid4()),
                "helmet.online",
                helmet_id,
                first_time - timedelta(seconds=5),
                __import__("json").dumps({"helmet_id": helmet_id}),
            )
            count += 1

            await conn.execute(
                "INSERT INTO events (event_id, event_type, helmet_id, occurred_at, payload_json) "
                "VALUES ($1, $2, $3, $4, $5)",
                str(uuid.uuid4()),
                "helmet.offline",
                helmet_id,
                last_time + timedelta(minutes=30),
                __import__("json").dumps({"helmet_id": helmet_id}),
            )
            count += 1

        print(f"Inserted {count} events across {len(HELMETS)} helmets.")
    finally:
        await conn.close()


# ── CLI ─────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed Safeguard dev database")
    parser.add_argument(
        "--gateway-url",
        default=os.environ.get("GATEWAY_URL", "http://localhost:8080"),
        help="Gateway base URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get(
            "POSTGRES_DSN",
            "postgresql://safeguard:safeguard@localhost:5432/safeguard",
        ),
        help="Postgres DSN (default: local compose)",
    )
    parser.add_argument(
        "--direct-db",
        action="store_true",
        help="Seed directly via Postgres (skip the HTTP API; no helmet state created)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete existing events before seeding",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()

    if args.direct_db:
        await seed_direct_db(dsn=args.dsn, clear=args.clear)
    else:
        print(f"Gateway: {args.gateway_url}")
        print("  (pass --direct-db to skip the API and seed Postgres directly)\n")
        await seed_via_api(gateway_url=args.gateway_url)


if __name__ == "__main__":
    asyncio.run(main())
