"use client";

// Real-time data provider for one helmet. Owns exactly one
// `GatewayEventSocket` connection (never one per card) and exposes
// derived state via `useHelmetLive()`. Scoped as a React Context local
// to the dashboard subtree — not an app-wide store — so it's created and
// torn down with the dashboard, per the "keep state localized, avoid
// unnecessary global state" constraint.
//
// Data flow per the integration plan:
//   1. REST snapshot  (`GET /v1/helmets/{id}`)        -> initial paint
//   2. REST backfill  (`GET /v1/helmets/{id}/events`) -> trend history
//   3. WS live stream (`GET /v1/ws`, filtered)         -> everything after
//
// State reset on helmet change is handled by remounting via `key`
// (`HelmetLiveSession key={helmetId}`) rather than resetting state
// inside an effect — the React-recommended pattern for "fully reset
// state when an id prop changes" (https://react.dev/learn/you-might-not-need-an-effect).

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getHelmet, listHelmetEvents } from "@/lib/api";
import type { DomainEvent, HelmetState, MLServiceResult, TelemetryBatch } from "@/lib/api";
import { GatewayEventSocket, type ConnectionState } from "@/lib/ws/socket";
import { applyBatchToHelmetState, environmentPointFromBatch, firstContactHelmetState, reconcileWithRestPoll } from "@/lib/sensors/telemetry";
import type { EnvironmentPoint } from "@/lib/sensors/normalize";

const ENVIRONMENT_HISTORY_LIMIT = 20;
const ALERTS_HISTORY_LIMIT = 20;
const ALERTS_BACKFILL_TYPES = ["telemetry.validation_failed", "ml.ppe_detection", "ml.result"] as const;
const OFFLINE_RESYNC_INTERVAL_MS = 30_000;

export interface MlFallSignal {
  service: string;
  payload: Record<string, unknown>;
  occurredAt: string;
}

interface HelmetLiveContextValue {
  helmetId: string | null;
  helmet: HelmetState | null;
  connection: ConnectionState;
  environmentHistory: EnvironmentPoint[];
  lastMlFallSignal: MlFallSignal | null;
  alerts: DomainEvent[];
}

const EMPTY_CONTEXT_VALUE: HelmetLiveContextValue = {
  helmetId: null,
  helmet: null,
  connection: "closed",
  environmentHistory: [],
  lastMlFallSignal: null,
  alerts: [],
};

const HelmetLiveContext = createContext<HelmetLiveContextValue | null>(null);

/** Public entry point. Renders no live connection while `helmetId` is
 * `null` (e.g. roster still loading); once set, mounts a fresh
 * `HelmetLiveSession` keyed by that id. */
export function HelmetLiveProvider({ helmetId, children }: { helmetId: string | null; children: ReactNode }) {
  if (!helmetId) {
    return <HelmetLiveContext.Provider value={EMPTY_CONTEXT_VALUE}>{children}</HelmetLiveContext.Provider>;
  }
  return (
    <HelmetLiveSession key={helmetId} helmetId={helmetId}>
      {children}
    </HelmetLiveSession>
  );
}

/** Owns the REST snapshot/backfill + one WS connection for exactly one
 * helmet id, for this component instance's whole lifetime. Remounted
 * (fresh state, no leftover data from the previous helmet) whenever the
 * parent's `key={helmetId}` changes. */
