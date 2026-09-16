"""Config flow, reauth and options: the local access token (0.3.0)."""

from ipaddress import ip_address
from unittest.mock import patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

try:
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
except ImportError:  # older HA
    from homeassistant.components.zeroconf import ZeroconfServiceInfo

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.suntide_link.const import (
    CONF_CLOUD_TOKEN,
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_LOCAL_TOKEN,
    DOMAIN,
)

HOST = "192.168.0.42"
DEVICE = "link-0002"
TOKEN = "0123456789abcdef0123456789abcdef"
NEW_TOKEN = "fedcba9876543210fedcba9876543210"
CLOUD = "cloud-token-abc"
STATE_URL = f"http://{HOST}/api/v1/state"
CLOUD_URL = f"https://suntide.energy/api/ext/v1/links/{DEVICE}/local"
STATE = {"deviceId": DEVICE, "pvW": 0, "loadW": 300, "batteryW": -300, "gridW": 0, "socPct": 55}

DISCOVERY = ZeroconfServiceInfo(
    ip_address=ip_address(HOST),
    ip_addresses=[ip_address(HOST)],
    hostname="link-0002.local.",
    name="link-0002._suntide-link._tcp.local.",
    port=80,
    type="_suntide-link._tcp.local.",
    properties={"deviceId": DEVICE, "fw": "0.17.0", "auth": "token"},
)


def _auth(call):
    headers = call[3] or {}
    return headers.get("Authorization")


@pytest.fixture(autouse=True)
def no_setup():
    with patch("custom_components.suntide_link.async_setup_entry", return_value=True):
        yield


async def _discover(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=DISCOVERY
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"
    return result


async def test_cloud_token_fetches_local_token(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(CLOUD_URL, json={"ok": True, "enabled": True, "token": TOKEN})
    aioclient_mock.get(STATE_URL, json=STATE)
    result = await _discover(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CLOUD_TOKEN: CLOUD}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_HOST: HOST,
        CONF_DEVICE_ID: DEVICE,
        CONF_CLOUD_TOKEN: CLOUD,
        CONF_LOCAL_TOKEN: TOKEN,
    }
    calls = {str(c[1]): c for c in aioclient_mock.mock_calls}
    assert _auth(calls[CLOUD_URL]) == f"Bearer {CLOUD}"
    assert _auth(calls[STATE_URL]) == f"Bearer {TOKEN}"


async def test_local_access_off_tells_the_user(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(CLOUD_URL, json={"ok": True, "enabled": False, "token": None})
    result = await _discover(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CLOUD_TOKEN: CLOUD}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "local_access_off"}
    # Nothing was sent to the Link.
    assert all(str(c[1]) != STATE_URL for c in aioclient_mock.mock_calls)


async def test_revoked_cloud_token(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(CLOUD_URL, status=401, json={"ok": False})
    result = await _discover(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CLOUD_TOKEN: CLOUD}
    )
    assert result["errors"] == {"base": "invalid_cloud_token"}


async def test_manual_token_pasted(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(STATE_URL, json=STATE)
    result = await _discover(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOCAL_TOKEN: " 0123456789ABCDEF 0123456789abcdef "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: HOST, CONF_DEVICE_ID: DEVICE, CONF_LOCAL_TOKEN: TOKEN}
    assert _auth(aioclient_mock.mock_calls[0]) == f"Bearer {TOKEN}"


async def test_badly_formed_token(hass: HomeAssistant, aioclient_mock):
    result = await _discover(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOCAL_TOKEN: "not-a-token"}
    )
    assert result["errors"] == {"base": "invalid_token_format"}
    assert aioclient_mock.call_count == 0


async def test_no_token_on_new_firmware_asks_for_one(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(STATE_URL, status=401)
    result = await _discover(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "local_token_required"}
    assert _auth(aioclient_mock.mock_calls[0]) is None


async def test_wrong_token_refused(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(STATE_URL, status=401)
    result = await _discover(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOCAL_TOKEN: TOKEN}
    )
    assert result["errors"] == {"base": "invalid_local_token"}


async def test_old_firmware_without_token_still_adds(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(STATE_URL, json=STATE)
    result = await _discover(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_LOCAL_TOKEN not in result["data"]


async def test_cloud_down_falls_back_to_link(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(CLOUD_URL, status=503)
    aioclient_mock.get(STATE_URL, status=401)
    result = await _discover(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CLOUD_TOKEN: CLOUD}
    )
    assert result["errors"] == {"base": "cloud_unreachable"}


async def test_unreachable_link(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(STATE_URL, exc=TimeoutError())
    result = await _discover(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOCAL_TOKEN: TOKEN}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_manual_path_with_link_id_uses_cloud(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(CLOUD_URL, json={"ok": True, "enabled": True, "token": TOKEN})
    aioclient_mock.get(STATE_URL, json=STATE)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_DEVICE_ID: DEVICE}
    )
    assert result["step_id"] == "confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CLOUD_TOKEN: CLOUD}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == DEVICE
    assert result["data"][CONF_LOCAL_TOKEN] == TOKEN


async def test_manual_path_rejects_odd_link_id(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_DEVICE_ID: "../overview"}
    )
    assert result["errors"] == {CONF_DEVICE_ID: "invalid_device_id"}


async def test_manual_path_old_firmware_learns_its_id(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(STATE_URL, json=STATE)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DEVICE_ID] == DEVICE
    assert result["result"].unique_id == DEVICE


def _entry(hass, data=None, options=None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DEVICE,
        data=data or {CONF_HOST: HOST, CONF_DEVICE_ID: DEVICE},
        options=options or {},
    )
    entry.add_to_hass(hass)
    return entry


async def test_reauth_fetches_from_cloud(hass: HomeAssistant, aioclient_mock):
    entry = _entry(
        hass,
        data={CONF_HOST: HOST, CONF_DEVICE_ID: DEVICE, CONF_CLOUD_TOKEN: CLOUD, CONF_LOCAL_TOKEN: TOKEN},
        options={CONF_LOCAL_TOKEN: TOKEN},
    )
    aioclient_mock.get(CLOUD_URL, json={"ok": True, "enabled": True, "token": NEW_TOKEN})
    aioclient_mock.get(STATE_URL, json=STATE)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_LOCAL_TOKEN] == NEW_TOKEN
    assert CONF_LOCAL_TOKEN not in entry.options


async def test_reauth_local_access_off(hass: HomeAssistant, aioclient_mock):
    entry = _entry(hass, data={CONF_HOST: HOST, CONF_DEVICE_ID: DEVICE, CONF_CLOUD_TOKEN: CLOUD})
    aioclient_mock.get(CLOUD_URL, json={"ok": True, "enabled": False, "token": None})
    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "local_access_off"}


async def test_reauth_pasted_token(hass: HomeAssistant, aioclient_mock):
    entry = _entry(hass)  # an entry from before 0.3.0: no tokens at all
    aioclient_mock.get(STATE_URL, json=STATE)
    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOCAL_TOKEN: NEW_TOKEN}
    )
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_LOCAL_TOKEN] == NEW_TOKEN


