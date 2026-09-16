"""Config flow: zeroconf finds the Link; the typing is kept to a minimum.

The doorstep rule carries over from the app: nobody transcribes anything a
machine already knows. Discovery brings host + deviceId from the mDNS TXT
record. Two optional fields follow:

- the cloud token, pasted from the Suntide app for households that want the
  plan/story/savings entities. When it is given, the Link's local access
  token is fetched with it, so nothing else needs typing;
- the local access token, shown in the Suntide app once "Home Assistant and
  local access" is on for the Link. From firmware 0.17.0 the Link answers
  only with it.

Every path ends by calling the Link exactly as the coordinator will, so a
wrong token is caught here rather than as a row of unavailable sensors.
Tokens are credentials: never logged, never put in an error.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

try:
    # HA 2025 and later: the canonical home
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
except ImportError:  # older HA
    from homeassistant.components.zeroconf import ZeroconfServiceInfo
from homeassistant.config_entries import ConfigEntry, OptionsFlow, ConfigFlow, ConfigFlowResult

from . import local_auth
from .const import (
    CLOUD_BASE,
    CONF_CLOUD_TOKEN,
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_LOCAL_TOKEN,
    DOMAIN,
)


def _configured(entry: ConfigEntry, key: str) -> str | None:
    # Options win over the original setup data (a rotated token takes effect
    # without deleting the device), and a blank option means "none".
    if key in entry.options:
        return entry.options[key] or None
    return entry.data.get(key) or None


def configured_cloud_token(entry: ConfigEntry) -> str | None:
    return _configured(entry, CONF_CLOUD_TOKEN)


def configured_local_token(entry: ConfigEntry) -> str | None:
    return _configured(entry, CONF_LOCAL_TOKEN)


async def resolve_and_check(
    hass,
    host: str,
    device_id: str | None,
    cloud_token: str | None,
    typed_local_token: str | None,
    saved_local_token: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Work out the local token and prove it against the Link.

    Returns (token, error key, deviceId the Link reported). A typed token
    wins; otherwise the cloud is asked when a cloud token and a real Link id
    are known; otherwise the saved token (options flow) is kept; otherwise
    the Link is tried without one (firmware before 0.17.0 needs none).
    """
    session = async_get_clientsession(hass)
    token: str | None = None
    cloud_down = False

    typed = local_auth.normalise_token(typed_local_token)
    if typed:
        if not local_auth.is_valid_token(typed):
            return None, "invalid_token_format", None
        token = typed
    elif cloud_token and local_auth.looks_like_device_id(device_id):
        result = await local_auth.fetch_cloud_local(session, CLOUD_BASE, cloud_token, device_id)
        if result.outcome == local_auth.CLOUD_OK:
            token = result.token
        elif result.outcome == local_auth.CLOUD_UNAVAILABLE:
            cloud_down = True
            token = saved_local_token
        else:
            return None, result.outcome, None
    else:
        token = saved_local_token

    outcome, reported_id = await local_auth.probe_link(session, host, token)
    if outcome == local_auth.LINK_OK:
        return token, None, reported_id
    if outcome == local_auth.LINK_TOKEN_REQUIRED and cloud_down:
        return None, local_auth.CLOUD_UNAVAILABLE, None
    return None, outcome, None


class SuntideLinkConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._device_id: str | None = None
        self._reauth_entry: ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> "SuntideLinkOptionsFlow":
        return SuntideLinkOptionsFlow()

    async def async_step_zeroconf(self, discovery: ZeroconfServiceInfo) -> ConfigFlowResult:
        self._host = str(discovery.ip_address)
        self._device_id = discovery.properties.get("deviceId", discovery.hostname)
        await self.async_set_unique_id(self._device_id)
        # A re-announce after DHCP moved the box updates the host in place.
        self._abort_if_unique_id_configured(updates={CONF_HOST: self._host})
        self.context["title_placeholders"] = {"name": self._device_id}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            cloud_token = (user_input.get(CONF_CLOUD_TOKEN) or "").strip() or None
            token, error, reported_id = await resolve_and_check(
                self.hass,
                self._host,
                self._device_id,
                cloud_token,
                user_input.get(CONF_LOCAL_TOKEN),
            )
            if error:
                errors["base"] = error
            else:
                if reported_id and not local_auth.looks_like_device_id(self._device_id):
                    # Manual path without an id: an older Link tells us its own.
                    if local_auth.looks_like_device_id(reported_id):
                        self._device_id = reported_id
                        await self.async_set_unique_id(reported_id, raise_on_progress=False)
                        self._abort_if_unique_id_configured(updates={CONF_HOST: self._host})
                data = {CONF_HOST: self._host, CONF_DEVICE_ID: self._device_id}
                if cloud_token:
                    data[CONF_CLOUD_TOKEN] = cloud_token
                if token:
                    data[CONF_LOCAL_TOKEN] = token
                return self.async_create_entry(
                    title=f"Suntide Link ({self._device_id})", data=data
                )
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CLOUD_TOKEN): str,
                    vol.Optional(CONF_LOCAL_TOKEN): str,
                }
            ),
            errors=errors,
            description_placeholders={"device": self._device_id or "Suntide Link"},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # Manual path for networks where mDNS is filtered: the address, and
        # the Link's id when known (it lets the cloud token fetch the local
        # token; an older Link reports its own id).
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            device_id = (user_input.get(CONF_DEVICE_ID) or "").strip() or None
            if device_id and not local_auth.looks_like_device_id(device_id):
                errors[CONF_DEVICE_ID] = "invalid_device_id"
            else:
                self._host = host
                self._device_id = device_id or host
                if device_id:
                    await self.async_set_unique_id(device_id)
                    self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return await self.async_step_confirm()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_DEVICE_ID): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The Link answered 401: its local token is missing or has changed."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._reauth_entry
        assert entry is not None
        cloud_token = configured_cloud_token(entry)
        errors: dict[str, str] = {}
        if user_input is not None:
            token, error, _ = await resolve_and_check(
                self.hass,
                entry.data[CONF_HOST],
                entry.data.get(CONF_DEVICE_ID),
                cloud_token,
                user_input.get(CONF_LOCAL_TOKEN),
            )
            if error:
                errors["base"] = error
            else:
                data = {k: v for k, v in entry.data.items() if k != CONF_LOCAL_TOKEN}
                if token:
                    data[CONF_LOCAL_TOKEN] = token
                # After a reauth the token lives in one place only.
                options = {k: v for k, v in entry.options.items() if k != CONF_LOCAL_TOKEN}
                return self.async_update_reload_and_abort(
                    entry, data=data, options=options, reason="reauth_successful"
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Optional(CONF_LOCAL_TOKEN): str}),
            errors=errors,
            description_placeholders={"device": entry.data.get(CONF_DEVICE_ID) or "Suntide Link"},
        )


class SuntideLinkOptionsFlow(OptionsFlow):
    """Change the cloud token or the local token without deleting the device.

    A token is a credential, and credentials get rotated, so needing to
    remove and re-add the integration to paste a new one is a design fault,
    not a minor inconvenience. It cost a real evening: every cloud sensor
    read "Unavailable" and the only cure was deleting the device.

    Leaving the local token blank fetches it again from the cloud when a
    cloud token is set, and otherwise keeps the one already saved.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.config_entry
        errors: dict[str, str] = {}
        if user_input is not None:
            cloud_token = (user_input.get(CONF_CLOUD_TOKEN) or "").strip() or None
            token, error, _ = await resolve_and_check(
                self.hass,
                entry.data[CONF_HOST],
                entry.data.get(CONF_DEVICE_ID),
                cloud_token,
                user_input.get(CONF_LOCAL_TOKEN),
                # Nothing typed and nothing from the cloud: keep what is saved.
                saved_local_token=configured_local_token(entry),
            )
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    data={CONF_CLOUD_TOKEN: cloud_token or "", CONF_LOCAL_TOKEN: token or ""}
                )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CLOUD_TOKEN,
                        description={"suggested_value": configured_cloud_token(entry) or ""},
                    ): str,
                    vol.Optional(CONF_LOCAL_TOKEN): str,
                }
            ),
            errors=errors,
        )
