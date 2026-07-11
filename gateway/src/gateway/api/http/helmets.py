"""Read-only device state APIs — proves telemetry actually updates
per-helmet state end-to-end. Filterable/paginated dashboard endpoints and
event history live in a later phase (WebSocket + live dashboard APIs);
this is the minimal read surface Phase 2 needs to be verifiable over HTTP.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from gateway.api.http.deps import DeviceRegistryDep
from gateway.domain.common.identifiers import HelmetId
from gateway.domain.helmets.models import HelmetState

router = APIRouter(prefix="/v1/helmets", tags=["helmets"])


@router.get("", response_model=list[HelmetState], summary="List all known helmets.")
async def list_helmets(registry: DeviceRegistryDep) -> list[HelmetState]:
    return await registry.list_all()


@router.get(
    "/{helmet_id}",
    response_model=HelmetState,
    summary="Get one helmet's current real-time state.",
)
async def get_helmet(helmet_id: HelmetId, registry: DeviceRegistryDep) -> HelmetState:
    state = await registry.get(helmet_id)
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"unknown helmet: {helmet_id}")
    return state
