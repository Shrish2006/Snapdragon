"""Tests for `gateway.infrastructure.bus.in_memory.InMemoryEventBus`."""

import asyncio

from gateway.domain.detection.models import PPEDetectionResult
from gateway.domain.events.models import PPEDetectionEvent
from gateway.infrastructure.bus.in_memory import InMemoryEventBus


def _event() -> PPEDetectionEvent:
    return PPEDetectionEvent(source="test", payload=PPEDetectionResult(detections=[]))


async def test_publish_with_no_subscribers_does_not_raise() -> None:
    bus = InMemoryEventBus()
    await bus.publish(_event())  # no assertion needed — must simply not error


async def test_subscriber_receives_a_published_event() -> None:
    bus = InMemoryEventBus()
    subscription = bus.subscribe("processing")
    event = _event()

    await bus.publish(event)
    received = await anext(aiter(subscription))

    assert received == event


async def test_independent_groups_each_receive_their_own_copy() -> None:
    bus = InMemoryEventBus()
    processing = bus.subscribe("processing")
    websocket = bus.subscribe("websocket")
    event = _event()

    await bus.publish(event)

    assert await anext(aiter(processing)) == event
    assert await anext(aiter(websocket)) == event


async def test_multiple_events_are_delivered_in_publish_order() -> None:
    bus = InMemoryEventBus()
    subscription = bus.subscribe("processing")
    first, second = _event(), _event()

    await bus.publish(first)
    await bus.publish(second)

    iterator = aiter(subscription)
    assert await anext(iterator) == first
    assert await anext(iterator) == second


async def test_close_unblocks_a_pending_iteration_immediately() -> None:
    bus = InMemoryEventBus()
    subscription = bus.subscribe("processing")

    async def _consume() -> list:
        return [event async for event in subscription]

    task = asyncio.create_task(_consume())
    await asyncio.sleep(0)  # let the task block on the empty queue
    await subscription.close()

    result = await asyncio.wait_for(task, timeout=1.0)
    assert result == []


async def test_events_published_after_close_are_not_delivered_to_that_subscriber() -> (
    None
):
    bus = InMemoryEventBus()
    subscription = bus.subscribe("processing")
    await subscription.close()

    await bus.publish(_event())  # must not raise, and must not queue up

    # a closed subscription's queue only ever contains the close sentinel
    remaining = [event async for event in subscription]
    assert remaining == []
