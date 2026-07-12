"use client";

// Roster hook — backs helmet auto-selection. `GET /v1/helmets` is
// infrequently-changing once at least one helmet exists, so this is a
// plain fetch, not a WebSocket subscription (see the integration plan's
// real-time strategy: "cache for roster/history"). It does retry on a
// fixed interval while the roster is empty — the dashboard can load
// before any helmet has ever sent telemetry, and there is no event to
// push "a helmet just appeared" (presence is telemetry-derived, and the
// gateway only emits a WS snapshot once at connect time).

import { useEffect, useState } from "react";
import { listHelmets } from "@/lib/api";
import type { HelmetState } from "@/lib/api";

const EMPTY_ROSTER_RETRY_MS = 10_000;

export interface UseHelmetsResult {
  helmets: HelmetState[];
  loading: boolean;
  error: Error | null;
}

export function useHelmets(): UseHelmetsResult {
  const [helmets, setHelmets] = useState<HelmetState[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    let retryTimer: ReturnType<typeof setTimeout> | undefined;

    async function fetchRoster() {
      try {
        const result = await listHelmets(controller.signal);
        if (cancelled) return;
        setHelmets(result);
        setError(null);
        if (result.length === 0) {
          retryTimer = setTimeout(fetchRoster, EMPTY_ROSTER_RETRY_MS);
        }
      } catch (caught: unknown) {
        if (cancelled || controller.signal.aborted) return;
        setError(caught instanceof Error ? caught : new Error(String(caught)));
        retryTimer = setTimeout(fetchRoster, EMPTY_ROSTER_RETRY_MS);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchRoster();

    return () => {
      cancelled = true;
      controller.abort();
      clearTimeout(retryTimer);
    };
  }, []);

  return { helmets, loading, error };
}
