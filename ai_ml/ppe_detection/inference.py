"""ONNX Runtime inference for YOLOv8 detection + pose (Snapdragon ARM64 / NPU).

No ultralytics, no OpenCV. Runs on onnxruntime(-qnn) + numpy + Pillow, so the same
code runs on the dev machine (CPU) and the Snapdragon (Hexagon NPU via QNN).

Frames are HxWx3 uint8 **RGB** numpy arrays (what PyAV hands us).
"""

import logging

import numpy as np
import onnxruntime as ort
from PIL import Image

logger = logging.getLogger(__name__)

IMGSZ = 640

# Hexagon NPU (QNN) is an opt-in plugin; fall back to CPU if it's not installed.
try:
    import onnxruntime_qnn as _qnn

    ort.register_execution_provider_library("QNNExecutionProvider", _qnn.get_library_path())
    _HAVE_QNN = True
    logger.info("QNN execution provider registered")
except Exception:  # noqa: BLE001
    _HAVE_QNN = False
    logger.info("QNN not available; using CPU")


def _make_session(model_path: str) -> ort.InferenceSession:
    """Prefer NPU (QNN) -> GPU (DirectML) -> CPU, using whatever is installed."""
    avail = ort.get_available_providers()
    providers: list = []
    opts: list = []
    if _HAVE_QNN:  # onnxruntime-qnn -> Hexagon NPU
        providers.append("QNNExecutionProvider")
        opts.append({"backend_path": "QnnHtp.dll"})
    if "DmlExecutionProvider" in avail:  # onnxruntime-directml -> Adreno GPU
        providers.append("DmlExecutionProvider")
        opts.append({})
    providers.append("CPUExecutionProvider")
    opts.append({})
    try:
        sess = ort.InferenceSession(model_path, providers=providers, provider_options=opts)
        logger.info("ONNX session running on: %s", sess.get_providers())
        return sess
    except Exception:  # noqa: BLE001
        logger.exception("session (%s) failed, using CPU only", providers)
        return ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])


def letterbox(frame_rgb: np.ndarray, size: int = IMGSZ):
    """Resize keeping aspect ratio + pad to square. Returns (blob, scale, dx, dy)."""
    h, w = frame_rgb.shape[:2]
    r = min(size / w, size / h)
    nw, nh = int(round(w * r)), int(round(h * r))
    img = Image.fromarray(frame_rgb).resize((nw, nh), Image.BILINEAR)
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    dx, dy = (size - nw) // 2, (size - nh) // 2
    canvas.paste(img, (dx, dy))
    blob = (np.asarray(canvas, np.float32) / 255.0).transpose(2, 0, 1)[None]
    return blob, r, dx, dy


def _cxcywh_to_xyxy(b: np.ndarray) -> np.ndarray:
    cx, cy, w, h = b[:, 0], b[:, 1], b[:, 2], b[:, 3]
    return np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_thres: float = 0.45) -> list[int]:
    """Greedy NMS. boxes: (N,4) xyxy. Returns kept indices."""
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
        order = order[1:][iou <= iou_thres]
    return keep


def _scale_back(pts_x, pts_y, r, dx, dy):
    """Map coords from 640 letterbox space back to original frame."""
    return (pts_x - dx) / r, (pts_y - dy) / r


class PPEDetector:
    """YOLOv8 detection -> list of {bbox(xyxy), cls, name, conf} in original coords."""

    def __init__(self, model_path: str, names: dict, conf: float = 0.35, iou: float = 0.45):
        self.session = _make_session(model_path)
        self.input_name = self.session.get_inputs()[0].name
        self.names = names
        self.conf = conf
        self.iou = iou

    def detect(self, frame_rgb: np.ndarray) -> list[dict]:
        blob, r, dx, dy = letterbox(frame_rgb)
        out = self.session.run(None, {self.input_name: blob})[0]  # (1, 4+nc, 8400)
        preds = out[0].T
        scores = preds[:, 4:]
        cls = scores.argmax(1)
        conf = scores.max(1)
        m = conf > self.conf
        if not m.any():
            return []
        xyxy = _cxcywh_to_xyxy(preds[m, :4])
        conf, cls = conf[m], cls[m]
        dets = []
        for i in _nms(xyxy, conf, self.iou):
            x1, y1 = _scale_back(xyxy[i, 0], xyxy[i, 1], r, dx, dy)
            x2, y2 = _scale_back(xyxy[i, 2], xyxy[i, 3], r, dx, dy)
            dets.append({
                "bbox": [float(x1), float(y1), float(x2), float(y2)],
                "cls": int(cls[i]),
                "name": self.names[int(cls[i])],
                "conf": float(conf[i]),
            })
        return dets


class PoseDetector:
    """YOLOv8-pose -> list of {bbox(xyxy), conf, keypoints(17,3)} in original coords."""

    def __init__(self, model_path: str, conf: float = 0.5, iou: float = 0.45):
        self.session = _make_session(model_path)
        self.input_name = self.session.get_inputs()[0].name
        self.conf = conf
        self.iou = iou

    def detect(self, frame_rgb: np.ndarray) -> list[dict]:
        blob, r, dx, dy = letterbox(frame_rgb)
        out = self.session.run(None, {self.input_name: blob})[0]  # (1, 56, 8400)
        preds = out[0].T
        conf = preds[:, 4]
        m = conf > self.conf
        if not m.any():
            return []
        preds = preds[m]
        xyxy = _cxcywh_to_xyxy(preds[:, :4])
        persons = []
        for i in _nms(xyxy, preds[:, 4], self.iou):
            kpts = preds[i, 5:].reshape(17, 3).copy()
            kpts[:, 0], kpts[:, 1] = _scale_back(kpts[:, 0], kpts[:, 1], r, dx, dy)
            x1, y1 = _scale_back(xyxy[i, 0], xyxy[i, 1], r, dx, dy)
            x2, y2 = _scale_back(xyxy[i, 2], xyxy[i, 3], r, dx, dy)
            persons.append({
                "bbox": [float(x1), float(y1), float(x2), float(y2)],
                "conf": float(preds[i, 4]),
                "keypoints": kpts,  # (17,3) x,y in original coords + visibility
            })
        return persons


def foot_point(kpts: np.ndarray, vis: float = 0.3):
    """Pick the ground-contact point: visible ankle (15/16), fall back to hip (11/12).

    Returns (x, y) in original coords, or None if nothing usable.
    """
    la, ra = kpts[15], kpts[16]
    if la[2] > vis or ra[2] > vis:
        fp = la[:2] if la[2] >= ra[2] else ra[:2]
    else:
        lh, rh = kpts[11], kpts[12]
        fp = lh[:2] if lh[2] >= rh[2] else rh[:2]
    if fp[0] == 0 and fp[1] == 0:
        return None
    return float(fp[0]), float(fp[1])


def point_in_polygon(x: float, y: float, poly: np.ndarray) -> bool:
    """Ray-casting point-in-polygon test. poly: (N,2). Replaces cv2.pointPolygonTest."""
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside
