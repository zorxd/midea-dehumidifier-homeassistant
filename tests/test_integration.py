# SPDX-FileCopyrightText: 2026 Xavier Douville
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for Midea Dehumidifier (Cloud), with the Midea cloud replaced by fakes."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.midea_cloud_dehumidifier.api import (
    MideaApiAuthError,
    MideaDehumidifierClient,
    _MideaCloud,
    password_credentials,
)
from custom_components.midea_cloud_dehumidifier.const import DOMAIN

CLIENT = "custom_components.midea_cloud_dehumidifier.api.MideaDehumidifierClient"

# State the Cube 50-pint reported through the cloud
STATE = {
    "running": True,
    "mode": 1,
    "target_humidity": 50,
    "current_humidity": 52,
    "current_temperature": 14.0,
    "fan_speed": 40,
    "tank_full": False,
    "tank_level": 0,
    "defrosting": False,
    "filter_indicator": False,
    "error_code": 0,
    "capabilities": {"fan_speed": 3, "filter": 2, "dry_clothes": 1, "water_level": 4},
}

CREDENTIALS = {
    "password_sha256": "sha",
    "password_md5_md5": "md5md5",
}

ONE_APPLIANCE = [{"id": "1506", "name": "Déshumidificateur", "model": "41377"}]


def fake_login(appliances):
    """Fake list_dehumidifiers that logs in like the real one: hashes replace the password."""

    def list_dehumidifiers(self):
        self.credentials = CREDENTIALS
        self.password = None
        return appliances

    return list_dehumidifiers


USER_INPUT = {
    "account": "ha@example.com",
    "password": "secret",
    "app": "MSmartHome",
    "scan_interval": 60,
}


