"""Events bounded context: the internal taxonomy and envelope used by the
event bus (Phase 4) and WebSocket fan-out (Phase 5).

This is new architecture being implemented per the approved gateway design
— `types.py` and `models.py` do not claim any of this already exists in the
current codebase (the current gateway has exactly two ad-hoc event shapes;
see each module's docstring for how this taxonomy is grounded in that
reality plus the proven telemetry/detection contracts).
"""
