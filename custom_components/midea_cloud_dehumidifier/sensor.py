# SPDX-FileCopyrightText: 2026 Xavier Douville
# SPDX-License-Identifier: GPL-3.0-or-later

"""Sensor platform for Midea Dehumidifier (Cloud)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import MideaCoordinatorEntity


@dataclass(frozen=True, kw_only=True)
class MideaSensorDescription(SensorEntityDescription):
    """Describes a sensor read from the state."""

    value_fn: Callable[[dict[str, Any]], Any]
    # Only created when the appliance reports this capability
    capability: str | None = None


SENSORS: tuple[MideaSensorDescription, ...] = (
    MideaSensorDescription(
        key="current_humidity",
        translation_key="current_humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: data.get("current_humidity"),
    ),
    MideaSensorDescription(
        key="current_temperature",
        translation_key="current_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        # The Cube reports whole degrees; the value keeps any decimals it sends
        suggested_display_precision=0,
        value_fn=lambda data: data.get("current_temperature"),
    ),
    MideaSensorDescription(
        key="tank_level",
        translation_key="tank_level",
        icon="mdi:cup-water",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        capability="water_level",
        value_fn=lambda data: data.get("tank_level"),
    ),
    MideaSensorDescription(
        key="error_code",
        translation_key="error_code",
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("error_code"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensors for the capabilities the appliance reports."""
    coordinator = entry.runtime_data
    capabilities = coordinator.data.get("capabilities", {})
    async_add_entities(
        MideaSensor(coordinator, description)
        for description in SENSORS
        if description.capability is None or capabilities.get(description.capability)
    )


class MideaSensor(MideaCoordinatorEntity, SensorEntity):
    """A value read from the dehumidifier's state."""

    entity_description: MideaSensorDescription

    def __init__(self, coordinator, description: MideaSensorDescription) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
