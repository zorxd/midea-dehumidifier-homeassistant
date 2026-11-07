"""Constants for the Midea Dehumidifier (Cloud) integration."""

from __future__ import annotations

DOMAIN = "midea_cloud_dehumidifier"
DEFAULT_NAME = "Midea Dehumidifier"
DEFAULT_SCAN_INTERVAL = 300
DEFAULT_APP = "MSmartHome"

CONF_ACCOUNT = "account"
CONF_PASSWORD = "password"
# Password hashes stored instead of the password
CONF_CREDENTIALS = "credentials"
CONF_APP = "app"
CONF_APPLIANCE_ID = "appliance_id"
CONF_SCAN_INTERVAL = "scan_interval"
# Generated once per entry, so the cloud always sees the same phone
CONF_DEVICE_ID = "device_id"
CONF_PUSH_TOKEN = "push_token"

# Midea apps whose cloud this integration has been tested with
APPS = ["MSmartHome", "NetHome Plus", "Midea Air"]

PLATFORMS = ["humidifier", "select", "sensor", "binary_sensor"]

# Operating modes as the appliance reports them
MODE_SET = 1
MODES = {
    MODE_SET: "set",
    2: "continuous",
    3: "smart",
    4: "dry_clothes",
}

# Fan speeds as the appliance reports them
FAN_SPEEDS = {
    40: "low",
    60: "medium",
    80: "high",
}

# The Midea app offers targets from 35 to 85 percent
MIN_HUMIDITY = 35
MAX_HUMIDITY = 85
