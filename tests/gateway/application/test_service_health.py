"""Tests for `gateway.application.service_health.ServiceHealthService`."""

from gateway.application.ports import ServiceHealth
from gateway.application.service_health import ServiceHealthService


class _FakeClient:
    def __init__(self, health: ServiceHealth) -> None:
        self._health = health

    async def health(self) -> ServiceHealth:
        return self._health


async def test_check_all_reports_each_service_by_name() -> None:
    service = ServiceHealthService(
        {
            "ppe-detection": _FakeClient(ServiceHealth.OK),
            "fall-detection": _FakeClient(ServiceHealth.UNREACHABLE),
        }
    )
    result = await service.check_all()
    assert result == {
        "ppe-detection": ServiceHealth.OK,
        "fall-detection": ServiceHealth.UNREACHABLE,
    }


async def test_check_all_handles_an_empty_client_map() -> None:
    service = ServiceHealthService({})
    assert await service.check_all() == {}
