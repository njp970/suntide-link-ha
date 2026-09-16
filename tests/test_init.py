"""The coordinator: the header is sent, and a 401 starts re-authentication."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.suntide_link.const import (
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_LOCAL_TOKEN,
    DOMAIN,
)

HOST = "192.168.0.42"
DEVICE = "link-0002"
TOKEN = "0123456789abcdef0123456789abcdef"
STATE_URL = f"http://{HOST}/api/v1/state"
STATE = {"deviceId": DEVICE, "pvW": 1200, "loadW": 300, "batteryW": 900, "gridW": 0, "socPct": 55}


def _entry(hass, data):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DEVICE, data=data)
    entry.add_to_hass(hass)
    return entry


async def test_sends_the_token(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(STATE_URL, json=STATE)
    entry = _entry(hass, {CONF_HOST: HOST, CONF_DEVICE_ID: DEVICE, CONF_LOCAL_TOKEN: TOKEN})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    headers = aioclient_mock.mock_calls[0][3]
    assert headers == {"Authorization": f"Bearer {TOKEN}"}
    await hass.config_entries.async_unload(entry.entry_id)


async def test_old_entry_sends_no_header(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(STATE_URL, json=STATE)
    entry = _entry(hass, {CONF_HOST: HOST, CONF_DEVICE_ID: DEVICE})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert not aioclient_mock.mock_calls[0][3]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_401_starts_reauth(hass: HomeAssistant, aioclient_mock, caplog):
    aioclient_mock.get(STATE_URL, status=401)
    entry = _entry(hass, {CONF_HOST: HOST, CONF_DEVICE_ID: DEVICE, CONF_LOCAL_TOKEN: TOKEN})
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_REAUTH
    assert flows[0]["step_id"] == "reauth_confirm"
    assert TOKEN not in caplog.text


async def test_old_entry_401_starts_reauth(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(STATE_URL, status=401)
    entry = _entry(hass, {CONF_HOST: HOST, CONF_DEVICE_ID: DEVICE})
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]


async def test_401_after_setup_starts_reauth(hass: HomeAssistant, aioclient_mock):
    """The Link updates to 0.17.0 while Home Assistant is running."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    aioclient_mock.get(STATE_URL, json=STATE)
    entry = _entry(hass, {CONF_HOST: HOST, CONF_DEVICE_ID: DEVICE})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.config_entries.flow.async_progress()

    aioclient_mock.clear_requests()
    aioclient_mock.get(STATE_URL, status=401)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=5))
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]
    await hass.config_entries.async_unload(entry.entry_id)
