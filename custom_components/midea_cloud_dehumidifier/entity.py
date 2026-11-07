"""Base entity for Midea Dehumidifier (Cloud)."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MideaDataUpdateCoordinator


class MideaCoordinatorEntity(CoordinatorEntity[MideaDataUpdateCoordinator]):
    """Base coordinator entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MideaDataUpdateCoordinator, key: str) -> None:
        """Initialize the entity; key makes its unique ID."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.api.appliance_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.api.appliance_id)},
            name=self.coordinator.appliance_name,
            manufacturer="Midea",
            model="Dehumidifier",
            model_id=self.coordinator.appliance_model,
        )

    def supports(self, capability: str) -> bool:
        """Return True if the appliance reports this capability."""
        return bool(self.coordinator.data.get("capabilities", {}).get(capability))
