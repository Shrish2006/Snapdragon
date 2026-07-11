"""Tests for `gateway.infrastructure.bus.redis_streams.RedisStreamsEventBus`.

Uses `fakeredis.aioredis.FakeRedis` — no real Redis server is contacted;
`fakeredis` implements the actual Streams commands (XADD/XGROUP/XREADGROUP/
XACK) this adapter issues, so this genuinely exercises the adapter's logic.
"""

import fakeredis.aioredis
import pytest

from gateway.domain.detection.models import PPEDetectionResult
from gateway.domain.events.models import PPEDetectionEvent
from gateway.infrastructure.bus.redis_streams import RedisStreamsEventBus


@pytest.fixture
def redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis()


def _event() -> PPEDetectionEvent:
    return PPEDetectionEvent(source="test", payload=PPEDetectionResult(detections=[]))


async def test_subscriber_receives_a_published_event(redis) -> None:
    bus = RedisStreamsEventBus(redis)
    subscription = bus.subscribe("processing")
    event = _event()

    await bus.publish(event)
    received = await anext(aiter(subscription))

    assert received == event


async def test_independent_groups_each_receive_their_own_copy(redis) -> None:
    """Redis consumer-group semantics: two distinct groups each get a full
    copy of the stream — this is fan-out, not competing consumers."""
    bus = RedisStreamsEventBus(redis)
    processing = bus.subscribe("processing")
    websocket = bus.subscribe("websocket")
    event = _event()

    await bus.publish(event)

    assert await anext(aiter(processing)) == event
    assert await anext(aiter(websocket)) == event


async def test_a_message_is_not_redelivered_after_being_acked(redis) -> None:
    bus = RedisStreamsEventBus(redis)
    subscription = bus.subscribe("processing")
    await bus.publish(_event())
    await anext(aiter(subscription))  # reads and acks the one message

    pending = await redis.xpending("gateway:events", "processing")
    assert pending["pending"] == 0


async def test_a_new_group_created_after_a_publish_still_sees_that_message(redis) -> None:
    """`xgroup_create(..., id="0")` backfills history — a subscriber that
    starts after events were already published must not miss them."""
    bus = RedisStreamsEventBus(redis)
    event = _event()
    await bus.publish(event)

    late_subscription = bus.subscribe("late-processing")
    received = await anext(aiter(late_subscription))

    assert received == event
