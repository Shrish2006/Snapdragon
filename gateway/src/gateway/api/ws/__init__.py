"""WebSocket transport. Thin — parses/serializes `protocol.py` messages,
delegates all fan-out/filtering logic to `application.subscription_service`.
"""
