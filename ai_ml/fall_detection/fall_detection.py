"""Stateless fall-detection inference: normalise → ONNX forward pass → sigmoid.

The gateway (FallDetectionProcessor) owns the circular buffer and debounce
state. This module is a pure function: receive a 200-sample window that the
gateway already assembled, return a fall probability. No per-helmet memory here.

Column order expected from caller: [accel_x_g, accel_y_g, accel_z_g,
                                    gyro_x_dps, gyro_y_dps, gyro_z_dps]
Units: g and deg/s — same SI units the StandardScaler was fit on.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import onnxruntime as ort

_MODEL_DIR = Path(os.getenv("MODEL_DIR", "/app/fall_detection/models"))
MODEL_PATH = _MODEL_DIR / "fall_detection.onnx"
SCALER_PATH = _MODEL_DIR / "scaler.npz"

WINDOW = 200  # must match train.py


class FallInference:
    """Loads the ONNX model + scaler once at startup; predict() is stateless."""

    def __init__(
        self,
        model_path: Path = MODEL_PATH,
        scaler_path: Path = SCALER_PATH,
    ) -> None:
        self._sess = ort.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
        d = np.load(str(scaler_path))
        self._mean: np.ndarray = d["mean"].astype(np.float32)  # (6,)
        self._std: np.ndarray = d["std"].astype(np.float32)  # (6,)

    def predict(self, window: list[list[float]]) -> float:
        """window: WINDOW × 6 list → fall probability in [0, 1]."""
        arr = np.array(window, dtype=np.float32)  # (200, 6)
        normed = (arr - self._mean) / self._std  # apply training scaler
        x = normed.T[np.newaxis].astype(np.float32)  # (1, 6, 200) — Conv1d format
        logit = float(np.ravel(self._sess.run(None, {"imu": x})[0])[0])
        return float(1.0 / (1.0 + np.exp(-logit)))  # sigmoid
