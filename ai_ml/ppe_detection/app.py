"""SafeGuard PPE + Virtual Fencing — ONNX Runtime pipeline (Snapdragon ARM64 / NPU).

OpenCV-free, ultralytics-free, torch-free. Runs on:
  onnxruntime(-qnn) + numpy + Pillow + pygrabber (camera)
so the same code runs on the dev machine (CPU) and the Snapdragon (Hexagon NPU).

Camera + inference live on one worker thread (keeps pygrabber's COM on one thread);
the MJPEG endpoint just serves the latest annotated JPEG, decoupled from inference rate.
"""

import io
import json
import logging
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from PIL import Image
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
import drawing as dw
from camera import Camera
from config import setup_logging
from inference import PoseDetector, PPEDetector, foot_point, point_in_polygon

setup_logging()
logger = logging.getLogger(__name__)

HERE = Path(__file__).parent
POSE_MODEL = str(HERE / "yolov8n-pose.onnx")
PPE_MODEL = str(HERE / "best.onnx")
PPE_NAMES = {
    0: "Fall-Detected",
    1: "Gloves",
    2: "Goggles",
    3: "Hardhat",
    4: "Ladder",
    5: "Mask",
    6: "NO-Gloves",
    7: "NO-Goggles",
    8: "NO-Hardhat",
    9: "NO-Mask",
    10: "NO-Safety Vest",
    11: "Person",
    12: "Safety Cone",
    13: "Safety Vest",
}

CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
CAMERA_SWAP_RB = bool(
    int(os.getenv("CAMERA_SWAP_RB", "0"))
)  # set 1 if colors look swapped
STREAM_QUALITY = int(os.getenv("STREAM_QUALITY", "85"))
DEBUG_POSE = bool(int(os.getenv("DEBUG_POSE", "0")))
ZONE_HOLD_SECS = 1.2  # keep zone red briefly after last trigger (anti-flicker)
FAILURE_LIMIT = 5

_pose: PoseDetector | None = None
_ppe: PPEDetector | None = None
_ready = False

# ── ROI (virtual fencing), hot-reloadable ──
_roi_points: np.ndarray | None = None
_roi_lock = threading.Lock()
ROI_FILE = HERE / "roi.json"

# ── stream state ──
_latest_jpeg: bytes | None = None
_stop = threading.Event()
_worker_thread: threading.Thread | None = None


def _load_roi() -> None:
    global _roi_points
    if not ROI_FILE.exists():
        return
    try:
        pts = json.loads(ROI_FILE.read_text())
        if isinstance(pts, list) and len(pts) >= 3:
            with _roi_lock:
                _roi_points = np.array(pts, dtype=np.int32)
            logger.info("ROI loaded: %d points", len(pts))
    except Exception:  # noqa: BLE001
        logger.exception("failed to load roi.json")


def _save_roi(pts: list) -> None:
    try:
        ROI_FILE.write_text(json.dumps(pts))
    except Exception:  # noqa: BLE001
        logger.exception("failed to save roi.json")


def _encode_jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=STREAM_QUALITY)
    return buf.getvalue()


_NO_SIGNAL_JPEG = _encode_jpeg(dw.no_signal_image())


def _worker() -> None:
    """Owns the camera; grabs -> infers -> draws -> encodes -> publishes latest JPEG."""
    global _latest_jpeg
    import comtypes

    comtypes.CoInitialize()  # DirectShow/COM must be initialised on this thread
    cam = Camera(CAMERA_INDEX, swap_rb=CAMERA_SWAP_RB)
    fails = warmup = 0
    zone_hold_until = 0.0

    while not _stop.is_set():
        frame = cam.read()
        if frame is None:
            fails += 1
            if fails >= FAILURE_LIMIT:
                _latest_jpeg = _NO_SIGNAL_JPEG
                logger.warning("camera lost, reopening…")
                cam.reopen()
                fails = 0
            time.sleep(0.1)
            continue
        fails = 0
        if warmup < 2:  # first frames are often garbage
            warmup += 1
            continue

        try:
            persons = _pose.detect(frame)
            dets = _ppe.detect(frame)

            with _roi_lock:
                poly = _roi_points

            feet, triggered = [], False
            for p in persons:
                fp = foot_point(p["keypoints"])
                if fp is None:
                    continue
                inside = poly is not None and point_in_polygon(fp[0], fp[1], poly)
                triggered = triggered or inside
                feet.append((fp, inside))

            now = time.time()
            if triggered:
                zone_hold_until = now + ZONE_HOLD_SECS
                logger.warning("zone_triggered: foot in restricted area")
            show_red = now < zone_hold_until

            img = Image.fromarray(frame)
            img = dw.draw_zone(img, poly, show_red)
            if DEBUG_POSE:
                dw.draw_skeleton(img, persons)
            dw.draw_feet(img, feet)
            dw.draw_ppe(img, dets)
            _latest_jpeg = _encode_jpeg(img)
        except Exception:  # noqa: BLE001
            logger.exception("worker error")

    cam.close()
    comtypes.CoUninitialize()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    global _pose, _ppe, _ready, _worker_thread, _latest_jpeg
    _load_roi()
    _pose = PoseDetector(POSE_MODEL)
    _ppe = PPEDetector(PPE_MODEL, PPE_NAMES)
    _latest_jpeg = _NO_SIGNAL_JPEG
    _stop.clear()
    _worker_thread = threading.Thread(target=_worker, daemon=True)
    _worker_thread.start()
    _ready = True
    yield
    _ready = False
    _stop.set()


app = FastAPI(title="SafeGuard PPE + Virtual Fencing (ONNX)", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    if not _ready:
        raise HTTPException(503, "model not loaded")
    return {"status": "ok"}


@app.get("/api/roi")
def get_roi() -> JSONResponse:
    with _roi_lock:
        pts = _roi_points
    return JSONResponse(
        {
            "points": [] if pts is None else pts.tolist(),
            "frame": {"width": 640, "height": 480},
        }
    )


class ROIRequest(BaseModel):
    points: list[list[int]]


@app.post("/set-roi")
def set_roi(body: ROIRequest) -> JSONResponse:
    if len(body.points) < 3:
        raise HTTPException(422, "at least 3 points required")
    global _roi_points
    with _roi_lock:
        _roi_points = np.array(body.points, dtype=np.int32)
    _save_roi(body.points)
    logger.info("ROI updated via API (%d points)", len(body.points))
    return JSONResponse({"status": "updated", "points": body.points})


@app.post("/detect")
async def detect(file: UploadFile = File(...)) -> JSONResponse:
    if not _ready:
        raise HTTPException(503, "model not loaded")
    data = await file.read()
    try:
        frame = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "invalid image data")
    dets = _ppe.detect(frame)
    out = [
        {"class_name": d["name"], "confidence": d["conf"], "bbox": d["bbox"]}
        for d in dets
    ]
    return JSONResponse({"detections": out})


def _mjpeg():
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    while True:
        yield boundary + (_latest_jpeg or _NO_SIGNAL_JPEG) + b"\r\n"
        time.sleep(0.03)


@app.get("/stream")
def stream() -> StreamingResponse:
    if not _ready:
        raise HTTPException(503, "model not loaded")
    return StreamingResponse(
        _mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame"
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
