"""HTTP PPE detection ingestion.

Mirrors the old gateway's `POST /detect/ppe` proxy (forward an uploaded
frame to ppe-detection, emit the result as an event) with a typed response
and centralized upstream-error translation — see `main.py`'s exception
handlers for `MLServiceUnavailableError` (-> 503) and
`MLServiceResponseError` (-> 502), registered once instead of duplicated
per route.
"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from gateway.api.http.deps import PPEDetectionServiceDep
from gateway.application.detection_service import DetectPPERequest
from gateway.domain.detection.models import PPEDetectionResult

router = APIRouter(prefix="/v1/detections", tags=["detections"])


@router.post(
    "/ppe",
    response_model=PPEDetectionResult,
    summary="Run PPE detection on an uploaded frame.",
    description=(
        "Upload an image file (JPEG/PNG) to run YOLO-based PPE detection.\n\n"
        "Returns detected objects with their class labels, confidence scores, "
        "bounding boxes (x1, y1, x2, y2), and optional tracker IDs.\n\n"
        "**Upstream errors**:\n"
        "- **503** if the PPE detection service is unreachable.\n"
        "- **502** if the detection service returns an error response."
    ),
)
async def detect_ppe(
    service: PPEDetectionServiceDep, file: UploadFile = File(...)
) -> PPEDetectionResult:
    image = await file.read()
    request = DetectPPERequest(
        image=image,
        filename=file.filename or "frame.jpg",
        content_type=file.content_type or "image/jpeg",
    )
    return await service.detect(request)
