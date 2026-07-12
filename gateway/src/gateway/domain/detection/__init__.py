"""Detection bounded context: what ML services report.

`PPEDetectionResult` is typed and matches the real, current
`ai_ml/ppe_detection/app.py::detect()` response field-for-field.
`MLServiceResult` is a generic envelope for any ML service without a typed
contract yet — today that's fall-detection (`ai_ml/fall_detection/app.py`
exposes only `/health`; `fall_detection.py` is an unimplemented stub).
"""
