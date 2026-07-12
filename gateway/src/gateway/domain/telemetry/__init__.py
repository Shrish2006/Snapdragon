"""Telemetry bounded context: what a helmet reports.

Grounded in `helmet/*.ino`. `sensors.py` holds the taxonomy and the
extensibility registry; `models.py` holds the reading/batch value objects;
`validation.py` holds business-rule (plausibility) checks distinct from
Pydantic's structural validation.
"""
