"""Tests for `gateway.application.device_registry.DeviceRegistryService`."""

from datetime import datetime, timedelta, timezone

from gateway.application.device_registry import DeviceRegistryService
from gateway.domain.helmets.models import HelmetState, HelmetStatus
from gateway.infrastructure.registry.in_memory import InMemoryHelmetRepository

T0 = datetime(2026, 7, 12, 12, 0, 0, tzinfo=timezone.utc)


def _online_state(helmet_id: str, last_seen_at: datetime) -> HelmetState:
    return HelmetState(
        helmet_id=helmet_id,
        status=HelmetStatus.ONLINE,
        first_seen_at=T0,
        last_seen_at=last_seen_at,
        last_sequence=1,
    )


async def test_get_and_list_all_reflect_the_repository() -> None:
    repo = InMemoryHelmetRepository()
    registry = DeviceRegistryService(repo)
    await repo.upsert(_online_state("HLM-0007", T0))

    assert (await registry.get("HLM-0007")) is not None
    assert (await registry.get("HLM-9999")) is None
    assert len(await registry.list_all()) == 1


async def test_list_online_filters_out_offline_helmets() -> None:
    repo = InMemoryHelmetRepository()
    registry = DeviceRegistryService(repo)
    await repo.upsert(_online_state("HLM-0001", T0))
    await repo.upsert(_online_state("HLM-0002", T0).mark_offline())

    online = await registry.list_online()
    assert [state.helmet_id for state in online] == ["HLM-0001"]


async def test_sweep_offline_transitions_only_stale_online_helmets() -> None:
    repo = InMemoryHelmetRepository()
    registry = DeviceRegistryService(repo)
    now = T0 + timedelta(seconds=120)
    fresh = _online_state("HLM-FRESH", now - timedelta(seconds=5))
    stale = _online_state("HLM-STALE", T0)
    await repo.upsert(fresh)
    await repo.upsert(stale)

    changed = await registry.sweep_offline(
        now=now, staleness_threshold=timedelta(seconds=60)
    )

    assert [state.helmet_id for state in changed] == ["HLM-STALE"]
    assert (await repo.get("HLM-STALE")).status is HelmetStatus.OFFLINE
    assert (await repo.get("HLM-FRESH")).status is HelmetStatus.ONLINE


async def test_sweep_offline_is_idempotent() -> None:
    repo = InMemoryHelmetRepository()
    registry = DeviceRegistryService(repo)
    await repo.upsert(_online_state("HLM-STALE", T0))

    now = T0 + timedelta(seconds=120)
    first_pass = await registry.sweep_offline(
        now=now, staleness_threshold=timedelta(seconds=60)
    )
    second_pass = await registry.sweep_offline(
        now=now, staleness_threshold=timedelta(seconds=60)
    )

    assert len(first_pass) == 1
    assert second_pass == []  # already offline — not re-flagged as "changed"
