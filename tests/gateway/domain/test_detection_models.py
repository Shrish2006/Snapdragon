"""Tests for `gateway.domain.detection.models` — must accept the exact
wire shape `ai_ml/ppe_detection/app.py::detect()` returns today."""

from gateway.domain.detection.models import MLServiceResult, PPEDetectionResult

REAL_PPE_RESPONSE = {
    "detections": [
        {
            "class_name": "helmet",
            "confidence": 0.93,
            "bbox": [10.0, 20.0, 110.0, 220.0],
            "tracker_id": 3,
        },
        {
            "class_name": "no_vest",
            "confidence": 0.61,
            "bbox": [5.0, 5.0, 50.0, 50.0],
            "tracker_id": None,
        },
    ]
}


def test_ppe_detection_result_parses_the_real_service_response() -> None:
    result = PPEDetectionResult.model_validate(REAL_PPE_RESPONSE)
    assert len(result.detections) == 2
    assert result.detections[0].class_name == "helmet"
    assert result.detections[0].bbox == (10.0, 20.0, 110.0, 220.0)
    assert result.detections[1].tracker_id is None


def test_ml_service_result_wraps_arbitrary_payload_for_untyped_services() -> None:
    result = MLServiceResult(service="fall-detection", payload={"anything": "goes"})
    assert result.service == "fall-detection"
    assert result.payload == {"anything": "goes"}
