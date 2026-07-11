import logging
import platform
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import setup_logging
from ppe_detection import PPEDetector

setup_logging()
logger = logging.getLogger(__name__)

_detector: PPEDetector | None = None
_ready = False

CAMERA_INDEX = int(__import__("os").getenv("CAMERA_INDEX", "0"))
_CAM_BACKEND = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_V4L2


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    global _detector, _ready
    _detector = PPEDetector()
    _ready = True
    yield
    _ready = False


app = FastAPI(title="SafeGuard PPE Detection", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    if not _ready:
        raise HTTPException(503, "model not loaded")
    return {"status": "ok"}


@app.post("/detect")
async def detect(file: UploadFile = File(...)) -> JSONResponse:
    if not _ready:
        raise HTTPException(503, "model not loaded")
    data = await file.read()
    arr = np.frombuffer(data, np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(400, "invalid image data")
    _, detections = _detector.detect(frame)
    return JSONResponse({"detections": detections})


def _frame_generator():
    cap = cv2.VideoCapture(CAMERA_INDEX, _CAM_BACKEND)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                logger.warning("frame grab failed, stopping stream")
                break
            annotated, _ = _detector.detect(frame)
            _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                + buf.tobytes()
                + b"\r\n"
            )
    finally:
        cap.release()


@app.get("/stream")
def stream() -> StreamingResponse:
    if not _ready:
        raise HTTPException(503, "model not loaded")
    return StreamingResponse(
        _frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
