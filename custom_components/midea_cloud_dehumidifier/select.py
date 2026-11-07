"""Select platform for Midea Dehumidifier (Cloud)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, FAN_SPEEDS
from .entity import MideaCoordinatorEntity

FAN_SPEED_IDS = {name: speed for speed, name in FAN_SPEEDS.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the fan speed select."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([MideaFanSpeedSelect(coordinator)])


class MideaFanSpeedSelect(MideaCoordinatorEntity, SelectEntity):
    """Fan speed: low, medium or high."""

    _attr_translation_key = "fan_speed"
    _attr_icon = "mdi:fan"
    _attr_options = list(FAN_SPEEDS.values())

    def __init__(self, coordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "fan_speed")

    @property
    def current_option(self) -> str | None:
        """Return the fan speed, or None if it is not one of the three presets."""
        return FAN_SPEEDS.get(self.coordinator.data.get("fan_speed"))

    async def async_select_option(self, option: str) -> None:
        """Set the fan speed."""
        await self.coordinator.async_set_state(fan_speed=FAN_SPEED_IDS[option])
