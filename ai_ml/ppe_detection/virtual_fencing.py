import logging

import cv2
import numpy as np
import torch
from ultralytics import YOLO

logger = logging.getLogger(__name__)

_GREEN = (0, 255, 0)
_RED = (0, 0, 255)

VISIBILITY_THRESHOLD = 0.3


class PoseDetector:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.debug("PoseDetector using device: %s", self.device)
        self.model = YOLO("yolov8n-pose.pt")
        self.model.to(self.device)
        self.debug = False  # when True: draw full skeleton via results.plot()

    def warmup(self):
        dummy = np.zeros((480, 640, 3), dtype=np.uint8)
        with torch.no_grad():
            self.model(dummy, verbose=False)

    def detect(
        self, frame: np.ndarray, roi_pts: np.ndarray | None
    ) -> tuple[np.ndarray, bool]:
        """Run pose inference on frame (which may already have PPE annotations drawn on it).
        Draws zone overlay and ankle dots in-place. Returns (annotated_frame, zone_triggered).
        """
        with torch.no_grad():
            results = self.model(frame, verbose=False)[0]

        zone_triggered = False
        # debug=True: results.plot() draws full skeleton (bones + keypoints) on the frame
        # debug=False: skip skeleton, draw only zone overlay and ankle dots
        annotated = results.plot() if self.debug else frame

        if roi_pts is not None:
            overlay = annotated.copy()
            cv2.fillPoly(overlay, [roi_pts], _GREEN)
            cv2.addWeighted(overlay, 0.16, annotated, 0.84, 0, annotated)
            cv2.polylines(annotated, [roi_pts], True, _GREEN, 2)

        if results.keypoints is None or len(results.keypoints) == 0:
            return annotated, False

        kps = results.keypoints.data.cpu().numpy()  # (N, 17, 3)

        for kp in kps:
            # COCO kp[15]=left_ankle, kp[16]=right_ankle; fall back to hip when invisible
            lc, rc = kp[15, 2], kp[16, 2]
            if lc > VISIBILITY_THRESHOLD or rc > VISIBILITY_THRESHOLD:
                fp = kp[15, :2] if lc >= rc else kp[16, :2]
            else:
                lhc, rhc = kp[11, 2], kp[12, 2]
                fp = kp[11, :2] if lhc >= rhc else kp[12, :2]

            if fp[0] == 0 and fp[1] == 0:
                continue

            inside = False
            if roi_pts is not None:
                dist = cv2.pointPolygonTest(
                    roi_pts, (float(fp[0]), float(fp[1])), measureDist=False
                )
                inside = dist >= 0

            if inside and not zone_triggered:
                zone_triggered = True
                logger.warning("zone_triggered: ankle in restricted area")
                overlay2 = annotated.copy()
                cv2.fillPoly(overlay2, [roi_pts], _RED)
                cv2.addWeighted(overlay2, 0.16, annotated, 0.84, 0, annotated)
                cv2.polylines(annotated, [roi_pts], True, _RED, 2)

            foot = (int(fp[0]), int(fp[1]))
            cv2.circle(annotated, foot, 6, _RED if inside else _GREEN, -1)

        return annotated, zone_triggered
