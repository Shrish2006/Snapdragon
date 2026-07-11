import json
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
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import setup_logging
from ppe_detection import PPEDetector
from virtual_fencing import PoseDetector

setup_logging()
logger = logging.getLogger(__name__)

_ppe_detector:  PPEDetector  | None = None
_pose_detector: PoseDetector | None = None
_ready = False

CAMERA_INDEX    = int(os.getenv("CAMERA_INDEX",    "1"))
PROCESS_EVERY_N = int(os.getenv("PROCESS_EVERY_N", "1"))
STREAM_QUALITY  = int(os.getenv("STREAM_QUALITY",  "85"))
DEBUG_POSE      = bool(int(os.getenv("DEBUG_POSE",  "1")))
_CAM_BACKEND    = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_V4L2

# ── ROI (virtual fencing) ─────────────────────────────────────────────────────
_roi_points: np.ndarray | None = None
_roi_lock      = threading.Lock()
ROI_FILE       = Path(__file__).parent / "roi.json"
ZONE_HOLD_SECS = 1.2  # keep zone red briefly after last trigger (anti-flicker)


def _load_roi_file() -> None:
    global _roi_points
    if not ROI_FILE.exists():
        return
    try:
        pts = json.loads(ROI_FILE.read_text())
        if isinstance(pts, list) and len(pts) >= 3:
            with _roi_lock:
                _roi_points = np.array(pts, dtype=np.int32)
            logger.info("ROI loaded: %d points", len(pts))
    except Exception:
        logger.exception("failed to load roi.json")


def _save_roi_file(pts: list) -> None:
    try:
        ROI_FILE.write_text(json.dumps(pts))
    except Exception:
        logger.exception("failed to save roi.json")


# ── No-signal card ────────────────────────────────────────────────────────────
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


# ── App lifecycle ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    global _ppe_detector, _pose_detector, _ready
    _load_roi_file()
    _ppe_detector        = PPEDetector()
    _pose_detector       = PoseDetector()
    _pose_detector.debug = DEBUG_POSE
    _pose_detector.warmup()
    _ready = True
    yield
    _ready = False


app = FastAPI(title="SafeGuard PPE Detection", lifespan=lifespan)


# ── Endpoints ─────────────────────────────────────────────────────────────────
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
    _, detections = _ppe_detector.detect(frame)
    return JSONResponse({"detections": detections})


@app.get("/api/roi")
def get_roi() -> JSONResponse:
    with _roi_lock:
        pts = _roi_points
    return JSONResponse({
        "points": [] if pts is None else pts.tolist(),
        "frame":  {"width": 640, "height": 480},
    })


class ROIRequest(BaseModel):
    points: list[list[int]]


@app.post("/set-roi")
def set_roi(body: ROIRequest) -> JSONResponse:
    if len(body.points) < 3:
        raise HTTPException(422, "at least 3 points required")
    global _roi_points
    arr = np.array(body.points, dtype=np.int32)
    with _roi_lock:
        _roi_points = arr
    _save_roi_file(body.points)
    logger.info("ROI updated via API (%d points)", len(body.points))
    return JSONResponse({"status": "updated", "points": body.points})


# ── MJPEG stream ──────────────────────────────────────────────────────────────
def _frame_generator():
    cache_lock  = threading.Lock()
    cached_jpeg = [_NO_SIGNAL_BYTES]

    slot_lock  = threading.Lock()
    slot_frame = [None]
    slot_event = threading.Event()
    stop_event = threading.Event()

    zone_hold_until = [0.0]

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
                # 1. PPE detection (draws bboxes + labels)
                annotated, _ = _ppe_detector.detect(frame)

                # 2. Pose / virtual fencing (draws zone + ankle dots on top)
                with _roi_lock:
                    roi = _roi_points
                annotated, zone = _pose_detector.detect(annotated, roi)

                now = time.time()
                if zone:
                    zone_hold_until[0] = now + ZONE_HOLD_SECS

                ok, buf = cv2.imencode(
                    ".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, STREAM_QUALITY]
                )
                if ok:
                    with cache_lock:
                        cached_jpeg[0] = buf.tobytes()
            except Exception:
                logger.exception("inference worker error")

    worker = threading.Thread(target=_inference_worker, daemon=True)
    worker.start()

    cap             = cv2.VideoCapture(CAMERA_INDEX, _CAM_BACKEND)
    frame_count     = 0
    consec_failures = 0
    FAILURE_LIMIT   = 5
    WARMUP_FRAMES   = 5
    t_start         = time.time()

    try:
        while True:
            ok, raw = cap.read()

            if not ok:
                consec_failures += 1

                if consec_failures >= FAILURE_LIMIT:
                    with cache_lock:
                        cached_jpeg[0] = _NO_SIGNAL_BYTES
                    logger.warning("camera lost, reconnecting…")
                    cap.release()
                    time.sleep(3.0)
                    cap = cv2.VideoCapture(CAMERA_INDEX)
                    if not cap.isOpened():
                        cap.release()
                        cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_MSMF)
                    if not cap.isOpened():
                        cap.release()
                        cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
                    consec_failures = 0
                    frame_count = 0
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + _NO_SIGNAL_BYTES + b"\r\n"
                else:
                    with cache_lock:
                        jpeg = cached_jpeg[0]
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                continue

            consec_failures = 0
            frame_count += 1

            if frame_count <= WARMUP_FRAMES:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + _NO_SIGNAL_BYTES + b"\r\n"
                continue

            if frame_count % PROCESS_EVERY_N == 0:
                with slot_lock:
                    slot_frame[0] = raw.copy()
                slot_event.set()

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
        slot_event.set()
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
