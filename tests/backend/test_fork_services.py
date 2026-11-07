"""Fork service boundary tests: headless zone preconditioning updates.

Upstream exposes the zone preconditioning update only through the panel's websocket
command, so a zone cannot be configured without the frontend. The fork adds the
`velair.update_zone_preconditioning` service as its headless counterpart.
"""

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from . import helpers as _helpers  # noqa: F401  # Install focused HA/voluptuous stubs.

from custom_components.velair.const import (
    DOMAIN,
    SERVICE_UPDATE_ZONE_PRECONDITIONING,
)
from custom_components.velair.services import async_setup_services


class _ServiceRegistry:
    def __init__(self) -> None:
        self.handlers: dict[tuple[str, str], tuple[object, object]] = {}
        self.removed: list[tuple[str, str]] = []

    def has_service(self, domain: str, service: str) -> bool:
        return (domain, service) in self.handlers

    def async_register(self, domain, service, handler, *, schema=None) -> None:
        self.handlers[(domain, service)] = (handler, schema)

    def async_remove(self, domain: str, service: str) -> None:
        self.removed.append((domain, service))


class ZonePreconditioningServiceTest(unittest.IsolatedAsyncioTestCase):
    """Verify the headless preconditioning service forwards the whole patch."""

    def setUp(self) -> None:
        self.scheduler = SimpleNamespace(
            async_update_zone_preconditioning=AsyncMock(),
            ensure_managed_entity=Mock(),
            set_temperature_migration_blocked=Mock(),
            temperature_migration_blocked=False,
        )
        self.services = _ServiceRegistry()
        self.hass = SimpleNamespace(
            services=self.services,
            data={
                DOMAIN: {
                    "entry": {
                        "scheduler": self.scheduler,
                        "storage": SimpleNamespace(
                            temperature_migration_required=False
                        ),
                        "operation_active": None,
                        "operation_recovery": None,
                    }
                }
            },
        )

    async def test_service_forwards_sensor_and_binary_output(self) -> None:
        await async_setup_services(self.hass)
        handler, schema = self.services.handlers[
            (DOMAIN, SERVICE_UPDATE_ZONE_PRECONDITIONING)
        ]
        preconditioning = {
            "room_temperature_entity_id": "sensor.salon_temperature",
            "room_sensor_assist_binary_output": True,
            "room_sensor_assist_deadband": 0.3,
        }

        await handler(
            SimpleNamespace(
                data=schema(
                    {
                        "entity_id": "climate.salon",
                        "preconditioning": preconditioning,
                    }
                )
            )
        )

        self.scheduler.ensure_managed_entity.assert_called_once_with("climate.salon")
        self.scheduler.async_update_zone_preconditioning.assert_awaited_once_with(
            "climate.salon", preconditioning
        )


if __name__ == "__main__":
    unittest.main()
