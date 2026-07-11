"""Tests for `gateway.application.subscription_service`."""

import asyncio

from gateway.application.subscription_service import (
    DEFAULT_QUEUE_SIZE,
    EventFilter,
    SubscriptionManager,
)
from gateway.domain.detection.models import PPEDetectionResult
from gateway.domain.events.models import PPEDetectionEvent
from gateway.domain.events.types import EventType, Severity
from gateway.infrastructure.bus.in_memory import InMemoryEventBus


def _event(
    helmet_id: str | None = None,
    event_type: EventType = EventType.PPE_DETECTION,
    severity: Severity = Severity.INFO,
) -> PPEDetectionEvent:
    return PPEDetectionEvent(
        helmet_id=helmet_id,
        severity=severity,
        source="test",
        payload=PPEDetectionResult(detections=[]),
        type=event_type,
    )


# -- EventFilter --------------------------------------------------------


def test_empty_filter_matches_everything() -> None:
    assert EventFilter().matches(_event())
    assert EventFilter().matches(
        _event(helmet_id="HLM-0007", severity=Severity.CRITICAL)
    )


def test_filter_by_helmet_id() -> None:
    event_filter = EventFilter(helmet_id="HLM-0007")
    assert event_filter.matches(_event(helmet_id="HLM-0007"))
    assert not event_filter.matches(_event(helmet_id="HLM-0008"))
    assert not event_filter.matches(_event(helmet_id=None))


def test_filter_by_event_type() -> None:
    event_filter = EventFilter(event_types={EventType.ML_RESULT})
    assert not event_filter.matches(_event(event_type=EventType.PPE_DETECTION))


def test_filter_by_severity() -> None:
    event_filter = EventFilter(severities={Severity.CRITICAL})
    assert not event_filter.matches(_event(severity=Severity.INFO))
    assert event_filter.matches(_event(severity=Severity.CRITICAL))


# -- SubscriptionManager --------------------------------------------------


async def _run_briefly(manager: SubscriptionManager) -> asyncio.Task:
    task = asyncio.create_task(manager.run())
    await asyncio.sleep(0)  # let it subscribe before publishing
    return task


async def _stop(task: asyncio.Task) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_registered_subscriber_receives_a_matching_event() -> None:
    bus = InMemoryEventBus()
    manager = SubscriptionManager(bus)
    subscriber = await manager.register()
    task = await _run_briefly(manager)

    event = _event()
    await bus.publish(event)
    await asyncio.sleep(0.02)

    assert subscriber.queue.get_nowait() == event
    await _stop(task)


async def test_subscriber_does_not_receive_events_that_fail_its_filter() -> None:
    bus = InMemoryEventBus()
    manager = SubscriptionManager(bus)
    subscriber = await manager.register(EventFilter(helmet_id="HLM-0007"))
    task = await _run_briefly(manager)

    await bus.publish(_event(helmet_id="HLM-9999"))
    await asyncio.sleep(0.02)

    assert subscriber.queue.empty()
    await _stop(task)


async def test_update_filter_changes_what_a_live_subscriber_receives() -> None:
    bus = InMemoryEventBus()
    manager = SubscriptionManager(bus)
    subscriber = await manager.register(EventFilter(helmet_id="HLM-0007"))
    task = await _run_briefly(manager)

    await manager.update_filter(subscriber.id, EventFilter(helmet_id="HLM-9999"))
    await bus.publish(_event(helmet_id="HLM-0007"))
    await asyncio.sleep(0.02)
    assert subscriber.queue.empty()  # no longer matches after the update

    await bus.publish(_event(helmet_id="HLM-9999"))
    await asyncio.sleep(0.02)
    assert not subscriber.queue.empty()
    await _stop(task)


async def test_unregistered_subscriber_stops_receiving_events() -> None:
    bus = InMemoryEventBus()
    manager = SubscriptionManager(bus)
    subscriber = await manager.register()
    task = await _run_briefly(manager)

    await manager.unregister(subscriber.id)
    await bus.publish(_event())
    await asyncio.sleep(0.02)

    assert subscriber.queue.empty()
    await _stop(task)


async def test_two_subscribers_each_get_independent_copies() -> None:
    bus = InMemoryEventBus()
    manager = SubscriptionManager(bus)
    a = await manager.register()
    b = await manager.register()
    task = await _run_briefly(manager)

    event = _event()
    await bus.publish(event)
    await asyncio.sleep(0.02)

    assert a.queue.get_nowait() == event
    assert b.queue.get_nowait() == event
    await _stop(task)


async def test_full_queue_drops_non_critical_events_without_blocking() -> None:
    bus = InMemoryEventBus()
    manager = SubscriptionManager(bus)
    subscriber = await manager.register()
    task = await _run_briefly(manager)

    for _ in range(DEFAULT_QUEUE_SIZE + 5):
        await bus.publish(_event(severity=Severity.INFO))
    await asyncio.sleep(0.05)

    assert subscriber.queue.qsize() == DEFAULT_QUEUE_SIZE  # never exceeds the bound
    await _stop(task)


async def test_full_queue_never_drops_a_critical_event() -> None:
    bus = InMemoryEventBus()
    manager = SubscriptionManager(bus)
    subscriber = await manager.register()
    task = await _run_briefly(manager)

    for _ in range(DEFAULT_QUEUE_SIZE):
        await bus.publish(_event(severity=Severity.INFO))
    await asyncio.sleep(0.05)
    critical = _event(severity=Severity.CRITICAL)
    await bus.publish(critical)
    await asyncio.sleep(0.05)

    queued = []
    while not subscriber.queue.empty():
        queued.append(subscriber.queue.get_nowait())
    assert critical in queued
    await _stop(task)