async def test_options_refetch_from_cloud(hass: HomeAssistant, aioclient_mock):
    entry = _entry(
        hass,
        data={CONF_HOST: HOST, CONF_DEVICE_ID: DEVICE, CONF_CLOUD_TOKEN: CLOUD, CONF_LOCAL_TOKEN: TOKEN},
    )
    aioclient_mock.get(CLOUD_URL, json={"ok": True, "enabled": True, "token": NEW_TOKEN})
    aioclient_mock.get(STATE_URL, json=STATE)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_CLOUD_TOKEN: CLOUD}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_CLOUD_TOKEN: CLOUD, CONF_LOCAL_TOKEN: NEW_TOKEN}


async def test_options_keep_saved_token_without_cloud(hass: HomeAssistant, aioclient_mock):
    entry = _entry(hass, data={CONF_HOST: HOST, CONF_DEVICE_ID: DEVICE, CONF_LOCAL_TOKEN: TOKEN})
    aioclient_mock.get(STATE_URL, json=STATE)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_CLOUD_TOKEN: "", CONF_LOCAL_TOKEN: TOKEN}
    assert _auth(aioclient_mock.mock_calls[0]) == f"Bearer {TOKEN}"


async def test_options_paste_new_token(hass: HomeAssistant, aioclient_mock):
    entry = _entry(hass, data={CONF_HOST: HOST, CONF_DEVICE_ID: DEVICE, CONF_LOCAL_TOKEN: TOKEN})
    aioclient_mock.get(STATE_URL, status=401)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_LOCAL_TOKEN: NEW_TOKEN}
    )
    assert result["errors"] == {"base": "invalid_local_token"}
