"""Domain layer: pure business models and rules.

Nothing in this package (or its subpackages) imports FastAPI, httpx, Redis,
or any other infrastructure/transport concern. Domain code is safe to unit
test without a running server, a database, or the network.

Subpackages:
- `common/`     Shared value objects and domain-level exceptions.
- `telemetry/`  What a helmet reports: sensor taxonomy, readings, batches,
                and business-rule (plausibility) validation.
- `detection/`  What ML services report: PPE detection (typed, matches the
                real ppe-detection API) and a generic envelope for services
                without a defined contract yet (fall-detection, future ML).
- `events/`     The internal event taxonomy and envelope used by the event
                bus (Phase 4) and WebSocket fan-out (Phase 5).
"""
