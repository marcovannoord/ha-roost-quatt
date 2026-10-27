"""Why Roost plans or does what it does: a code with values, so the card can show it in the user's language.

The English text stays available as str(reason), for the state attributes and the logs. The card holds the same
codes in its own language tables; a code it does not know falls back to this English text.
"""
from __future__ import annotations

from dataclasses import dataclass, field

EN = {
    "starting": "starting",
    "window_open": "window open: Roost waits until the room is back",
    "no_price": "no price",
    "no_room": "no room temperature",
    "no_weather": "no weather forecast and no outdoor temperature",
    "no_plan": "no plan",
    "off": "Roost is off",
    "airing": "window open: thermostat at its lowest until it closes",
    "fallback_no_price": "no price: planned on one flat price",
    "fallback_schedule": "no full plan: comfort schedule",
    # planner: the first hour
    "store_solar": "charging the floor on own solar (up to {sp:g} °C)",
    "store_cheap": "charging the floor now ({ct:.0f} ct) before more expensive hours",
    "expensive": "expensive hour ({ct:.0f} ct): living off the heat in the floor",
    "store_solar_house": "storing heat in the house on own solar (up to {sp:g} °C)",
    "store_cheap_house": "storing heat in the house now ({ct:.0f} ct) before more expensive hours",
    "expensive_house": "expensive hour ({ct:.0f} ct): living off the heat in the house",
    "store_ahead": "warming the floor ahead of dearer hours ({ct:.0f} ct from {at}:00)",
    "store_ahead_house": "warming the house ahead of dearer hours ({ct:.0f} ct from {at}:00)",
    "warm_enough": "warm enough ({room:.1f} °C): no heat needed",
    "holding": "keeping the room at temperature",
    # control: what happens with the thermostat
    "paused": "changed by hand: leaving the thermostat alone for {min:.0f} more min",
    "already_right": "thermostat already right",
    "wait": "next change allowed in {min:.0f} min",
    "urgent": "room below the minimum: correcting now",
    "following": "following the plan",
    "min_run": "the heat pump just started: lowering in {min:.0f} min",
    "set_failed": "could not set the thermostat: trying again in {min:.0f} min",
}


@dataclass(frozen=True)
class Reason:
    code: str
    args: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return EN[self.code].format(**self.args)

    def as_dict(self) -> dict:
        return {"code": self.code, "args": dict(self.args), "text": str(self)}
