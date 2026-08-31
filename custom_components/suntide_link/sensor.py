"""Sensors: five fast local, four cloud-flavoured when a token is present."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, DOMAIN

LOCAL_SENSORS = [
    ("pvW", "Solar power", "W", SensorDeviceClass.POWER),
    ("loadW", "House load", "W", SensorDeviceClass.POWER),
    ("batteryW", "Battery power", "W", SensorDeviceClass.POWER),
    ("gridW", "Grid power", "W", SensorDeviceClass.POWER),
    ("socPct", "Battery charge", "%", SensorDeviceClass.BATTERY),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    device_id = entry.data[CONF_DEVICE_ID]
    device = DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name="Suntide Link",
        manufacturer="Suntide",
        model="Link",
    )
    entities: list[SensorEntity] = [
        LocalSensor(data["local"], device, device_id, key, name, unit, cls)
        for key, name, unit, cls in LOCAL_SENSORS
    ]
    if data["cloud"] is not None:
        c = data["cloud"]
        entities += [
            CloudHeadline(c, device, device_id),
            CloudStory(c, device, device_id),
            CloudSavings(c, device, device_id),
            CloudNextEvent(c, device, device_id),
            # The automation-grade set: timestamps and money an automation
            # can trigger on, not prose.
            CloudTimestamp(c, device, device_id, "cheapStart", "cheap_rate_starts", "Cheap rate starts"),
            CloudTimestamp(c, device, device_id, "cheapEnd", "cheap_rate_ends", "Cheap rate ends"),
            CloudTimestamp(c, device, device_id, "holdsUntil", "battery_holds_until", "Battery holds until"),
            CloudPredictedSpend(c, device, device_id),
            CloudEndSoc(c, device, device_id),
        ]
    add(entities)


class LocalSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, device, device_id, key, name, unit, cls):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = cls
        self._attr_unique_id = f"{device_id}_{key}"
        self._attr_device_info = device

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get(self._key)


class _CloudBase(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, device, device_id, suffix, name):
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_unique_id = f"{device_id}_{suffix}"
        self._attr_device_info = device


class CloudHeadline(_CloudBase):
    def __init__(self, coordinator, device, device_id):
        super().__init__(coordinator, device, device_id, "plan_headline", "Plan")

    @property
    def native_value(self):
        # HA states cap at 255 chars; the full text rides as an attribute.
        head = (self.coordinator.data or {}).get("headline") or ""
        return head[:255] or None

    @property
    def extra_state_attributes(self):
        return {"full": (self.coordinator.data or {}).get("headline")}


class CloudStory(_CloudBase):
    def __init__(self, coordinator, device, device_id):
        super().__init__(coordinator, device, device_id, "day_story", "The day so far")

    @property
    def native_value(self):
        beats = ((self.coordinator.data or {}).get("story") or {}).get("beats") or []
        return (beats[0]["text"][:255]) if beats else None

    @property
    def extra_state_attributes(self):
        beats = ((self.coordinator.data or {}).get("story") or {}).get("beats") or []
        return {"beats": [b["text"] for b in beats]}


class CloudSavings(_CloudBase):
    _attr_state_class = SensorStateClass.TOTAL
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(self, coordinator, device, device_id):
        super().__init__(coordinator, device, device_id, "battery_earned_mtd", "Battery earned this month")
        self._attr_native_unit_of_measurement = "GBP"

    @property
    def native_value(self):
        s = (self.coordinator.data or {}).get("savings")
        return round(s["mtdBatterySavingMinor"] / 100, 2) if s else None


class CloudNextEvent(_CloudBase):
    def __init__(self, coordinator, device, device_id):
        super().__init__(coordinator, device, device_id, "next_grid_event", "Next grid event")

    @property
    def native_value(self):
        ev = (self.coordinator.data or {}).get("nextEvent")
        return ev["startIso"] if ev else None

    @property
    def extra_state_attributes(self):
        ev = (self.coordinator.data or {}).get("nextEvent") or {}
        return {
            "direction": ev.get("direction"),
            "rate_per_kwh": (ev.get("rateMinorPerKwh") or 0) / 100,
            "expected_net": (ev.get("netMinor") or 0) / 100,
        }


class CloudTimestamp(_CloudBase):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, device, device_id, key, suffix, name):
        super().__init__(coordinator, device, device_id, suffix, name)
        self._key = key

    @property
    def native_value(self):
        iso = (self.coordinator.data or {}).get(self._key)
        if not iso:
            return None
        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except ValueError:
            return None


class CloudPredictedSpend(_CloudBase):
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "GBP"

    def __init__(self, coordinator, device, device_id):
        super().__init__(coordinator, device, device_id, "predicted_spend", "Predicted spend (24h)")

    @property
    def native_value(self):
        v = (self.coordinator.data or {}).get("predictedSpendMinor")
        return round(v / 100, 2) if v is not None else None


class CloudEndSoc(_CloudBase):
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, device, device_id):
        super().__init__(coordinator, device, device_id, "end_of_day_soc", "Projected end-of-day charge")

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("endSocPct")
