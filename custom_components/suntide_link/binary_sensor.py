"""Binary sensors: the signals an automation flips on."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    if data["cloud"] is None:
        return
    device_id = entry.data[CONF_DEVICE_ID]
    device = DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name="Suntide Link",
        manufacturer="Suntide",
        model="Link",
    )
    add([GridEventActive(data["cloud"], device, device_id)])


class GridEventActive(CoordinatorEntity, BinarySensorEntity):
    """ON while a paid grid event is running — the hour your battery is
    earning £1/kWh and an automation should get out of its way (pause the
    car charger, hold the immersion)."""

    _attr_has_entity_name = True
    _attr_name = "Grid event active"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator, device, device_id):
        super().__init__(coordinator)
        self._attr_unique_id = f"{device_id}_grid_event_active"
        self._attr_device_info = device

    @property
    def is_on(self):
        return bool((self.coordinator.data or {}).get("eventActive"))
