# SPDX-FileCopyrightText: 2026 Xavier Douville
# SPDX-License-Identifier: GPL-3.0-or-later

"""Client for Midea dehumidifiers through the Midea cloud.

Wraps the midea-beautiful-air library, which is synchronous: call these
methods from an executor. The library is not maintained, so this module also
works around changes to the Midea cloud that it predates.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import md5, sha256
from secrets import token_hex, token_urlsafe
from threading import Lock
from typing import Any

from midea_beautiful import appliance_state
from midea_beautiful import cloud as cloud_module
from midea_beautiful.cloud import MideaCloud
from midea_beautiful.exceptions import (
    AuthenticationError,
    CloudAuthenticationError,
    MideaError,
)
from midea_beautiful.lan import LanDevice
from midea_beautiful.midea import APPLIANCE_TYPE_DEHUMIDIFIER, SUPPORTED_APPS


class MideaApiError(Exception):
    """Base error for the Midea cloud client."""


class MideaApiAuthError(MideaApiError):
    """Raised when the cloud rejects the account or password."""


def password_credentials(password: str) -> dict[str, str]:
    """Return the password hashes to store instead of the password.

    These are the parts of the Midea login hashes that depend only on the
    password. The cloud's format leaves no room for a salt of our own.
    """
    return {
        "password_sha256": sha256(password.encode("ascii")).hexdigest(),
        "password_md5_md5": md5(
            md5(password.encode("ascii")).hexdigest().encode("ascii")
        ).hexdigest(),
    }


def new_device_identity() -> tuple[str, str]:
    """Return a new random device ID and push token for logging in.

    The library's default device ID is shared by all its users, and the cloud
    rejects logins from it (error 65027: too many logins on this device).
    """
    return token_hex(8), token_urlsafe(120)


class _MideaCloud(MideaCloud):
    """Midea cloud client that sends commands the way the cloud now expects."""

    def use_credentials(self, credentials: dict[str, str]) -> None:
        """Log in with stored password hashes instead of the password.

        The cloud receives hash(login ID + password hash + app key), with a new
        login ID for every login, so only the inner password hashes are stored.
        """
        if not {"password_sha256", "password_md5_md5"} <= credentials.keys():
            # Version 0.2 stored the outer hashes, which only work once
            raise MideaApiAuthError(
                "The stored login no longer works; enter the password under Configure"
            )
        appkey = self._security._appkey

        def outer(login_id: str, inner: str) -> str:
            return sha256((login_id + inner + appkey).encode("ascii")).hexdigest()

        self._security.encrypt_password = lambda login_id, password: outer(
            login_id, credentials["password_sha256"]
        )
        self._security.encrypt_iam_password = lambda login_id, password: outer(
            login_id, credentials["password_md5_md5"]
        )

    def api_request(self, endpoint, args=None, *rest, **kwargs):
        # The cloud rejects unknown fields in transparent/send: it wants
        # "applianceCode" instead of "applianceId", and none of the extra
        # fields the library adds when the body has no "reqId"
        if endpoint == "/v1/appliance/transparent/send" and args:
            kwargs["data"] = {
                "appId": self._appid,
                "format": cloud_module.CLOUD_API_FORMAT,
                "clientType": cloud_module.CLOUD_API_CLIENT_TYPE,
                "language": cloud_module.CLOUD_API_LANGUAGE,
                "src": self._appid,
                "stamp": datetime.now().strftime("%Y%m%d%H%M%S"),
                "deviceId": self._device_id,
                "reqId": token_hex(16),
                "uid": self._uid or "",
                "order": args["order"],
                "funId": args["funId"],
                "applianceCode": args.get("applianceCode", args.get("applianceId")),
            }
            args = {}
        return super().api_request(endpoint, args, *rest, **kwargs)


class MideaDehumidifierClient:
    """Read and control one dehumidifier through the Midea cloud.

    Give it either the password or stored credentials (password hashes). After
    a login with the password, credentials holds the hashes to store and the
    password is forgotten.
    """

    def __init__(
        self,
        account: str,
        app: str,
        device_id: str,
        push_token: str,
        appliance_id: str | None = None,
        password: str | None = None,
        credentials: dict[str, str] | None = None,
    ) -> None:
        """Initialize the client; nothing is sent until the first call."""
        self.account = account
        self.app = app
        self.device_id = device_id
        self.push_token = push_token
        self.appliance_id = appliance_id
        self.password = password
        self.credentials = credentials
        self._cloud: MideaCloud | None = None
        self._device: LanDevice | None = None
        self._lock = Lock()

    def _connect(self) -> MideaCloud:
        """Log in unless already logged in; hold the lock."""
        if self._cloud is None:
            app = SUPPORTED_APPS[self.app]
            cloud = _MideaCloud(
                appkey=app["appkey"],
                account=self.account,
                password=self.password or "",
                appid=app["appid"],
                api_url=app["apiurl"],
                sign_key=app["signkey"],
                iot_key=app.get("iotkey"),
                hmac_key=app.get("hmackey"),
                proxied=app.get("proxied"),
                pushtoken=self.push_token,
                device_id=self.device_id,
            )
            if self.password is None:
                cloud.use_credentials(self.credentials)
            cloud.authenticate()
            if self.password is not None:
                self.credentials = password_credentials(self.password)
                self.password = None
                cloud.use_credentials(self.credentials)
            self._cloud = cloud
        return self._cloud

    def _call(self, func):
        """Run func with a logged-in cloud, translating library errors.

        After an error the session is dropped, so the next call logs in again
        in case it had expired.
        """
        with self._lock:
            try:
                return func(self._connect())
            except MideaApiError:
                self._cloud = None
                raise
            except (AuthenticationError, CloudAuthenticationError) as err:
                self._cloud = None
                raise MideaApiAuthError(str(err)) from err
            except (MideaError, OSError, KeyError, ValueError) as err:
                self._cloud = None
                raise MideaApiError(str(err)) from err

    def list_dehumidifiers(self) -> list[dict[str, Any]]:
        """Return the account's dehumidifiers as id, name and model."""

        def run(cloud: MideaCloud) -> list[dict[str, Any]]:
            return [
                {
                    "id": str(item["id"]),
                    "name": item.get("name") or str(item["id"]),
                    "model": item.get("modelNumber"),
                }
                for item in cloud.list_appliances(True)
                if str(item.get("type")).lower() == APPLIANCE_TYPE_DEHUMIDIFIER
            ]

        return self._call(run)

    def refresh(self) -> dict[str, Any]:
        """Read the dehumidifier's current state."""

        def run(cloud: MideaCloud) -> dict[str, Any]:
            if self._device is None:
                # Also reads the appliance's capabilities
                self._device = appliance_state(
                    cloud=cloud,
                    use_cloud=True,
                    appliance_id=self.appliance_id,
                    appliance_type=APPLIANCE_TYPE_DEHUMIDIFIER,
                )
            else:
                self._device.refresh(cloud)
            return self._snapshot()

        return self._call(run)

    def set_state(self, **changes: Any) -> dict[str, Any]:
        """Change state attributes, e.g. running=True, and return the new state."""

        def run(cloud: MideaCloud) -> dict[str, Any]:
            if self._device is None:
                raise MideaApiError("The dehumidifier has not been read yet")
            self._device.set_state(cloud=cloud, **changes)
            return self._snapshot()

        return self._call(run)

    def _snapshot(self) -> dict[str, Any]:
        """Copy the device state, so later changes don't affect entities."""
        state = self._device.state
        return {
            "running": state.running,
            "mode": state.mode,
            "target_humidity": state.target_humidity,
            "current_humidity": state.current_humidity,
            "current_temperature": state.current_temperature,
            "fan_speed": state.fan_speed,
            "tank_full": state.tank_full,
            "tank_level": state.tank_level,
            "defrosting": state.defrosting,
            "filter_indicator": state.filter_indicator,
            "error_code": state.error_code,
            "capabilities": dict(state.capabilities or {}),
        }
