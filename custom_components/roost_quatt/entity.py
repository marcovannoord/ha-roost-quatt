"""Shared base entity."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .manager import RoostManager


class RoostEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, mgr: RoostManager, key: str) -> None:
        self.mgr = mgr
        self._attr_translation_key = key
        self._attr_unique_id = f"{mgr.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, mgr.entry.entry_id)}, name=mgr.entry.title, manufacturer="Roost",
                                            model="Heating planner for Quatt", entry_type=DeviceEntryType.SERVICE)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.mgr.add_listener(self.async_write_ha_state))
