# SPDX-FileCopyrightText: 2026 Xavier Douville
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for Midea Dehumidifier (Cloud), with the Midea cloud replaced by fakes."""

import json
from pathlib import Path
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.midea_cloud_dehumidifier.api import (
    MideaApiAuthError,
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


def recording_login(appliances, seen):
    """Fake list_dehumidifiers that records the credentials it logs in with."""

    def list_dehumidifiers(self):
        seen.append(self.credentials)
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

    seen = []
    with patch(
        f"{CLIENT}.list_dehumidifiers", recording_login(ONE_APPLIANCE, seen)
    ), patch(f"{CLIENT}.refresh", return_value=dict(STATE)):
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
    # Logged in with the password hashes, which are stored instead of it
    assert seen == [password_credentials("secret")]
    assert "password" not in data
    assert data["credentials"] == password_credentials("secret")
    assert result["options"] == {"scan_interval": 60}


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
    with patch(f"{CLIENT}.list_dehumidifiers", return_value=appliances), patch(
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


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Déshumidificateur",
        unique_id="1506",
        options={"scan_interval": 60},
        data={
            "account": USER_INPUT["account"],
            "app": USER_INPUT["app"],
            "credentials": CREDENTIALS,
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


async def test_logs_in_with_stored_hashes(hass: HomeAssistant) -> None:
    """An entry logs in with its stored hashes."""
    seen = []

    def refresh(self):
        seen.append(self.credentials)
        return dict(STATE)

    with patch(f"{CLIENT}.refresh", refresh):
        await _setup(hass)

    assert seen == [CREDENTIALS]


async def test_options_new_password_replaces_hashes(hass: HomeAssistant) -> None:
    """A new password under Configure is checked, then only its hashes are kept."""
    with patch(f"{CLIENT}.refresh", return_value=dict(STATE)):
        entry = await _setup(hass)

    new_credentials = password_credentials("new-secret")
    seen = []

    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch(
        f"{CLIENT}.list_dehumidifiers", recording_login(ONE_APPLIANCE, seen)
    ), patch(
        f"{CLIENT}.refresh", return_value=dict(STATE)
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"password": "new-secret", "scan_interval": 120}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert seen == [new_credentials]
    assert entry.options == {"scan_interval": 120}
    assert entry.data["credentials"] == new_credentials
    assert "password" not in entry.data


async def test_options_new_password_reloads_with_same_interval(
    hass: HomeAssistant,
) -> None:
    """A new password takes effect even when the scan interval is unchanged."""
    with patch(f"{CLIENT}.refresh", return_value=dict(STATE)):
        entry = await _setup(hass)

    seen = []

    def refresh(self):
        seen.append(self.credentials)
        return dict(STATE)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch(f"{CLIENT}.list_dehumidifiers", return_value=ONE_APPLIANCE), patch(
        f"{CLIENT}.refresh", refresh
    ):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {"password": "new-secret", "scan_interval": 60}
        )
        await hass.async_block_till_done()

    # Reloaded and logged in with the new hashes
    assert seen and seen[-1] == password_credentials("new-secret")


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


async def test_rejected_login_asks_for_password(hass: HomeAssistant) -> None:
    """A rejected login stops polling and starts re-authentication."""
    with patch(f"{CLIENT}.refresh", side_effect=MideaApiAuthError("invalid password")):
        entry = await _setup(hass)

    assert entry.state is config_entries.ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == [config_entries.SOURCE_REAUTH]


async def test_reauth_stores_new_hashes(hass: HomeAssistant) -> None:
    """Re-authentication checks the new password, then stores only its hashes."""
    with patch(f"{CLIENT}.refresh", side_effect=MideaApiAuthError("invalid password")):
        entry = await _setup(hass)
    flow = hass.config_entries.flow.async_progress_by_handler(DOMAIN)[0]

    # A wrong password keeps the form open
    with patch(f"{CLIENT}.list_dehumidifiers", side_effect=MideaApiAuthError("no")):
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {"password": "wrong"}
        )
    assert result["errors"] == {"base": "invalid_auth"}

    seen = []
    with patch(
        f"{CLIENT}.list_dehumidifiers", recording_login(ONE_APPLIANCE, seen)
    ), patch(f"{CLIENT}.refresh", return_value=dict(STATE)):
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {"password": "new-secret"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert seen == [password_credentials("new-secret")]
    assert entry.data["credentials"] == password_credentials("new-secret")
    assert "password" not in entry.data
    assert entry.state is config_entries.ConfigEntryState.LOADED


async def test_two_speed_models_have_no_medium(hass: HomeAssistant) -> None:
    """The Cube reports fan speed capability 3 and has only low and high."""
    with patch(f"{CLIENT}.refresh", return_value=dict(STATE)):
        await _setup(hass)

    state = hass.states.get("select.deshumidificateur_fan_speed")
    assert state.attributes["options"] == ["low", "high"]


async def test_three_speed_models_have_medium(hass: HomeAssistant) -> None:
    """Models reporting three speeds (capability 7) also get medium."""
    capabilities = {**STATE["capabilities"], "fan_speed": 7}
    with patch(
        f"{CLIENT}.refresh", return_value={**STATE, "capabilities": capabilities}
    ):
        await _setup(hass)

    state = hass.states.get("select.deshumidificateur_fan_speed")
    assert state.attributes["options"] == ["low", "medium", "high"]
