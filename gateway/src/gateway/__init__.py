"""SafeGuard Gateway — telemetry ingestion, ML event fan-in, and real-time
distribution for the helmet safety system.

Package layout (populated incrementally, see docs/deployment.md and the
approved gateway architecture):

- `domain/`         Pure business models and rules. No I/O, no framework
                     imports. (Phase 1)
- `application/`     Use-cases orchestrating domain + infrastructure ports.
                     (from Phase 2)
- `infrastructure/`  Adapters: event bus, storage, ML HTTP clients.
                     (from Phase 3)
- `api/`             Transport layer: HTTP routes, WebSocket routes.
                     (from Phase 2 / Phase 5)
- `workers/`         Standalone event-processing consumers.
                     (from Phase 4)
"""
