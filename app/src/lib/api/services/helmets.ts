// Service layer for gateway/src/gateway/api/http/helmets.py.
// Read-only helmet state: roster + per-helmet snapshot.

import { apiRequest, ApiError } from "../http";
import type { HelmetState } from "../types";

/** `GET /v1/helmets` — every helmet the gateway has ever seen. */
export function listHelmets(signal?: AbortSignal): Promise<HelmetState[]> {
  return apiRequest<HelmetState[]>("/v1/helmets", { signal });
}

/**
 * `GET /v1/helmets/{helmet_id}` — one helmet's current real-time state.
 * Resolves to `null` (not a thrown error) on a 404, since "helmet never
 * seen" is an expected, handleable case for callers — not just a fetch
 * failure.
 */
export async function getHelmet(helmetId: string, signal?: AbortSignal): Promise<HelmetState | null> {
  try {
    return await apiRequest<HelmetState>(`/v1/helmets/${encodeURIComponent(helmetId)}`, { signal });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
