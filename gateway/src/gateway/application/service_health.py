"""Aggregates health across every integrated ML service.

Mirrors the old gateway's `GET /status` behavior
(`{"gateway": "ok", "services": {name: "ok"|"degraded"|"unreachable"}}`),
now backed by typed `MLServiceClient` ports instead of ad-hoc `httpx` calls
inline in a route handler.

Takes a `dict[str, MLServiceClient]` rather than named parameters
specifically so a future third ML service is one more entry in
`bootstrap.py`'s dict — this class never changes.
"""

from __future__ import annotations

import asyncio

from gateway.application.ports import MLServiceClient, ServiceHealth


class ServiceHealthService:
    def __init__(self, clients: dict[str, MLServiceClient]) -> None:
        self._clients = clients

    async def check_all(self) -> dict[str, ServiceHealth]:
        names = list(self._clients)
        results = await asyncio.gather(
            *(self._clients[name].health() for name in names)
        )
        return dict(zip(names, results, strict=True))
