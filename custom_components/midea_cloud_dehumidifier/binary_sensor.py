# SPDX-FileCopyrightText: 2026 Xavier Douville
# SPDX-License-Identifier: GPL-3.0-or-later

"""Binary sensor platform for Midea Dehumidifier (Cloud)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import MideaCoordinatorEntity


@dataclass(frozen=True, kw_only=True)
class MideaBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a binary sensor read from the state."""

    value_fn: Callable[[dict[str, Any]], bool | None]
    # Only created when the appliance reports this capability
    capability: str | None = None


BINARY_SENSORS: tuple[MideaBinarySensorDescription, ...] = (
    MideaBinarySensorDescription(
        key="tank_full",
        translation_key="tank_full",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:cup-water",
        value_fn=lambda data: data.get("tank_full"),
    ),
    MideaBinarySensorDescription(
        key="filter_indicator",
        translation_key="filter_indicator",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:air-filter",
        capability="filter",
        value_fn=lambda data: data.get("filter_indicator"),
    ),
    MideaBinarySensorDescription(
        key="defrosting",
        translation_key="defrosting",
        icon="mdi:snowflake-melt",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("defrosting"),
    ),
    MideaBinarySensorDescription(
        key="error",
        translation_key="error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: bool(data.get("error_code")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up binary sensors for the capabilities the appliance reports."""
    coordinator = entry.runtime_data
    capabilities = coordinator.data.get("capabilities", {})
    async_add_entities(
        MideaBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
        if description.capability is None or capabilities.get(description.capability)
    )


class MideaBinarySensor(MideaCoordinatorEntity, BinarySensorEntity):
    """A flag read from the dehumidifier's state."""

    entity_description: MideaBinarySensorDescription

    def __init__(self, coordinator, description: MideaBinarySensorDescription) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return True if the flag is set."""
        return self.entity_description.value_fn(self.coordinator.data)
