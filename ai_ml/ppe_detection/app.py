import logging
import os
import platform
import sys
import threading
import time
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


CAMERA_INDEX    = int(os.getenv("CAMERA_INDEX",    "1"))
PROCESS_EVERY_N = int(os.getenv("PROCESS_EVERY_N", "1"))
STREAM_QUALITY  = int(os.getenv("STREAM_QUALITY",  "85"))
_CAM_BACKEND    = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_V4L2


def _make_no_signal_jpeg() -> bytes:
    h, w = 480, 640
    frame = np.full((h, w, 3), 14, dtype=np.uint8)
    cx, cy = w // 2, h // 2
    for x in range(0, w, 40):
        cv2.line(frame, (x, 0), (x, h), (28, 28, 28), 1)
    for y in range(0, h, 40):
        cv2.line(frame, (0, y), (w, y), (28, 28, 28), 1)
    text = "NO SIGNAL"
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, 1.4, 2)
    cv2.putText(frame, text, (cx - tw // 2, cy + th // 2),
                cv2.FONT_HERSHEY_DUPLEX, 1.4, (255, 231, 52), 2, cv2.LINE_AA)
    sub = "AWAITING VIDEO FEED"
    (sw, _), _ = cv2.getTextSize(sub, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.putText(frame, sub, (cx - sw // 2, cy + th // 2 + 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 120, 120), 1, cv2.LINE_AA)
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buf.tobytes()


_NO_SIGNAL_BYTES = _make_no_signal_jpeg()


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
    cache_lock  = threading.Lock()
    cached_jpeg = [_NO_SIGNAL_BYTES]   # always has something to yield

    slot_lock  = threading.Lock()
    slot_frame = [None]
    slot_event = threading.Event()
    stop_event = threading.Event()

    def _inference_worker():
        while not stop_event.is_set():
            slot_event.wait()
            slot_event.clear()
            if stop_event.is_set():
                break
            with slot_lock:
                frame = slot_frame[0]
            if frame is None:
                continue
            try:
                annotated, _ = _detector.detect(frame)
                ok, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, STREAM_QUALITY])
                if ok:
                    with cache_lock:
                        cached_jpeg[0] = buf.tobytes()
            except Exception:
                logger.exception("inference worker error")

    worker = threading.Thread(target=_inference_worker, daemon=True)
    worker.start()

    cap = cv2.VideoCapture(CAMERA_INDEX, _CAM_BACKEND)
    frame_count = 0
    t_start = time.time()

    try:
        while True:
            ok, raw = cap.read()
            if not ok:
                time.sleep(0.1)
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + _NO_SIGNAL_BYTES + b"\r\n"
                continue

            if frame_count % PROCESS_EVERY_N == 0:
                with slot_lock:
                    slot_frame[0] = raw.copy()
                slot_event.set()
            frame_count += 1

            with cache_lock:
                jpeg = cached_jpeg[0]

            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"

            elapsed = time.time() - t_start
            if elapsed >= 5.0:
                logger.info("stream fps=%.1f", frame_count / elapsed)
                frame_count = 0
                t_start = time.time()

    finally:
        stop_event.set()
        slot_event.set()   # wake worker so it can observe stop
        cap.release()


@app.get("/stream")
def stream() -> StreamingResponse:
    if not _ready:
        raise HTTPException(503, "model not loaded")
    return StreamingResponse(
        _frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
