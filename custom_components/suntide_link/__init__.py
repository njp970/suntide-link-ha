"""Suntide Link — local-first inverter data, cloud intelligence optional.

Two coordinators, two trust domains, one honest rule: the local sensors
never depend on the cloud. If Suntide's API is unreachable the power
entities keep updating at 1 Hz off the Link on the LAN; only the
plan/story/savings entities go unavailable.
"""

from __future__ import annotations

import aiohttp
import async_timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from datetime import timedelta

from .const import (
    CLOUD_BASE,
    CLOUD_INTERVAL_SECONDS,
    CONF_CLOUD_TOKEN,
    CONF_DEVICE_ID,
    CONF_HOST,
    DOMAIN,
    LOCAL_INTERVAL_SECONDS,
)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    host = entry.data[CONF_HOST]
    token = entry.data.get(CONF_CLOUD_TOKEN)

    async def fetch_local():
        try:
            async with async_timeout.timeout(3):
                resp = await session.get(f"http://{host}/api/v1/state")
                if resp.status != 200:
                    raise UpdateFailed(f"Link answered {resp.status}")
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Link unreachable: {err}") from err

    local = DataUpdateCoordinator(
        hass,
        __import__("logging").getLogger(__name__),
        name=f"{DOMAIN}_local",
        update_method=fetch_local,
        update_interval=timedelta(seconds=LOCAL_INTERVAL_SECONDS),
    )

    cloud = None
    if token:

        async def fetch_cloud():
            try:
                async with async_timeout.timeout(15):
                    resp = await session.get(
                        f"{CLOUD_BASE}/api/ext/v1/overview",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if resp.status == 401:
                        raise UpdateFailed("token revoked — mint a new one in the Suntide app")
                    if resp.status != 200:
                        raise UpdateFailed(f"cloud answered {resp.status}")
                    return await resp.json()
            except (aiohttp.ClientError, TimeoutError) as err:
                raise UpdateFailed(f"cloud unreachable: {err}") from err

        cloud = DataUpdateCoordinator(
            hass,
            __import__("logging").getLogger(__name__),
            name=f"{DOMAIN}_cloud",
            update_method=fetch_cloud,
            update_interval=timedelta(seconds=CLOUD_INTERVAL_SECONDS),
        )

    await local.async_config_entry_first_refresh()
    if cloud:
        # Cloud failure must not block setup: local-first is the contract.
        await cloud.async_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"local": local, "cloud": cloud}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return ok
