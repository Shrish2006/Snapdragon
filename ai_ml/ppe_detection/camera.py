"""Webcam capture via pygrabber (DirectShow) — OpenCV-free, ARM64-safe.

pygrabber uses comtypes (ctypes), so it runs on Windows ARM64 where opencv can't.
Enumerates by index like cv2, and hands back RGB uint8 frames.

IMPORTANT: all pygrabber/COM calls must stay on ONE thread. Construct and use a
Camera entirely inside the inference worker thread.
"""

import logging
import threading

import numpy as np
from pygrabber.dshow_graph import FilterGraph

logger = logging.getLogger(__name__)


def list_cameras() -> list[str]:
    """Return camera device names indexed by position (index 0, 1, ...)."""
    return FilterGraph().get_input_devices()


class Camera:
    def __init__(self, index: int = 0, swap_rb: bool = False):
        self.index = index
        self.swap_rb = swap_rb  # DirectShow often returns BGR; swap to RGB for YOLO
        self._latest: np.ndarray | None = None
        self._lock = threading.Lock()
        self._graph = None
        self.open()

    def _on_frame(self, frame: np.ndarray) -> None:
        with self._lock:
            self._latest = frame  # RGB uint8 HxWx3

    def open(self) -> None:
        try:
            g = FilterGraph()
            g.add_video_input_device(self.index)
            g.add_sample_grabber(self._on_frame)
            g.add_null_render()
            g.prepare_preview_graph()
            g.run()
            self._graph = g
            logger.info("camera %d opened", self.index)
        except Exception:  # noqa: BLE001
            logger.exception("camera %d open failed", self.index)
            self._graph = None

    def read(self) -> np.ndarray | None:
        """Trigger a grab; return the most recent RGB frame (or None)."""
        if self._graph is None:
            return None
        try:
            self._graph.grab_frame()
        except Exception:  # noqa: BLE001
            logger.exception("grab failed")
            return None
        with self._lock:
            if self._latest is None:
                return None
            return (
                self._latest[:, :, ::-1].copy() if self.swap_rb else self._latest.copy()
            )

    def reopen(self) -> None:
        self.close()
        self.open()

    def close(self) -> None:
        if self._graph is not None:
            try:
                self._graph.stop()
            except Exception:  # noqa: BLE001
                pass
            self._graph = None
