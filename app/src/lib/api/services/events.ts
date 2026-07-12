// Service layer for gateway/src/gateway/api/http/events.py.
// Historical event queries — used to backfill trend data and event
// history before the live WebSocket stream takes over.

import { apiRequest } from "../http";
import type { DomainEvent, EventQueryParams } from "../types";

/** `GET /v1/events` — recent event history across all helmets. */
export function listEvents(
  params: EventQueryParams & { helmet_id?: string } = {},
  signal?: AbortSignal,
): Promise<DomainEvent[]> {
  return apiRequest<DomainEvent[]>("/v1/events", { query: params, signal });
}

/** `GET /v1/helmets/{helmet_id}/events` — one helmet's recent event history. */
export function listHelmetEvents(
  helmetId: string,
  params: EventQueryParams = {},
  signal?: AbortSignal,
): Promise<DomainEvent[]> {
  return apiRequest<DomainEvent[]>(`/v1/helmets/${encodeURIComponent(helmetId)}/events`, {
    query: params,
    signal,
  });
}