async def test_config_flow_creates_entry(hass: HomeAssistant) -> None:
    """One dehumidifier on the account is added directly."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    with patch(f"{CLIENT}.list_dehumidifiers", fake_login(ONE_APPLIANCE)), patch(
        f"{CLIENT}.refresh", return_value=dict(STATE)
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Déshumidificateur"
    data = result["data"]
    assert data["appliance_id"] == "1506"
    assert data["model"] == "41377"
    # Own device identity instead of the library's shared one
    assert len(data["device_id"]) == 16
    assert data["device_id"] != "c1acad8939ac0d7d"
    assert data["push_token"]
    # Only the password hashes are stored
    assert "password" not in data
    assert data["credentials"] == CREDENTIALS


async def test_config_flow_invalid_auth(hass: HomeAssistant) -> None:
    """A rejected login shows an error on the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(f"{CLIENT}.list_dehumidifiers", side_effect=MideaApiAuthError("no")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_config_flow_chooses_among_several(hass: HomeAssistant) -> None:
    """Several dehumidifiers on the account: the user picks one."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    appliances = [
        {"id": "1", "name": "Basement", "model": "a"},
        {"id": "2", "name": "Garage", "model": "b"},
    ]
    with patch(f"{CLIENT}.list_dehumidifiers", fake_login(appliances)), patch(
        f"{CLIENT}.refresh", return_value=dict(STATE)
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "appliance"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"appliance_id": "2"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Garage"


async def _setup(hass: HomeAssistant, **login) -> MockConfigEntry:
    login = login or {"credentials": CREDENTIALS}
    account = {k: v for k, v in USER_INPUT.items() if k != "password"}
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Déshumidificateur",
        unique_id="1506",
        data={
            **account,
            **login,
            "appliance_id": "1506",
            "model": "41377",
            "device_id": "0123456789abcdef",
            "push_token": "token",
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_entities_show_state(hass: HomeAssistant) -> None:
    """Entities reflect the state read from the cloud."""
    with patch(f"{CLIENT}.refresh", return_value=dict(STATE)):
        await _setup(hass)

    dehumidifier = hass.states.get("humidifier.deshumidificateur")
    assert dehumidifier.state == "on"
    assert dehumidifier.attributes["humidity"] == 50
    assert dehumidifier.attributes["current_humidity"] == 52
    assert dehumidifier.attributes["mode"] == "set"
    # The Cube doesn't report "auto", so it has no Smart mode
    assert dehumidifier.attributes["available_modes"] == [
        "set",
        "continuous",
        "dry_clothes",
    ]
    assert hass.states.get("select.deshumidificateur_fan_speed").state == "low"
    assert hass.states.get("sensor.deshumidificateur_humidity").state == "52"
    assert hass.states.get("sensor.deshumidificateur_temperature").state == "14.0"
    # Shown without decimals
    temperature = er.async_get(hass).async_get("sensor.deshumidificateur_temperature")
    assert temperature.options["sensor"]["suggested_display_precision"] == 0
    assert hass.states.get("sensor.deshumidificateur_water_level").state == "0"
    assert hass.states.get("binary_sensor.deshumidificateur_tank_full").state == "off"
    assert (
        hass.states.get("binary_sensor.deshumidificateur_filter_needs_cleaning").state
        == "off"
    )


async def test_controls_send_changes(hass: HomeAssistant) -> None:
    """Services send the matching state changes to the cloud."""
    with patch(f"{CLIENT}.refresh", return_value=dict(STATE)):
        await _setup(hass)

    calls = []

    def fake_set_state(self, **changes):
        calls.append(changes)
        return {**STATE, **changes}

    with patch(f"{CLIENT}.set_state", fake_set_state):
        await hass.services.async_call(
            "humidifier",
            "set_humidity",
            {"entity_id": "humidifier.deshumidificateur", "humidity": 45},
            blocking=True,
        )
        await hass.services.async_call(
            "humidifier",
            "set_mode",
            {"entity_id": "humidifier.deshumidificateur", "mode": "continuous"},
            blocking=True,
        )
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": "select.deshumidificateur_fan_speed", "option": "high"},
            blocking=True,
        )
        await hass.services.async_call(
            "humidifier",
            "turn_off",
            {"entity_id": "humidifier.deshumidificateur"},
            blocking=True,
        )

    assert calls == [
        {"target_humidity": 45},
        {"mode": 2},
        {"fan_speed": 80},
        {"running": False},
    ]
    assert hass.states.get("humidifier.deshumidificateur").state == "off"


async def test_set_humidity_switches_to_set_mode(hass: HomeAssistant) -> None:
    """A target humidity only applies in Set mode, so it switches to it."""
    with patch(f"{CLIENT}.refresh", return_value={**STATE, "mode": 2}):
        await _setup(hass)

    calls = []
    with patch(
        f"{CLIENT}.set_state",
        lambda self, **changes: calls.append(changes) or {**STATE, **changes},
    ):
        await hass.services.async_call(
            "humidifier",
            "set_humidity",
            {"entity_id": "humidifier.deshumidificateur", "humidity": 55},
            blocking=True,
        )
    assert calls == [{"target_humidity": 55, "mode": 1}]


async def test_config_flow_rejects_non_ascii_password(hass: HomeAssistant) -> None:
    """The library can't hash non-ASCII passwords, so the form says so."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, "password": "mot de passe é"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "password_not_ascii"}


async def test_stored_password_is_replaced_by_hashes(hass: HomeAssistant) -> None:
    """Entries from 0.1.0 stored the password; setup swaps it for its hashes."""

    def refresh(self):
        assert self.password == "old-secret"
        self.credentials = CREDENTIALS
        self.password = None
        return dict(STATE)

    with patch(f"{CLIENT}.refresh", refresh):
        entry = await _setup(hass, password="old-secret")

    assert "password" not in entry.data
    assert entry.data["credentials"] == CREDENTIALS
    assert hass.states.get("humidifier.deshumidificateur").state == "on"


async def test_logs_in_with_stored_hashes(hass: HomeAssistant) -> None:
    """An entry with hashes logs in with them, without a password."""
    seen = {}

    def refresh(self):
        seen.update(password=self.password, credentials=self.credentials)
        return dict(STATE)

    with patch(f"{CLIENT}.refresh", refresh):
        await _setup(hass)

    assert seen == {"password": None, "credentials": CREDENTIALS}


async def test_options_new_password_replaces_hashes(hass: HomeAssistant) -> None:
    """A new password under Configure is checked, then only its hashes are kept."""
    with patch(f"{CLIENT}.refresh", return_value=dict(STATE)):
        entry = await _setup(hass)

    new_credentials = {**CREDENTIALS, "password_sha256": "newsha"}

    def list_dehumidifiers(self):
        assert self.password == "new-secret"
        self.credentials = new_credentials
        self.password = None
        return ONE_APPLIANCE

    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch(f"{CLIENT}.list_dehumidifiers", list_dehumidifiers), patch(
        f"{CLIENT}.refresh", return_value=dict(STATE)
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"password": "new-secret", "scan_interval": 120}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"scan_interval": 120}
    assert entry.data["credentials"] == new_credentials
    assert "password" not in entry.data


async def test_options_new_password_reloads_with_same_interval(
    hass: HomeAssistant,
) -> None:
    """A new password takes effect even when the scan interval is unchanged."""
    with patch(f"{CLIENT}.refresh", return_value=dict(STATE)):
        entry = await _setup(hass)
    hass.config_entries.async_update_entry(entry, options={"scan_interval": 60})
    await hass.async_block_till_done()

    seen = []

    def refresh(self):
        seen.append(self.credentials)
        return dict(STATE)

    def list_dehumidifiers(self):
        self.credentials = {**CREDENTIALS, "password_sha256": "newsha"}
        self.password = None
        return ONE_APPLIANCE

    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch(f"{CLIENT}.list_dehumidifiers", list_dehumidifiers), patch(
        f"{CLIENT}.refresh", refresh
    ):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {"password": "new-secret", "scan_interval": 60}
        )
        await hass.async_block_till_done()

    # Reloaded and logged in with the new hashes
    assert seen and seen[-1]["password_sha256"] == "newsha"


