# SPDX-FileCopyrightText: 2026 Xavier Douville
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Midea Dehumidifier (Cloud) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import MideaDehumidifierClient
from .const import (
    CONF_ACCOUNT,
    CONF_APP,
    CONF_APPLIANCE_ID,
    CONF_CREDENTIALS,
    CONF_DEVICE_ID,
    CONF_PUSH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    PLATFORMS,
)
from .coordinator import MideaDataUpdateCoordinator

type MideaConfigEntry = ConfigEntry[MideaDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: MideaConfigEntry) -> bool:
    """Set up a dehumidifier from a config entry."""
    api = MideaDehumidifierClient(
        account=entry.data[CONF_ACCOUNT],
        app=entry.data[CONF_APP],
        device_id=entry.data[CONF_DEVICE_ID],
        push_token=entry.data[CONF_PUSH_TOKEN],
        credentials=entry.data[CONF_CREDENTIALS],
        appliance_id=entry.data[CONF_APPLIANCE_ID],
    )

    coordinator = MideaDataUpdateCoordinator(
        hass=hass,
        api=api,
        scan_interval=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        name=entry.title,
        model=entry.data.get("model"),
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MideaConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
