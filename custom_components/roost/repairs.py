"""Repair flows: Roost can steer (switch to active), or a comfort setting learned from changes by hand. Always the
user's decision."""
from __future__ import annotations

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN


class ReadyForActiveFlow(RepairsFlow):
    def __init__(self, issue_id: str, data: dict | None) -> None:
        self._issue_id = issue_id
        self._data = dict(data or {})
        self._entry_id = self._data.get("entry_id")

    async def async_step_init(self, user_input: dict | None = None) -> data_entry_flow.FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict | None = None) -> data_entry_flow.FlowResult:
        if user_input is not None:
            entry = self.hass.config_entries.async_get_entry(self._entry_id) if self._entry_id else None
            mgr = getattr(entry, "runtime_data", None) if entry else None
            if mgr is not None:
                await mgr.async_set_mode("active")
            return self.async_create_entry(data={})
        issue = ir.async_get(self.hass).async_get_issue(DOMAIN, self._issue_id)
        return self.async_show_form(step_id="confirm", description_placeholders=(issue.translation_placeholders if issue else None) or {})


class ComfortSuggestionFlow(ReadyForActiveFlow):
    """A comfort setting learned from changes made by hand: confirm to store it."""

    async def async_step_confirm(self, user_input: dict | None = None) -> data_entry_flow.FlowResult:
        if user_input is not None:
            entry = self.hass.config_entries.async_get_entry(self._entry_id) if self._entry_id else None
            mgr = getattr(entry, "runtime_data", None) if entry else None
            if mgr is not None:
                await mgr.async_accept_suggestion(self._data["key"], self._data["value"])
            return self.async_create_entry(data={})
        return await super().async_step_confirm(None)


async def async_create_fix_flow(hass: HomeAssistant, issue_id: str, data: dict | None) -> RepairsFlow:
    if (data or {}).get("issue") == "comfort":
        return ComfortSuggestionFlow(issue_id, data)
    return ReadyForActiveFlow(issue_id, data)
