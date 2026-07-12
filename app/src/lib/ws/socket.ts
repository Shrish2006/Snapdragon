// Real-time transport for gateway/src/gateway/api/ws/stream.py
// (`GET /v1/ws`). One `GatewayEventSocket` instance owns one physical
// WebSocket connection and fans parsed server messages out to listeners
// via a small pub/sub — callers never touch `WebSocket` directly, and
// never open a second connection for a second card.
//
// Reconnect: exponential backoff (1s -> 2s -> 4s ... capped at 30s),
// restarting from 1s after any successful connection. On reconnect the
// last `subscribe` filter is resent automatically, so a client's scope
// survives a drop without the caller re-issuing it.

import { backendWsUrl } from "../api/config";
import type { EventFilter, ServerMessage, SubscribeMessage } from "../api/types";

export type ConnectionState = "connecting" | "open" | "reconnecting" | "closed";

type MessageListener = (message: ServerMessage) => void;
type StateListener = (state: ConnectionState) => void;

const INITIAL_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30_000;

export class GatewayEventSocket {
  private socket: WebSocket | null = null;
  private state: ConnectionState = "closed";
  private backoffMs = INITIAL_BACKOFF_MS;
  private reconnectTimer: ReturnType<typeof setTimeout> | undefined = undefined;
  private currentFilter: EventFilter = {};
  private closedByCaller = false;

  private readonly messageListeners = new Set<MessageListener>();
  private readonly stateListeners = new Set<StateListener>();

  connect(): void {
    this.closedByCaller = false;
    this.open();
  }

  close(): void {
    this.closedByCaller = true;
    clearTimeout(this.reconnectTimer);
    this.socket?.close();
    this.socket = null;
    this.setState("closed");
  }

  /** (Re)scopes the stream. Resent automatically after every reconnect. */
  subscribe(filter: EventFilter): void {
    this.currentFilter = filter;
    this.sendSubscribe();
  }

  onMessage(listener: MessageListener): () => void {
    this.messageListeners.add(listener);
    return () => this.messageListeners.delete(listener);
  }

  onStateChange(listener: StateListener): () => void {
    this.stateListeners.add(listener);
    return () => this.stateListeners.delete(listener);
  }

  getState(): ConnectionState {
    return this.state;
  }

  private open(): void {
    this.setState(this.socket === null && this.backoffMs === INITIAL_BACKOFF_MS ? "connecting" : "reconnecting");

    const socket = new WebSocket(backendWsUrl());
    this.socket = socket;

    socket.addEventListener("open", () => {
      this.backoffMs = INITIAL_BACKOFF_MS;
      this.setState("open");
      this.sendSubscribe();
    });

    socket.addEventListener("message", (event) => {
      this.dispatchMessage(event.data);
    });

    socket.addEventListener("close", () => {
      if (this.closedByCaller) return;
      this.scheduleReconnect();
    });

    socket.addEventListener("error", () => {
      // The browser follows this with a `close` event — reconnect logic
      // lives there so a connection is never retried twice for one drop.
      socket.close();
    });
  }

  private scheduleReconnect(): void {
    this.setState("reconnecting");
    this.reconnectTimer = setTimeout(() => {
      this.backoffMs = Math.min(this.backoffMs * 2, MAX_BACKOFF_MS);
      this.open();
    }, this.backoffMs);
  }

  private sendSubscribe(): void {
    if (this.socket?.readyState !== WebSocket.OPEN) return;
    const message: SubscribeMessage = { action: "subscribe", filter: this.currentFilter };
    this.socket.send(JSON.stringify(message));
  }

  private dispatchMessage(raw: string): void {
    let parsed: ServerMessage;
    try {
      parsed = JSON.parse(raw) as ServerMessage;
    } catch {
      return; // malformed frame — drop, do not crash the stream
    }
    for (const listener of this.messageListeners) listener(parsed);
  }

  private setState(state: ConnectionState): void {
    this.state = state;
    for (const listener of this.stateListeners) listener(state);
  }
}