function HelmetLiveSession({ helmetId, children }: { helmetId: string; children: ReactNode }) {
  const [helmet, setHelmet] = useState<HelmetState | null>(null);
  const [connection, setConnection] = useState<ConnectionState>("closed");
  const [environmentHistory, setEnvironmentHistory] = useState<EnvironmentPoint[]>([]);
  const [lastMlFallSignal, setLastMlFallSignal] = useState<MlFallSignal | null>(null);
  const [alerts, setAlerts] = useState<DomainEvent[]>([]);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    getHelmet(helmetId, controller.signal)
      .then((state) => {
        // Guard against a race with the WS snapshot/live stream: the
        // socket below can receive a `snapshot` or `telemetry.received`
        // event before this REST call resolves, in which case this
        // response must not clobber the fresher state — merge via the
        // same recency rule `reconcileWithRestPoll` uses for periodic
        // resync, and never null out already-known state on a
        // transient 404.
        if (cancelled || !state) return;
        setHelmet((current) => (current ? reconcileWithRestPoll(current, state) : state));
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) console.error("HelmetLiveProvider: initial snapshot fetch failed", error);
        // Non-fatal: the WS snapshot/live stream can still populate state.
      });

    listHelmetEvents(helmetId, { event_type: "telemetry.received", limit: ENVIRONMENT_HISTORY_LIMIT }, controller.signal)
      .then((events) => {
        if (cancelled) return;
        const points = events
          .slice()
          .reverse() // event history is newest-first; trend lines read left-to-right
          .map((event) => environmentPointFromBatch(event.payload as TelemetryBatch));
        setEnvironmentHistory(points);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) console.error("HelmetLiveProvider: event-history backfill failed", error);
        // Non-fatal: live WS events still accumulate a trend going forward.
      });

    // Alerts backfill: one targeted query per interesting event type
    // rather than one unfiltered query, since `telemetry.received`
    // fires on every batch and would otherwise crowd the most recent
    // `limit` results out of the far rarer alert-worthy event types.
    Promise.all(
      ALERTS_BACKFILL_TYPES.map((eventType) =>
        listHelmetEvents(helmetId, { event_type: eventType, limit: ALERTS_HISTORY_LIMIT }, controller.signal),
      ),
    )
      .then((results) => {
        if (cancelled) return;
        const merged = results
          .flat()
          .sort((a, b) => new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime())
          .slice(0, ALERTS_HISTORY_LIMIT);
        setAlerts(merged);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) console.error("HelmetLiveProvider: alerts backfill failed", error);
        // Non-fatal: live WS events still accumulate alerts going forward.
      });

    // Periodic REST re-sync — the only current way to observe an
    // offline transition (see `reconcileWithRestPoll`'s docstring).
    const resyncInterval = setInterval(() => {
      getHelmet(helmetId, controller.signal)
        .then((restState) => {
          if (cancelled || !restState) return;
          setHelmet((current) => reconcileWithRestPoll(current, restState));
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted) console.error("HelmetLiveProvider: periodic resync failed", error);
        });
    }, OFFLINE_RESYNC_INTERVAL_MS);

    const socket = new GatewayEventSocket();

    const offMessage = socket.onMessage((message) => {
      if (message.type === "snapshot") {
        const match = message.helmets.find((entry) => entry.helmet_id === helmetId);
        if (match) setHelmet(match);
        return;
      }

      if (message.type === "error") {
        console.error("HelmetLiveProvider: gateway rejected a WS message", message.detail);
        return;
      }
      if (message.type !== "event") return; // heartbeat — nothing to do
      const event = message.event as DomainEvent;
      if (event.helmet_id !== helmetId) return;

      if (event.type === "telemetry.received") {
        const batch = event.payload as TelemetryBatch;
        setHelmet((current) => (current ? applyBatchToHelmetState(current, batch) : firstContactHelmetState(batch)));
        setEnvironmentHistory((current) => [...current, environmentPointFromBatch(batch)].slice(-ENVIRONMENT_HISTORY_LIMIT));
        return;
      }

      // Every other event type is alert-worthy — prepend to the rolling
      // buffer (newest first, matching the backfill's sort order).
      setAlerts((current) => [event, ...current].slice(0, ALERTS_HISTORY_LIMIT));

      if (event.type === "ml.result") {
        const result = event.payload as MLServiceResult;
        setLastMlFallSignal({ service: result.service, payload: result.payload, occurredAt: event.occurred_at });
      }
    });

    const offState = socket.onStateChange(setConnection);

    socket.connect();
    // No `event_types` filter: `EventFilter.event_types: null` means "no
    // restriction" (see `application/subscription_service.py`'s
    // docstring) — this is deliberate, not an oversight. It means the
    // alerts feed picks up `helmet.online`/`helmet.offline` the day the
    // gateway starts publishing them, with zero frontend changes.
    socket.subscribe({ helmet_id: helmetId });

    return () => {
      cancelled = true;
      controller.abort();
      clearInterval(resyncInterval);
      offMessage();
      offState();
      socket.close();
    };
  }, [helmetId]);

  const value = useMemo<HelmetLiveContextValue>(
    () => ({ helmetId, helmet, connection, environmentHistory, lastMlFallSignal, alerts }),
    [helmetId, helmet, connection, environmentHistory, lastMlFallSignal, alerts],
  );

  return <HelmetLiveContext.Provider value={value}>{children}</HelmetLiveContext.Provider>;
}

/** Consumes the nearest `HelmetLiveProvider`. Throws outside one — a
 * missing provider is a wiring bug, not a recoverable state. */
export function useHelmetLive(): HelmetLiveContextValue {
  const context = useContext(HelmetLiveContext);
  if (!context) throw new Error("useHelmetLive must be used within a HelmetLiveProvider");
  return context;
}
