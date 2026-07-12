"""Concrete `workers.pipeline.EventProcessor` implementations.

`persistence_processor.py` is the only one this phase ships. Threshold,
cross-sensor fusion, and risk-scoring processors (named in the approved
architecture) are deliberately not implemented — no such algorithm exists
anywhere in this codebase (`tests/test_sensor_fusion.py` is still exactly
the `# TODO` stub it was before this phase). This package is where they
plug in once one is designed: implement `EventProcessor`, register the
instance in `bootstrap.py`'s processor list.
"""
