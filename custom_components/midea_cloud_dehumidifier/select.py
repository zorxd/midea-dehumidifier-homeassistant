# SPDX-FileCopyrightText: 2026 Xavier Douville
# SPDX-License-Identifier: GPL-3.0-or-later

"""Select platform for Midea Dehumidifier (Cloud)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import FAN_SPEEDS
from .entity import MideaCoordinatorEntity

FAN_SPEED_IDS = {name: speed for speed, name in FAN_SPEEDS.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the fan speed select."""
    coordinator = entry.runtime_data
    async_add_entities([MideaFanSpeedSelect(coordinator)])


class MideaFanSpeedSelect(MideaCoordinatorEntity, SelectEntity):
    """Fan speed: low, medium or high, or only low and high."""

    _attr_translation_key = "fan_speed"
    _attr_icon = "mdi:fan"

    def __init__(self, coordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "fan_speed")

    @property
    def options(self) -> list[str]:
        """Return the speeds this model offers.

        The fan speed capability looks like a bitmask of speeds: the Cube
        50-pint reports 3 (two bits) and has only low and high, setting
        medium gives low. Models that report three bits, or nothing, get all
        three speeds.
        """
        capability = self.coordinator.data.get("capabilities", {}).get("fan_speed")
        if capability is not None and bin(capability).count("1") == 2:
            return ["low", "high"]
        return list(FAN_SPEEDS.values())

    @property
    def current_option(self) -> str | None:
        """Return the fan speed, or None if it is not one of the presets."""
        return FAN_SPEEDS.get(self.coordinator.data.get("fan_speed"))

    async def async_select_option(self, option: str) -> None:
        """Set the fan speed."""
        await self.coordinator.async_set_state(fan_speed=FAN_SPEED_IDS[option])
