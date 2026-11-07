"""Config flow for Midea Dehumidifier (Cloud)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
)

from .api import (
    MideaApiAuthError,
    MideaApiError,
    MideaDehumidifierClient,
    new_device_identity,
)
from .const import (
    APPS,
    CONF_ACCOUNT,
    CONF_APP,
    CONF_APPLIANCE_ID,
    CONF_CREDENTIALS,
    CONF_DEVICE_ID,
    CONF_PASSWORD,
    CONF_PUSH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_APP,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)


def build_user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build the account form schema."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_ACCOUNT, default=defaults.get(CONF_ACCOUNT, "")): TextSelector(
                TextSelectorConfig(type="email")
            ),
            vol.Required(CONF_PASSWORD): TextSelector(
                TextSelectorConfig(type="password")
            ),
            vol.Required(CONF_APP, default=defaults.get(CONF_APP, DEFAULT_APP)): SelectSelector(
                SelectSelectorConfig(options=APPS)
            ),
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): NumberSelector(
                NumberSelectorConfig(min=30, max=3600, step=1, mode=NumberSelectorMode.BOX)
            ),
        }
    )


async def async_log_in(
    hass, client: MideaDehumidifierClient, errors: dict[str, str]
) -> list[dict[str, Any]] | None:
    """Log in and list the dehumidifiers, or set errors and return None."""
    # The library hashes the password as ASCII and fails on anything else
    if client.password is not None and not client.password.isascii():
        errors["base"] = "password_not_ascii"
        return None
    try:
        return await hass.async_add_executor_job(client.list_dehumidifiers)
    except MideaApiAuthError:
        errors["base"] = "invalid_auth"
    except MideaApiError:
        errors["base"] = "cannot_connect"
    except Exception:  # noqa: BLE001
        errors["base"] = "unknown"
    return None


class MideaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Midea Dehumidifier (Cloud)."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._account: dict[str, Any] = {}
        self._appliances: list[dict[str, Any]] = []
        # One identity per flow, so retries don't use up more login slots
        self._device_id, self._push_token = new_device_identity()

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Ask for the Midea account and log in."""
        errors: dict[str, str] = {}

        if user_input is not None:
            account = str(user_input[CONF_ACCOUNT]).strip()
            client = MideaDehumidifierClient(
                account=account,
                app=user_input[CONF_APP],
                device_id=self._device_id,
                push_token=self._push_token,
                password=user_input[CONF_PASSWORD],
            )
            appliances = await async_log_in(self.hass, client, errors)
            if appliances is not None:
                configured = self._async_current_ids()
                self._appliances = [a for a in appliances if a["id"] not in configured]
                if not appliances:
                    errors["base"] = "no_dehumidifiers"
                elif not self._appliances:
                    return self.async_abort(reason="already_configured")
                else:
                    # Store the password hashes, not the password
                    self._account = {
                        CONF_ACCOUNT: account,
                        CONF_CREDENTIALS: client.credentials,
                        CONF_APP: user_input[CONF_APP],
                        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                        CONF_DEVICE_ID: self._device_id,
                        CONF_PUSH_TOKEN: self._push_token,
                    }
                    if len(self._appliances) == 1:
                        return await self._async_create(self._appliances[0])
                    return await self.async_step_appliance()

            user_input = {k: v for k, v in user_input.items() if k != CONF_PASSWORD}

        return self.async_show_form(
            step_id="user",
            data_schema=build_user_schema(user_input),
            errors=errors,
        )

    async def async_step_appliance(self, user_input: dict[str, Any] | None = None):
        """Ask which dehumidifier to add when the account has several."""
        if user_input is not None:
            appliance = next(
                a for a in self._appliances if a["id"] == user_input[CONF_APPLIANCE_ID]
            )
            return await self._async_create(appliance)

        schema = vol.Schema(
            {
                vol.Required(CONF_APPLIANCE_ID): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=a["id"], label=a["name"])
                            for a in self._appliances
                        ]
                    )
                ),
            }
        )
        return self.async_show_form(step_id="appliance", data_schema=schema)

    async def _async_create(self, appliance: dict[str, Any]):
        """Create the entry for one dehumidifier."""
        await self.async_set_unique_id(appliance["id"])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=appliance["name"],
            data={
                **self._account,
                CONF_APPLIANCE_ID: appliance["id"],
                "model": appliance["model"],
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get options flow."""
        return MideaOptionsFlowHandler(config_entry)


class MideaOptionsFlowHandler(config_entries.OptionsFlowWithReload):
    """Handle options flow."""

    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage the integration options; a new password replaces the hashes."""
        errors: dict[str, str] = {}
        entry = self._config_entry

        if user_input is not None:
            if password := user_input.get(CONF_PASSWORD):
                client = MideaDehumidifierClient(
                    account=entry.data[CONF_ACCOUNT],
                    app=entry.data[CONF_APP],
                    device_id=entry.data[CONF_DEVICE_ID],
                    push_token=entry.data[CONF_PUSH_TOKEN],
                    password=password,
                )
                if await async_log_in(self.hass, client, errors) is not None:
                    data = {k: v for k, v in entry.data.items() if k != CONF_PASSWORD}
                    self.hass.config_entries.async_update_entry(
                        entry, data={**data, CONF_CREDENTIALS: client.credentials}
                    )
            if not errors:
                return self.async_create_entry(
                    title="",
                    data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])},
                )

        scan_interval = entry.options.get(
            CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        schema = vol.Schema(
            {
                vol.Optional(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type="password")
                ),
                vol.Required(CONF_SCAN_INTERVAL, default=scan_interval): NumberSelector(
                    NumberSelectorConfig(min=30, max=3600, step=1, mode=NumberSelectorMode.BOX)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
