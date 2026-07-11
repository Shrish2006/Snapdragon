"""Tests for `gateway.infrastructure.registry.in_memory.InMemoryHelmetRepository`."""

from datetime import datetime, timezone

from gateway.domain.helmets.models import HelmetState, HelmetStatus
from gateway.infrastructure.registry.in_memory import InMemoryHelmetRepository

NOW = datetime(2026, 7, 12, tzinfo=timezone.utc)


def _state(helmet_id: str) -> HelmetState:
    return HelmetState(
        helmet_id=helmet_id,
        status=HelmetStatus.ONLINE,
        first_seen_at=NOW,
        last_seen_at=NOW,
        last_sequence=1,
    )


async def test_get_returns_none_for_unknown_helmet() -> None:
    repo = InMemoryHelmetRepository()
    assert await repo.get("HLM-0007") is None


async def test_upsert_then_get_round_trips() -> None:
    repo = InMemoryHelmetRepository()
    await repo.upsert(_state("HLM-0007"))
    result = await repo.get("HLM-0007")
    assert result is not None
    assert result.helmet_id == "HLM-0007"


async def test_upsert_overwrites_existing_entry() -> None:
    repo = InMemoryHelmetRepository()
    await repo.upsert(_state("HLM-0007"))
    updated = _state("HLM-0007").mark_offline()
    await repo.upsert(updated)
    result = await repo.get("HLM-0007")
    assert result is not None
    assert result.status is HelmetStatus.OFFLINE


async def test_list_all_returns_every_stored_helmet() -> None:
    repo = InMemoryHelmetRepository()
    await repo.upsert(_state("HLM-0001"))
    await repo.upsert(_state("HLM-0002"))
    ids = {state.helmet_id for state in await repo.list_all()}
    assert ids == {"HLM-0001", "HLM-0002"}
