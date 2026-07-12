"""SafeGuard PPE + Virtual Fencing — ONNX Runtime pipeline (Snapdragon ARM64 / NPU).

Runs on Linux (V4L2/OpenCV camera) and Windows (DirectShow/pygrabber camera).
OpenCV-free in model inference; ultralytics-free; torch-free.

Two-thread design:
  _capture_thread  — owns the Camera; grabs frames as fast as V4L2 delivers them
                     and writes the latest into _latest_frame (1-slot buffer).
  _worker_thread   — reads _latest_frame, runs inference, draws, encodes JPEG,
                     publishes to _latest_jpeg for the MJPEG HTTP endpoint.
This decoupling ensures inference latency never causes stale-frame accumulation.
"""

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
import cv2
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
import drawing as dw

try:
    from camera import Camera
except Exception:  # noqa: BLE001
    Camera = None  # camera module or its deps unavailable — /stream disabled
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
_latest_frame: np.ndarray | None = None  # RGB; written by capture thread
_frame_lock = threading.Lock()
_latest_jpeg: bytes | None = None  # written by inference thread
_stop = threading.Event()
_capture_thread: threading.Thread | None = None
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


def _encode_jpeg(frame_rgb: np.ndarray) -> bytes:
    """Encode an RGB uint8 ndarray to JPEG bytes via cv2 (5-10× faster than PIL)."""
    ok, buf = cv2.imencode(
        ".jpg",
        frame_rgb[:, :, ::-1],  # RGB→BGR for cv2
        [cv2.IMWRITE_JPEG_QUALITY, STREAM_QUALITY],
    )
    return buf.tobytes() if ok else b""


def _make_no_signal_jpeg() -> bytes:
    img_pil = dw.no_signal_image()
    arr = np.array(img_pil)
    return _encode_jpeg(arr)


_NO_SIGNAL_JPEG = _make_no_signal_jpeg()


def _capture() -> None:
    """Camera-owning thread: grabs frames as fast as V4L2 delivers and
    writes the latest RGB ndarray into _latest_frame (1-slot buffer).
    Decoupled from inference so slow YOLO runs never stall the grab loop."""
    global _latest_frame

    if Camera is None:
        logger.warning("Camera not available — stream disabled, /detect still works")
        _stop.wait()
        return

    import platform

    _windows = platform.system() == "Windows"
    if _windows:
        import comtypes

        comtypes.CoInitialize()

    cam = Camera(CAMERA_INDEX, swap_rb=CAMERA_SWAP_RB)
    fails = warmup = 0

    while not _stop.is_set():
        frame = cam.read()
        if frame is None:
            fails += 1
            if fails >= FAILURE_LIMIT:
                with _frame_lock:
                    _latest_frame = None
                logger.warning("camera lost, reopening…")
                cam.reopen()
                fails = 0
            time.sleep(0.05)
            continue
        fails = 0
        if warmup < 3:  # discard first 3 frames — V4L2 ring-buffer flush
            warmup += 1
            continue
        with _frame_lock:
            _latest_frame = frame  # inference thread picks this up

    cam.close()
    if _windows:
        import comtypes

        comtypes.CoUninitialize()


def _worker() -> None:
    """Inference thread: reads latest frame, runs YOLO×2, draws overlays,
    encodes JPEG, publishes to _latest_jpeg for the MJPEG endpoint."""
    global _latest_jpeg

    zone_hold_until = 0.0
    last_frame_id = id(None)  # skip if no new frame since last iteration

    while not _stop.is_set():
        with _frame_lock:
            frame = _latest_frame

        if frame is None or id(frame) == last_frame_id:
            time.sleep(0.005)
            continue
        last_frame_id = id(frame)

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

            from PIL import Image as _Image

            img = _Image.fromarray(frame)
            img = dw.draw_zone(img, poly, show_red)
            if DEBUG_POSE:
                dw.draw_skeleton(img, persons)
            dw.draw_feet(img, feet)
            dw.draw_ppe(img, dets)
            drawn = np.array(img)
            _latest_jpeg = _encode_jpeg(drawn)
        except Exception:  # noqa: BLE001
            logger.exception("worker error")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    global _pose, _ppe, _ready, _capture_thread, _worker_thread, _latest_jpeg
    _load_roi()
    _pose = PoseDetector(POSE_MODEL)
    _ppe = PPEDetector(PPE_MODEL, PPE_NAMES)
    _latest_jpeg = _NO_SIGNAL_JPEG
    _stop.clear()
    _capture_thread = threading.Thread(target=_capture, daemon=True, name="cam-grab")
    _worker_thread = threading.Thread(target=_worker, daemon=True, name="inference")
    _capture_thread.start()
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
