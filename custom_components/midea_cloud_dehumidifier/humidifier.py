# SPDX-FileCopyrightText: 2026 Xavier Douville
# SPDX-License-Identifier: GPL-3.0-or-later

"""Humidifier platform for Midea Dehumidifier (Cloud)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.humidifier import (
    HumidifierDeviceClass,
    HumidifierEntity,
    HumidifierEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, HUMIDITY_STEP, MAX_HUMIDITY, MIN_HUMIDITY, MODE_SET, MODES
from .entity import MideaCoordinatorEntity

MODE_IDS = {name: mode for mode, name in MODES.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the dehumidifier entity."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([MideaDehumidifier(coordinator)])


class MideaDehumidifier(MideaCoordinatorEntity, HumidifierEntity):
    """The dehumidifier: power, target humidity and mode."""

    _attr_name = None
    _attr_translation_key = "dehumidifier"
    _attr_device_class = HumidifierDeviceClass.DEHUMIDIFIER
    _attr_supported_features = HumidifierEntityFeature.MODES
    _attr_min_humidity = MIN_HUMIDITY
    _attr_max_humidity = MAX_HUMIDITY
    _attr_target_humidity_step = HUMIDITY_STEP

    def __init__(self, coordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "dehumidifier")

    @property
    def available_modes(self) -> list[str]:
        """Return the modes this model offers."""
        return [
            name
            for name in MODES.values()
            if name != "dry_clothes" or self.supports("dry_clothes")
        ]

    @property
    def is_on(self) -> bool:
        """Return True if the dehumidifier is running."""
        return bool(self.coordinator.data.get("running"))

    @property
    def mode(self) -> str | None:
        """Return the operating mode."""
        return MODES.get(self.coordinator.data.get("mode"))

    @property
    def target_humidity(self) -> int | None:
        """Return the target humidity."""
        return self.coordinator.data.get("target_humidity")

    @property
    def current_humidity(self) -> int | None:
        """Return the measured humidity."""
        return self.coordinator.data.get("current_humidity")

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the dehumidifier on."""
        await self.coordinator.async_set_state(running=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the dehumidifier off."""
        await self.coordinator.async_set_state(running=False)

    async def async_set_humidity(self, humidity: int) -> None:
        """Set the target humidity; it only applies in Set mode.

        Rounded to the 5 % steps the Midea app offers, since automations can
        ask for any value.
        """
        humidity = round(humidity / HUMIDITY_STEP) * HUMIDITY_STEP
        humidity = min(max(humidity, MIN_HUMIDITY), MAX_HUMIDITY)
        changes: dict[str, Any] = {"target_humidity": humidity}
        if self.coordinator.data.get("mode") != MODE_SET:
            changes["mode"] = MODE_SET
        await self.coordinator.async_set_state(**changes)

    async def async_set_mode(self, mode: str) -> None:
        """Set the operating mode."""
        await self.coordinator.async_set_state(mode=MODE_IDS[mode])
