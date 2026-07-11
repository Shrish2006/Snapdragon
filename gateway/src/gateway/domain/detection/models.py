"""Models for ML service outputs the gateway consumes.

`PPEDetectionResult`/`PPEDetectionItem` mirror the *actual* current response
of `ai_ml/ppe_detection/app.py::detect()` and
`ai_ml/ppe_detection/ppe_detection.py::PPEDetector.detect()` field-for-field:

    {"detections": [{"class_name": str, "confidence": float,
                      "bbox": [x1, y1, x2, y2], "tracker_id": int | null}]}

Fall detection (`ai_ml/fall_detection/`) has no implemented output — only
`GET /health` exists, `fall_detection.py` is a `# TODO` stub — so it has no
contract to derive a typed model from. It is represented by the generic
`MLServiceResult` envelope, which mirrors how the *current* gateway already
ingests arbitrary ML payloads (`POST /events/{service}` accepting an
untyped `dict`). Do not add fall-specific fields until `fall_detection.py`
defines a real response schema; `MLServiceResult` is also the landing spot
for any future ML service before it earns its own typed model.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


class PPEDetectionItem(BaseModel):
    """One tracked detection, matching
    `PPEDetector.detect()`'s per-box dict exactly."""

    model_config = ConfigDict(frozen=True)

    class_name: str
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    bbox: tuple[float, float, float, float]
    """(x1, y1, x2, y2) pixel coordinates — matches
    `box.xyxy[0].tolist()` in `ppe_detection.py`."""
    tracker_id: int | None = None
    """BoT-SORT track id from `model.track(...)`; `None` when the tracker
    could not assign one (mirrors `int(box.id[0]) if box.id is not None
    else None` in `ppe_detection.py`)."""


class PPEDetectionResult(BaseModel):
    """Matches the JSON body of `POST /detect` on ppe-detection exactly:
    `{"detections": [...]}`."""

    model_config = ConfigDict(frozen=True)

    detections: list[PPEDetectionItem]


class MLServiceResult(BaseModel):
    """Generic envelope for any ML service without a typed contract yet.

    Mirrors the existing gateway's `POST /events/{service}` behavior, which
    already accepts an arbitrary `dict` payload — this gives that payload a
    name and a place in the type system instead of `dict[str, Any]`
    scattered through call sites.
    """

    model_config = ConfigDict(frozen=True)

    service: str
    payload: dict[str, Any]
