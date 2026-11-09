# SPDX-FileCopyrightText: 2026 Xavier Douville
# SPDX-License-Identifier: GPL-3.0-or-later

"""Data update coordinator for Midea Dehumidifier (Cloud)."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MideaApiAuthError, MideaApiError, MideaDehumidifierClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class MideaDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll the dehumidifier's state from the Midea cloud."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: MideaDehumidifierClient,
        scan_interval: int,
        name: str,
        model: str | None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self.appliance_name = name
        self.appliance_model = model

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the current state."""
        try:
            return await self.hass.async_add_executor_job(self.api.refresh)
        except MideaApiAuthError as err:
            # Stops polling and asks for the password, instead of retrying a
            # rejected login every poll, which could get the account locked
            raise ConfigEntryAuthFailed(f"Midea cloud rejected the login: {err}") from err
        except MideaApiError as err:
            raise UpdateFailed(f"Midea cloud error: {err}") from err

    async def async_set_state(self, **changes: Any) -> None:
        """Change the dehumidifier's state and publish the result."""
        try:
            data = await self.hass.async_add_executor_job(
                lambda: self.api.set_state(**changes)
            )
        except MideaApiError as err:
            raise HomeAssistantError(f"Couldn't change the dehumidifier: {err}") from err
        self.async_set_updated_data(data)
