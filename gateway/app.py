import logging
import os
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

import httpx
from config import setup_logging
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect

setup_logging()
logger = logging.getLogger(__name__)

PPE_URL = os.getenv("PPE_URL", "http://ppe-detection:8000")
FALL_URL = os.getenv("FALL_URL", "http://fall-detection:8000")

_buf: deque[dict] = deque(maxlen=int(os.getenv("EVENT_BUFFER", "200")))
_subs: set[WebSocket] = set()
_http: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    global _http
    _http = httpx.AsyncClient(timeout=30.0)
    yield
    await _http.aclose()


app = FastAPI(title="SafeGuard Gateway", lifespan=lifespan)


# ── internal helpers ──────────────────────────────────────────────────────────

def _stamp(kind: str, data: dict) -> dict:
    return {"type": kind, "ts": datetime.now(timezone.utc).isoformat(), "data": data}


async def _broadcast(event: dict) -> None:
    dead: set[WebSocket] = set()
    for ws in _subs:
        try:
            await ws.send_json(event)
        except Exception:
            dead.add(ws)
    _subs.difference_update(dead)


async def _push(kind: str, data: dict) -> None:
    ev = _stamp(kind, data)
    _buf.append(ev)
    await _broadcast(ev)


# ── health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/status")
async def status() -> dict:
    services: dict[str, str] = {}
    for name, url in (("ppe", PPE_URL), ("fall", FALL_URL)):
        try:
            r = await _http.get(f"{url}/health", timeout=5.0)
            services[name] = "ok" if r.is_success else "degraded"
        except Exception:
            services[name] = "unreachable"
    return {"gateway": "ok", "services": services}


# ── detection proxy ───────────────────────────────────────────────────────────

@app.post("/detect/ppe")
async def detect_ppe(file: UploadFile = File(...)) -> dict:
    """Forward an image to ppe-detection, emit the result as an event."""
    data = await file.read()
    try:
        resp = await _http.post(
            f"{PPE_URL}/detect",
            files={"file": (file.filename, data, file.content_type or "image/jpeg")},
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, detail=str(exc)) from exc
    except httpx.RequestError as exc:
        raise HTTPException(503, detail=f"ppe-detection unreachable: {exc}") from exc
    result = resp.json()
    await _push("ppe_detection", result)
    return result


# ── event ingestion (ML services push here) ───────────────────────────────────

@app.post("/events/{service}")
async def ingest(service: str, payload: dict) -> dict:
    """ML services POST detection results here for storage and fan-out."""
    await _push(service, payload)
    logger.info("event from %s", service)
    return {"accepted": True}


# ── event query ───────────────────────────────────────────────────────────────

@app.get("/events")
def get_events(limit: int = 50) -> list:
    return list(_buf)[-limit:]


# ── realtime ──────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket(ws: WebSocket) -> None:
    await ws.accept()
    _subs.add(ws)
    logger.info("ws +1 (%d)", len(_subs))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _subs.discard(ws)
        logger.info("ws -1 (%d)", len(_subs))
