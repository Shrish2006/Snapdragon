from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fall_detection import MODEL_PATH, SCALER_PATH, FallInference
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class IngestRequest(BaseModel):
    helmet_id: str = Field(min_length=1, max_length=64)
    window: list[list[float]] = Field(min_length=1)
    """200 × 6 rows: [accel_x_g, accel_y_g, accel_z_g, gyro_x_dps, gyro_y_dps, gyro_z_dps]"""


class IngestResponse(BaseModel):
    fall_detected: bool
    probability: float


@asynccontextmanager
async def lifespan(app: FastAPI):
    if MODEL_PATH.exists() and SCALER_PATH.exists():
        app.state.model = FallInference()
        logger.info("FallInference loaded: %s", MODEL_PATH)
    else:
        app.state.model = None
        logger.warning("Model files not found at %s — /ingest returns 503", MODEL_PATH)
    yield


app = FastAPI(title="SafeGuard Fall Detection", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest) -> IngestResponse:
    if app.state.model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    prob = app.state.model.predict(req.window)
    return IngestResponse(fall_detected=False, probability=prob)
    # fall_detected is always False here — the gateway's FallDetectionProcessor
    # owns the debounce decision; the service returns the raw probability only
