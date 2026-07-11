import logging
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)

MODEL_PATH = "hf://gauravp22/vyra-yolo-ppe-detection/best.pt"


class PPEDetector:
    def __init__(self, model_path: str = MODEL_PATH):
        logger.debug("Loading model: %s", model_path)
        self.model = YOLO(model_path)
        logger.debug("Model loaded successfully")

    def detect(self, frame: np.ndarray) -> tuple[np.ndarray, list[dict]]:
        results = self.model(frame, verbose=False)[0]
        detections = [
            {
                "class_name": results.names[int(box.cls[0])],
                "confidence": float(box.conf[0]),
                "bbox": box.xyxy[0].tolist(),
            }
            for box in results.boxes
        ]
        logger.debug("Detected %d objects", len(detections))
        return results.plot(), detections


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from config import setup_logging
    setup_logging()

    detector = PPEDetector()
    cap = cv2.VideoCapture(0)

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

            cv2.putText(annotated, f"FPS: {fps:.1f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.imshow("SafeGuard — PPE Detection", annotated)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        logger.debug("Camera released, inference loop ended")
