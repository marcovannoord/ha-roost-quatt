"""Buttons: learn now, import the heat pump's history from Home Assistant's statistics."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RoostConfigEntry
from .const import IMPORT_DAYS
from .entity import RoostEntity


async def async_setup_entry(hass: HomeAssistant, entry: RoostConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    m = entry.runtime_data
    async_add_entities([LearnButton(m), ImportButton(m)])


class LearnButton(RoostEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:school-outline"

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "learn_now")

    async def async_press(self) -> None:
        self.mgr.spawn(self.mgr.async_learn(), "learning")


class ImportButton(RoostEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:database-import-outline"

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "import_history")

    async def async_press(self) -> None:
        self.mgr.spawn(self.mgr.async_import(IMPORT_DAYS), "import from the statistics")
