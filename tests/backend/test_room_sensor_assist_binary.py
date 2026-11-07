"""Binary room sensor assist output: valves receive only the physical minimum or maximum.

Fork-specific tests (see patches/0001-binary-output.patch). Upstream Velair delivers
`scheduled target + signed correction`; this fork delivers `max` when the room asks for
heat and `min` when it does not, reusing the hysteresis phase upstream already computes.
The flag is per zone and defaults to False, so upstream behaviour is the default.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from .helpers import (
    FakeClimateManager,
    FakeHass,
    MODE_AUTO,
    VelairScheduler,
    empty_week_schedule,
    normalize_panel_settings,
    normalize_preconditioning_data,
)


class _BinaryFixture:
    """Minimal zone scaffolding for one managed climate with an external sensor."""

    def setUp(self) -> None:
        self.entity_id = "climate.salon"
        self.hass = FakeHass()
        self.hass.states[self.entity_id] = SimpleNamespace(
            state="heat", attributes={"current_temperature": 20}
        )
        self.climate = FakeClimateManager()
        self.data = {
            "version": 1,
            "global_": {
                "mode": MODE_AUTO,
                "paused_until": None,
                "paused_started_at": None,
            },
            "zones": {
                self.entity_id: {
                    "enabled": True,
                    "schedule": empty_week_schedule(),
                    "override": None,
                    "preconditioning": {
                        "enabled": True,
                        "max_lead_minutes": 180,
                        "minimum_delta_temperature": 0.3,
                        "fallback_minutes_per_degree": 20,
                    },
                }
            },
            "settings": normalize_panel_settings(None, [self.entity_id]),
            "templates": [],
            "templates_seeded": True,
        }

        async def _async_save() -> None:
            return None

        self.scheduler = VelairScheduler(
            self.hass,
            self.data,
            self.climate,
            _async_save,
        )

    def _target(
        self,
        *,
        phase,
        target: float = 19.5,
        room: float = 19.0,
        climate: float = 20.0,
        max_delta: float = 10.0,
        binary: bool = True,
    ):
        config = normalize_preconditioning_data(
            {
                "room_sensor_assist_deadband": 0.15,
                "room_sensor_assist_max_delta": max_delta,
                "room_sensor_assist_binary_output": binary,
            }
        )
        return self.scheduler._room_sensor_assist_target(
            self.entity_id,
            config,
            "heat",
            target,
            room,
            climate,
            hysteresis_phase=phase,
            hysteresis_target=target,
        )


class RoomSensorAssistBinaryOutputTest(_BinaryFixture, unittest.TestCase):
    """Verify that the scalar assist output is binary and ignores the numeric caps."""

    def test_towards_upper_requests_the_physical_maximum(self) -> None:
        result = self._target(phase="towards_upper")

        self.assertEqual(result.requested_temperature, 35.0)
        self.assertEqual(result.applied_temperature, 35.0)
        self.assertEqual(result.hysteresis_phase, "towards_upper")

    def test_towards_lower_requests_the_physical_minimum(self) -> None:
        result = self._target(phase="towards_lower", room=20.4)

        self.assertEqual(result.requested_temperature, 5.0)
        self.assertEqual(result.applied_temperature, 5.0)

    def test_max_delta_does_not_cap_the_binary_output(self) -> None:
        result = self._target(phase="towards_upper", max_delta=2.0)

        self.assertEqual(result.requested_temperature, 35.0)

    def test_cold_room_without_phase_falls_back_to_heating(self) -> None:
        result = self._target(phase=None, room=18.9)

        self.assertEqual(result.requested_temperature, 35.0)

    def test_binary_output_bypasses_the_scheduled_target_guard(self) -> None:
        result = self._target(phase="towards_upper")

        self.assertIsNone(result.scheduled_target_guard)
        self.assertIsNone(result.limited_by)
        self.assertIsNone(result.limit_temperature)

    def test_disabled_zone_keeps_upstream_correction(self) -> None:
        result = self._target(phase="towards_upper", binary=False)

        self.assertEqual(result.requested_temperature, 20.5)


class RoomSensorAssistBinaryPersistenceTest(unittest.TestCase):
    """Verify the flag is stored with a safe default and survives normalisation."""

    def test_flag_defaults_to_false(self) -> None:
        self.assertFalse(
            normalize_preconditioning_data({})["room_sensor_assist_binary_output"]
        )

    def test_flag_round_trips(self) -> None:
        normalized = normalize_preconditioning_data(
            {"room_sensor_assist_binary_output": True}
        )

        self.assertTrue(normalized["room_sensor_assist_binary_output"])


if __name__ == "__main__":
    unittest.main()