async def test_options_wrong_password_keeps_hashes(hass: HomeAssistant) -> None:
    """A rejected new password changes nothing."""
    with patch(f"{CLIENT}.refresh", return_value=dict(STATE)):
        entry = await _setup(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch(f"{CLIENT}.list_dehumidifiers", side_effect=MideaApiAuthError("no")):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"password": "wrong", "scan_interval": 60}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data["credentials"] == CREDENTIALS


def test_credentials_match_library_hashes() -> None:
    """Stored hashes give the library's login hashes for any login ID.

    The cloud issues a new login ID for every login, so this must hold for
    login IDs other than the one at setup.
    """
    credentials = password_credentials("secret")
    assert "secret" not in credentials.values()

    with_password = _MideaCloud(appkey="key", account="a", password="secret")
    with_hashes = _MideaCloud(appkey="key", account="a", password="")
    with_hashes.use_credentials(credentials)

    for login_id in ("first-login", "second-login"):
        assert with_hashes._security.encrypt_password(
            login_id, ""
        ) == with_password._security.encrypt_password(login_id, "secret")
        assert with_hashes._security.encrypt_iam_password(
            login_id, ""
        ) == with_password._security.encrypt_iam_password(login_id, "secret")


def test_old_credentials_ask_for_password() -> None:
    """Version 0.2 stored one-time hashes; they lead to a clear login error."""
    client = MideaDehumidifierClient(
        account="a",
        app="MSmartHome",
        device_id="0123456789abcdef",
        push_token="token",
        appliance_id="1506",
        credentials={"login_id": "x", "password_hash": "y", "iam_password_hash": "z"},
    )
    with patch("midea_beautiful.cloud.MideaCloud.authenticate") as authenticate:
        with pytest.raises(MideaApiAuthError, match="Configure"):
            client.refresh()
    authenticate.assert_not_called()


def test_transparent_send_body_has_only_accepted_fields() -> None:
    """Commands carry applianceCode and only the fields the cloud accepts."""
    accepted = set(
        "stamp src clientType userId order uid deviceId utcTimestamp timestamp format"
        " language reqId applianceCode homegroupId appId waitResp isFull funId".split()
    )
    cloud = _MideaCloud(
        appkey="key", account="a", password="p", device_id="0123456789abcdef"
    )
    sent = {}

    def fake_api_request(self, endpoint, args=None, *rest, **kwargs):
        sent.update(args=args, data=kwargs.get("data"))

    with patch(
        "midea_beautiful.cloud.MideaCloud.api_request", fake_api_request
    ):
        cloud.api_request(
            "/v1/appliance/transparent/send",
            {"order": "o", "funId": "0000", "applianceId": "1506"},
        )

    assert sent["args"] == {}
    assert set(sent["data"]) <= accepted
    assert sent["data"]["applianceCode"] == "1506"
    assert sent["data"]["deviceId"] == "0123456789abcdef"


async def test_humidity_uses_5_percent_steps(hass: HomeAssistant) -> None:
    """The slider moves in 5 % steps and other values are rounded to them."""
    with patch(f"{CLIENT}.refresh", return_value=dict(STATE)):
        await _setup(hass)

    state = hass.states.get("humidifier.deshumidificateur")
    assert state.attributes["target_humidity_step"] == 5

    calls = []
    with patch(
        f"{CLIENT}.set_state",
        lambda self, **changes: calls.append(changes) or {**STATE, **changes},
    ):
        for humidity in (43, 47, 36):
            await hass.services.async_call(
                "humidifier",
                "set_humidity",
                {"entity_id": "humidifier.deshumidificateur", "humidity": humidity},
                blocking=True,
            )
    assert [c["target_humidity"] for c in calls] == [45, 45, 35]


def test_translations_have_the_same_keys() -> None:
    """Every translation covers exactly the texts of the English one."""
    folder = Path(__file__).parents[1] / "custom_components" / DOMAIN / "translations"

    def keys(tree, prefix=""):
        if not isinstance(tree, dict):
            return {prefix}
        return set().union(*(keys(v, f"{prefix}/{k}") for k, v in tree.items()))

    english = keys(json.loads((folder / "en.json").read_text(encoding="utf-8")))
    for path in folder.glob("*.json"):
        assert keys(json.loads(path.read_text(encoding="utf-8"))) == english, path.name


async def test_smart_mode_needs_auto_capability(hass: HomeAssistant) -> None:
    """Models that report the "auto" capability also get the Smart mode."""
    capabilities = {**STATE["capabilities"], "auto": 1}
    with patch(
        f"{CLIENT}.refresh", return_value={**STATE, "capabilities": capabilities}
    ):
        await _setup(hass)

    modes = hass.states.get("humidifier.deshumidificateur").attributes["available_modes"]
    assert modes == ["set", "continuous", "smart", "dry_clothes"]
