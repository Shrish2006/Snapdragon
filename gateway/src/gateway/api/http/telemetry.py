"""HTTP telemetry ingestion — the Phase 2 concrete transport for
`IngestionService`.

HTTP, not MQTT: the approved architecture names MQTT as the eventual
transport for hundreds of intermittently-connected helmets, but no broker,
client library, or firmware networking code exists anywhere in this repo
today (`helmet_firmware.ino` is a stub) — there is nothing to build an MQTT
adapter against yet. HTTP is what every other service in this codebase
already speaks. `IngestionService` itself is transport-agnostic (see its
docstring); an MQTT subscriber becomes a second caller of the same
use-case later, not a rewrite of it.
"""

from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from gateway.api.http.deps import IngestionServiceDep
from gateway.domain.telemetry.models import TelemetryBatch
from gateway.domain.telemetry.validation import ValidationIssue

router = APIRouter(prefix="/v1/telemetry", tags=["telemetry"])


class TelemetryAcceptedResponse(BaseModel):
    accepted: bool = True
    helmet_id: str
    sequence: int
    status: str


class TelemetryRejectedResponse(BaseModel):
    accepted: bool = False
    issues: list[ValidationIssue]


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TelemetryAcceptedResponse,
    responses={422: {"model": TelemetryRejectedResponse}},
    summary="Ingest one telemetry batch from a helmet.",
)
async def ingest_telemetry(
    batch: TelemetryBatch, service: IngestionServiceDep
) -> TelemetryAcceptedResponse | JSONResponse:
    result = await service.ingest(batch)
    if not result.accepted:
        rejected = TelemetryRejectedResponse(issues=list(result.issues))
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=rejected.model_dump(mode="json"),
        )
    assert result.state is not None  # accepted implies a state was produced
    return TelemetryAcceptedResponse(
        helmet_id=result.state.helmet_id,
        sequence=result.state.last_sequence,
        status=result.state.status.value,
    )
