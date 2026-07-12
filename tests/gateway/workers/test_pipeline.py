"""Tests for `gateway.workers.pipeline.ProcessingPipeline`."""

import asyncio
from typing import Any

from gateway.domain.detection.models import PPEDetectionResult
from gateway.domain.events.models import DomainEvent, PPEDetectionEvent
from gateway.infrastructure.bus.in_memory import InMemoryEventBus
from gateway.workers.pipeline import ProcessingPipeline


def _event() -> PPEDetectionEvent:
    return PPEDetectionEvent(source="test", payload=PPEDetectionResult(detections=[]))


class _RecordingProcessor:
    def __init__(self) -> None:
        self.processed: list[DomainEvent[Any]] = []

    async def process(self, event: DomainEvent[Any]) -> None:
        self.processed.append(event)


class _FailingProcessor:
    async def process(self, event: DomainEvent[Any]) -> None:
        raise RuntimeError("boom")


async def _run_briefly(pipeline: ProcessingPipeline) -> None:
    task = asyncio.create_task(pipeline.run())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_pipeline_dispatches_published_events_to_every_processor() -> None:
    bus = InMemoryEventBus()
    processor_a, processor_b = _RecordingProcessor(), _RecordingProcessor()
    pipeline = ProcessingPipeline(bus, [processor_a, processor_b])

    task = asyncio.create_task(pipeline.run())
    await asyncio.sleep(0)  # let the pipeline subscribe before we publish
    event = _event()
    await bus.publish(event)
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert processor_a.processed == [event]
    assert processor_b.processed == [event]


async def test_one_failing_processor_does_not_block_the_others() -> None:
    bus = InMemoryEventBus()
    good_processor = _RecordingProcessor()
    pipeline = ProcessingPipeline(bus, [_FailingProcessor(), good_processor])

    task = asyncio.create_task(pipeline.run())
    await asyncio.sleep(0)
    event = _event()
    await bus.publish(event)
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert good_processor.processed == [event]


async def test_pipeline_stops_cleanly_on_task_cancellation() -> None:
    bus = InMemoryEventBus()
    pipeline = ProcessingPipeline(bus, [])

    await _run_briefly(pipeline)  # must not raise or hang
