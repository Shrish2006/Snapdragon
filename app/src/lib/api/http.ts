// Low-level HTTP transport for the gateway REST API. Every service
// function in `lib/api/services/*` calls through here — this is the one
// place that knows how to build a request, parse a response, and surface
// a failure. No component and no service module should call `fetch`
// directly.

import { backendUrl } from "./config";

/** Thrown for any non-2xx gateway response. Carries enough to branch on
 * (404 vs 503 vs 422) without re-parsing the body. */
export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

interface RequestOptions {
  method?: "GET" | "POST";
  query?: Record<string, string | number | boolean | undefined>;
  body?: unknown;
  signal?: AbortSignal;
}

function buildQueryString(query: RequestOptions["query"]): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

/**
 * Issues one request against the gateway and returns the parsed JSON
 * body. Throws `ApiError` on any non-2xx response (after attempting to
 * parse a JSON error body, since the gateway's 422/503/502 error
 * payloads are structured — see `telemetry.py`'s `TelemetryRejectedResponse`
 * and `main.py`'s exception handlers).
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = `${backendUrl(path)}${buildQueryString(options.query)}`;
  const response = await fetch(url, {
    method: options.method ?? "GET",
    headers: options.body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
    cache: "no-store",
  });

  const contentType = response.headers.get("content-type") ?? "";
  const parsedBody = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    throw new ApiError(`gateway request failed: ${options.method ?? "GET"} ${path} -> ${response.status}`, response.status, parsedBody);
  }

  return parsedBody as T;
}
