"""The Midea Dehumidifier (Cloud) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import MideaDehumidifierClient
from .const import (
    CONF_ACCOUNT,
    CONF_APP,
    CONF_APPLIANCE_ID,
    CONF_DEVICE_ID,
    CONF_PASSWORD,
    CONF_PUSH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import MideaDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a dehumidifier from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    api = MideaDehumidifierClient(
        account=entry.data[CONF_ACCOUNT],
        password=entry.options.get(CONF_PASSWORD, entry.data[CONF_PASSWORD]),
        app=entry.data[CONF_APP],
        device_id=entry.data[CONF_DEVICE_ID],
        push_token=entry.data[CONF_PUSH_TOKEN],
        appliance_id=entry.data[CONF_APPLIANCE_ID],
    )

    coordinator = MideaDataUpdateCoordinator(
        hass=hass,
        api=api,
        scan_interval=entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        ),
        name=entry.title,
        model=entry.data.get("model"),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
