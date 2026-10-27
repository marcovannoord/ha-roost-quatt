"""Mode: off, shadow (plan only, never touch the thermostat) or active."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RoostConfigEntry
from .const import MODES
from .entity import RoostEntity


async def async_setup_entry(hass: HomeAssistant, entry: RoostConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([ModeSelect(entry.runtime_data)])


class ModeSelect(RoostEntity, SelectEntity):
    _attr_icon = "mdi:bird"
    _attr_options = MODES

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "mode")

    @property
    def current_option(self) -> str:
        return self.mgr.mode

    async def async_select_option(self, option: str) -> None:
        await self.mgr.async_set_mode(option)
