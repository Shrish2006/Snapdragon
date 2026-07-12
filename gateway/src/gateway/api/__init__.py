"""Transport layer: HTTP routes (from Phase 2) and WebSocket routes (from
Phase 5). Thin controllers only — parse/validate input, call an
`application` use-case, serialize the result. No business logic lives here.
"""
