"""Webcam capture — V4L2 on Linux (via OpenCV), DirectShow on Windows.

Platform detection is automatic:
  - Linux  → OpenCV VideoCapture (V4L2); no COM, no pygrabber needed.
  - Windows → pygrabber (DirectShow) via comtypes; OpenCV-free, ARM64-safe.

IMPORTANT (Windows only): all pygrabber/COM calls must stay on ONE thread.
Construct and use a Camera entirely inside the inference worker thread.
"""

import logging
import platform
import threading

import numpy as np

logger = logging.getLogger(__name__)

_IS_LINUX = platform.system() == "Linux"


def list_cameras() -> list[str]:
    """Return camera device names indexed by position (index 0, 1, ...)."""
    if _IS_LINUX:
        import cv2

        names: list[str] = []
        for i in range(8):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                names.append(f"/dev/video{i}")
                cap.release()
        return names
    from pygrabber.dshow_graph import FilterGraph

    return FilterGraph().get_input_devices()


class Camera:
    def __init__(self, index: int = 0, swap_rb: bool = False):
        self.index = index
        # swap_rb is only relevant for Windows/DirectShow which returns BGR.
        # OpenCV already returns BGR natively — we flip to RGB for YOLO ourselves.
        self.swap_rb = swap_rb
        self._lock = threading.Lock()
        self._latest: np.ndarray | None = None
        self._graph = None   # Windows only
        self._cap = None     # Linux only
        self.open()

    # ── Linux / OpenCV ────────────────────────────────────────────────────

    def _open_linux(self) -> None:
        import cv2

        cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            logger.error("cv2: camera %d could not be opened", self.index)
            return
        # Request a reasonable default resolution; camera may clamp it.
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self._cap = cap
        logger.info("cv2: camera %d opened (%dx%d)", self.index,
                    int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))

    def _read_linux(self) -> np.ndarray | None:
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return None
        # OpenCV gives BGR; convert to RGB for the ONNX pipeline.
        return frame[:, :, ::-1].copy()

    def _close_linux(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    # ── Windows / pygrabber ───────────────────────────────────────────────

    def _on_frame(self, frame: np.ndarray) -> None:
        with self._lock:
            self._latest = frame  # RGB uint8 HxWx3

    def _open_windows(self) -> None:
        try:
            from pygrabber.dshow_graph import FilterGraph

            g = FilterGraph()
            g.add_video_input_device(self.index)
            g.add_sample_grabber(self._on_frame)
            g.add_null_render()
            g.prepare_preview_graph()
            g.run()
            self._graph = g
            logger.info("dshow: camera %d opened", self.index)
        except Exception:  # noqa: BLE001
            logger.exception("dshow: camera %d open failed", self.index)
            self._graph = None

    def _read_windows(self) -> np.ndarray | None:
        if self._graph is None:
            return None
        try:
            self._graph.grab_frame()
        except Exception:  # noqa: BLE001
            logger.exception("dshow: grab failed")
            return None
        with self._lock:
            if self._latest is None:
                return None
            return (
                self._latest[:, :, ::-1].copy()
                if self.swap_rb
                else self._latest.copy()
            )

    def _close_windows(self) -> None:
        if self._graph is not None:
            try:
                self._graph.stop()
            except Exception:  # noqa: BLE001
                pass
            self._graph = None

    # ── Public interface ──────────────────────────────────────────────────

    def open(self) -> None:
        if _IS_LINUX:
            self._open_linux()
        else:
            self._open_windows()

    def read(self) -> np.ndarray | None:
        """Return the most recent RGB frame, or None if unavailable."""
        if _IS_LINUX:
            return self._read_linux()
        return self._read_windows()

    def reopen(self) -> None:
        self.close()
        self.open()

    def close(self) -> None:
        if _IS_LINUX:
            self._close_linux()
        else:
            self._close_windows()
