// Service layer for gateway/src/gateway/api/http/status.py.
// Aggregate gateway + upstream ML service health, for ops/connectivity
// indicators — polled, never streamed (see docs/notes on polling vs WS).

import { apiRequest } from "../http";
import type { GatewayStatusResponse } from "../types";

/** `GET /v1/status` — gateway + every upstream ML service's health. */
export function getGatewayStatus(signal?: AbortSignal): Promise<GatewayStatusResponse> {
  return apiRequest<GatewayStatusResponse>("/v1/status", { signal });
}
