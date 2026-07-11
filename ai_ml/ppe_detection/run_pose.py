"""Minimal YOLOv8-pose inference via ONNX Runtime on Snapdragon.

Runs the model with the Hexagon NPU (QNN) execution provider, falling back to CPU.
Deps (all have ARM64 wheels): onnxruntime-qnn, numpy, pillow
Usage:  python run_pose.py <image.jpg>
"""

import sys

import numpy as np
import onnxruntime as ort
from PIL import Image

MODEL = "yolov8n-pose.onnx"
IMGSZ = 640
CONF = 0.5

# ── register the Hexagon NPU (QNN) plugin execution provider ──
try:
    import onnxruntime_qnn as qnn_ep
    ort.register_execution_provider_library("QNNExecutionProvider", qnn_ep.get_library_path())
    _HAVE_QNN = True
except Exception as e:  # noqa: BLE001
    print("QNN EP not available, will use CPU:", e)
    _HAVE_QNN = False


def letterbox(img: Image.Image, size: int = IMGSZ):
    """Resize keeping aspect ratio, pad to square. Returns (canvas, scale, dx, dy)."""
    w, h = img.size
    r = min(size / w, size / h)
    nw, nh = int(round(w * r)), int(round(h * r))
    resized = img.resize((nw, nh), Image.BILINEAR)
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    dx, dy = (size - nw) // 2, (size - nh) // 2
    canvas.paste(resized, (dx, dy))
    return canvas, r, dx, dy


def make_session():
    if _HAVE_QNN:
        try:
            s = ort.InferenceSession(
                MODEL,
                providers=["QNNExecutionProvider", "CPUExecutionProvider"],
                provider_options=[{"backend_path": "QnnHtp.dll"}, {}],
            )
            return s
        except Exception as e:  # noqa: BLE001
            print("QNN session failed, falling back to CPU:", e)
    return ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])


def main(path: str):
    img = Image.open(path).convert("RGB")
    lb, r, dx, dy = letterbox(img)
    x = (np.asarray(lb, dtype=np.float32) / 255.0).transpose(2, 0, 1)[None]  # (1,3,640,640)

    sess = make_session()
    print("running on:", sess.get_providers())

    out = sess.run(None, {sess.get_inputs()[0].name: x})[0]  # (1,56,8400)
    preds = out[0].T                                          # (8400,56)
    preds = preds[preds[:, 4] > CONF]                         # conf filter
    print(f"detected {len(preds)} person(s) above conf {CONF}")

    for i, p in enumerate(preds[:5]):
        kpts = p[5:].reshape(17, 3)                           # 17 x (x,y,conf), 640-space
        for name, idx in (("L-ankle", 15), ("R-ankle", 16)):
            kx, ky, kc = kpts[idx]
            ox, oy = (kx - dx) / r, (ky - dy) / r             # back to original coords
            print(f"  person{i} {name}: ({ox:.0f},{oy:.0f}) conf={kc:.2f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "test.jpg")
