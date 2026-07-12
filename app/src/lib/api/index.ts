// Centralized API layer entry point. Components and hooks import from
// `@/lib/api`, never from `lib/api/http`, a specific service module, or
// `fetch` directly — this barrel is the one contract surface.

export { ApiError } from "./http";
export { backendUrl, backendWsUrl, getDefaultHelmetId } from "./config";
export { listHelmets, getHelmet } from "./services/helmets";
export { listEvents, listHelmetEvents } from "./services/events";
export { getGatewayStatus } from "./services/status";
export type * from "./types";
