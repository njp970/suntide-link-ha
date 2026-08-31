"""Config flow: zeroconf finds the Link; the only typing is optional.

The doorstep rule carries over from the app: nobody transcribes anything a
machine already knows. Discovery brings host + deviceId from the mDNS TXT
record; the single optional field is the cloud token, pasted from the
Suntide app for households that want the plan/story/savings entities.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.core import callback

try:
    # HA ≥2025: the canonical home
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
except ImportError:  # older HA
    from homeassistant.components.zeroconf import ZeroconfServiceInfo
from homeassistant.config_entries import ConfigEntry, OptionsFlow, ConfigFlow, ConfigFlowResult

from .const import CONF_CLOUD_TOKEN, CONF_DEVICE_ID, CONF_HOST, DOMAIN


class SuntideLinkConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._device_id: str | None = None

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
        if user_input is not None:
            data = {CONF_HOST: self._host, CONF_DEVICE_ID: self._device_id}
            token = (user_input.get(CONF_CLOUD_TOKEN) or "").strip()
            if token:
                data[CONF_CLOUD_TOKEN] = token
            return self.async_create_entry(title=f"Suntide Link ({self._device_id})", data=data)
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({vol.Optional(CONF_CLOUD_TOKEN): str}),
            description_placeholders={"device": self._device_id or "Suntide Link"},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # Manual path for networks where mDNS is filtered: host + optional token.
        if user_input is not None:
            self._host = user_input[CONF_HOST]
            self._device_id = user_input[CONF_HOST]
            return await self.async_step_confirm()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
        )


class SuntideLinkOptionsFlow(OptionsFlow):
    """Change the cloud token without deleting the device.

    A token is a credential, and credentials get rotated — so needing to
    remove and re-add the integration to paste a new one is a design fault,
    not a minor inconvenience. It cost a real evening: every cloud sensor
    read "Unavailable" and the only cure was deleting the device.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            token = (user_input.get(CONF_CLOUD_TOKEN) or "").strip()
            return self.async_create_entry(data={CONF_CLOUD_TOKEN: token})
        current = self.config_entry.options.get(
            CONF_CLOUD_TOKEN, self.config_entry.data.get(CONF_CLOUD_TOKEN, "")
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CLOUD_TOKEN,
                        description={"suggested_value": current},
                    ): str
                }
            ),
        )
