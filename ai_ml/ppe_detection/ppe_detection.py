import logging
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import torch
from huggingface_hub import hf_hub_download
from ultralytics import YOLO

logger = logging.getLogger(__name__)

HF_REPO = "gauravp22/vyra-yolo-ppe-detection"
HF_FILE = "best.pt"

SUSTAIN_FRAMES = 10


class PPEDetector:
    def __init__(self, repo_id: str = HF_REPO, filename: str = HF_FILE):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.debug("Using device: %s", self.device)
        local_path = hf_hub_download(
            repo_id=repo_id, filename=filename, local_files_only=False
        )
        self.model = YOLO(local_path)
        self.model.to(self.device)
        self._streak: dict[tuple, int] = defaultdict(int)
        self._logged: set[tuple] = set()
        logger.debug("Model moved to %s", self.device)

    def detect(self, frame: np.ndarray) -> tuple[np.ndarray, list[dict]]:
        results = self.model.track(
            frame, persist=True, tracker="botsort.yaml", verbose=False
        )[0]

        detections: list[dict] = []
        active: set[tuple] = set()

        for box in results.boxes:
            class_name = results.names[int(box.cls[0])]
            tracker_id = int(box.id[0]) if box.id is not None else None
            detections.append(
                {
                    "class_name": class_name,
                    "confidence": float(box.conf[0]),
                    "bbox": box.xyxy[0].tolist(),
                    "tracker_id": tracker_id,
                }
            )

            if tracker_id is not None:
                active.add((tracker_id, class_name))

        for key in active:
            self._streak[key] += 1
            if self._streak[key] >= SUSTAIN_FRAMES and key not in self._logged:
                logger.warning(
                    "stable detection: tracker_id=%d class=%s", key[0], key[1]
                )
                self._logged.add(key)

        for key in set(self._streak) - active:
            del self._streak[key]
            self._logged.discard(key)

        logger.debug("detected %d objects", len(detections))
        return results.plot(), detections


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from config import setup_logging

    setup_logging()

    detector = PPEDetector(HF_REPO, HF_FILE)
    print(f"Running on: {detector.device}")
    cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)

    if not cap.isOpened():
        logger.error("Could not open webcam")
        sys.exit(1)

    logger.debug("Starting live inference loop")
    prev_time = time.time()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.error("Failed to grab frame")
                break

            annotated, detections = detector.detect(frame)

            now = time.time()
            fps = 1.0 / (now - prev_time)
            prev_time = now

            cv2.putText(
                annotated,
                f"FPS: {fps:.1f}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2,
            )
            cv2.imshow("SafeGuard — PPE Detection", annotated)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        logger.debug("Camera released, inference loop ended")
