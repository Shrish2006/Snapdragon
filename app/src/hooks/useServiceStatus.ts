"use client";

// Ops/health polling hook for `GET /v1/status`. Aggregate gateway + ML
// service health changes slowly and isn't published as a domain event,
// so polling is the correct transport here (not WebSocket) — see the
// integration plan's real-time strategy.

import { useEffect, useState } from "react";
import { getGatewayStatus } from "@/lib/api";
import type { GatewayStatusResponse } from "@/lib/api";

const POLL_INTERVAL_MS = 20_000;

export interface UseServiceStatusResult {
  status: GatewayStatusResponse | null;
  error: Error | null;
}

export function useServiceStatus(pollIntervalMs: number = POLL_INTERVAL_MS): UseServiceStatusResult {
  const [status, setStatus] = useState<GatewayStatusResponse | null>(null);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    async function poll() {
      try {
        const result = await getGatewayStatus(controller.signal);
        if (!cancelled) {
          setStatus(result);
          setError(null);
        }
      } catch (caught: unknown) {
        if (!cancelled && !controller.signal.aborted) {
          setError(caught instanceof Error ? caught : new Error(String(caught)));
        }
      }
    }

    poll();
    const interval = setInterval(poll, pollIntervalMs);

    return () => {
      cancelled = true;
      controller.abort();
      clearInterval(interval);
    };
  }, [pollIntervalMs]);

  return { status, error };
}
