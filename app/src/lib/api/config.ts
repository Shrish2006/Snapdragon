// Centralized backend connection config. Every API/WS call in the app
// resolves its target through this module — nothing else reads
// `NEXT_PUBLIC_BACKEND_BASE_URL` directly.
//
// `NEXT_PUBLIC_BACKEND_BASE_URL` is already wired end-to-end outside this
// file: `docker-compose.yml` sets it on the `app` service, and
// `docker-entrypoint.sh` rewrites the baked-in build value inside the
// compiled `.js` output at container start. This module is what finally
// consumes it.

const DEFAULT_HTTP_BASE_URL = "http://localhost:8080";

/** Base HTTP(S) origin of the gateway, e.g. `http://localhost:8080`. */
export function getBackendHttpBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_BACKEND_BASE_URL || DEFAULT_HTTP_BASE_URL;
  return raw.endsWith("/") ? raw.slice(0, -1) : raw;
}

/**
 * Base WebSocket origin, derived from the HTTP base
 * (`http(s)://host` -> `ws(s)://host`) rather than a second env var —
 * one source of truth, one place that can drift.
 */
export function getBackendWsBaseUrl(): string {
  return getBackendHttpBaseUrl().replace(/^http/, "ws");
}

/** Builds a full gateway REST URL for a `/v1/...` (or root) path. */
export function backendUrl(path: string): string {
  return `${getBackendHttpBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
}

/** Full URL for the gateway's real-time event stream. */
export function backendWsUrl(path = "/v1/ws"): string {
  return `${getBackendWsBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
}

/**
 * Optional operator override for which helmet the dashboard displays by
 * default. Unset in normal operation — the app auto-selects the first
 * (preferably online) helmet from `GET /v1/helmets`. Exists only so a
 * single-helmet deployment can pin one without UI changes.
 */
export function getDefaultHelmetId(): string | undefined {
  return process.env.NEXT_PUBLIC_DEFAULT_HELMET_ID || undefined;
}
