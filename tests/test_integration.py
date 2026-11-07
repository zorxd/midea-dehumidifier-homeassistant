"""Tests for Midea Dehumidifier (Cloud), with the Midea cloud replaced by fakes."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.midea_cloud_dehumidifier.api import (
    MideaApiAuthError,
    _MideaCloud,
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

    with patch(
        f"{CLIENT}.list_dehumidifiers",
        return_value=[{"id": "1506", "name": "Déshumidificateur", "model": "41377"}],
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
        data={
            **USER_INPUT,
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
    assert dehumidifier.attributes["available_modes"] == [
        "set",
        "continuous",
        "smart",
        "dry_clothes",
    ]
    assert hass.states.get("select.deshumidificateur_fan_speed").state == "low"
    assert hass.states.get("sensor.deshumidificateur_humidity").state == "52"
    assert hass.states.get("sensor.deshumidificateur_temperature").state == "14.0"
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
