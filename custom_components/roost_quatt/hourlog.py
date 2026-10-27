"""The hourly log and the day numbers: what was planned, predicted and what happened (the look back). A mixin of RoostManager (manager.py): the methods use its state."""
from __future__ import annotations

from .mgr_common import *  # noqa: F401,F403 - the shared imports and constants
from .mgr_common import _LOGGER, _f, _i, _iso_ts  # noqa: F401
from . import replan


class HourLogMixin:
    def _log_hour(self, now: datetime) -> None:
        """Once per hour: what the thermostat had and the inputs, so the day can be replayed for the saving."""
        hour = int(now.timestamp() // 3600 * 3600)
        if self.hour_log and self.hour_log[-1]["ts"] == hour:
            return
        room = self.room()
        sp = self.thermostat_sp() if self.mode == "active" or self.mem.virtual_sp is None else self.mem.virtual_sp
        wx = self._weather.get(hour)
        if room is None or sp is None or wx is None or not self.plan_hours:
            return
        h = self.plan_hours[0]
        pr = self.pred.get(hour, {})
        self.hour_log.append({"ts": hour, "T": round(room, 2), "E": round(self.storage_e, 2), "sp": sp, "sp_t": self.thermostat_sp(),
                              "t_out": wx[0], "rad": round(self.sun_on_house(hour, wx), 4), "hour": dt_util.as_local(now).hour,
                              "wind": wx[2] if wx[2] is not None else 3.5, "p_grid": h.p_grid, "p_own": h.p_own, "own": h.own_kw,
                              "p_imp": None if h.p_imp is None else round(h.p_imp, 4),
                              "day": self.is_day(dt_util.as_local(now)),
                              # for looking back: the plan, its reason, what was predicted for this hour, the mode
                              "sp_plan": self.plan.first.sp if self.plan and self.plan.first else None,
                              "reason": self.reason.code, "args": dict(self.reason.args),
                              "p6": pr.get("p6"), "p1": pr.get("p1"), "mode": self.mode, "window": hour in self.window.hours,
                              "paused": bool(self.mem.pause_until and self.mem.pause_until > time.time()),
                              # forecast 6 h before for this hour: [outdoor °C, sun, price, price guessed]
                              "f6": pr.get("f6"), "corr": [self.corr_kw]})
        self.hour_log = self.hour_log[-HOUR_LOG_KEPT:]
        self._log_plan(hour, room)
        self.pred = {k: v for k, v in self.pred.items() if k > hour - 7200}
        self.spawn(self.async_save(), "save the hour", background=False)   # a crash or power cut loses at most an hour

    def _log_plan(self, hour: int, room: float) -> None:
        """Everything the plan in force saw, so a decision can be replayed exactly (planner.plan with these hours, room,
        storage, output and setpoint): per hour ahead [outdoor °C, sun, wind, grid price, own price, own solar kW, hot
        water share, correction kW, price guessed], and the setpoints it planned."""
        p, guess = self.plan, self.plan_guess
        self.plan_log.append({
            "ts": hour, "at": round(self.plan_at or 0), "room": round(room, 2), "E": round(self.storage_e, 2),
            "w_now": None if self.plan_w_now is None else round(self.plan_w_now, 2), "sp_now": self.thermostat_sp(),
            "corr": [self.corr_kw, self.corr_n],
            "hours": [[round(h.t_out, 1), round(h.rad, 3), round(h.wind, 1), round(h.p_grid, 4), round(h.p_own, 4), round(h.own_kw, 2),
                       round(h.dhw, 2), round(h.extra_kw, 3), guess[i] if i < len(guess) else None] for i, h in enumerate(self.plan_hours)],
            "sp": [x.sp for x in p.hours] if p else None, "neutral": self.plan_on_guess})
        self.plan_log = self.plan_log[-PLAN_LOG_KEPT:]

    def _remember_prediction(self, now: datetime, p) -> None:
        """The room the plan expects at the start of the coming hours, 1 and 6 hours ahead, to set beside what happened."""
        base = int(now.timestamp() // 3600 * 3600)
        for j, hp in enumerate(p.hours[:6]):
            ahead = j + 1
            if ahead in (1, 6):
                self.pred.setdefault(base + ahead * 3600, {})[f"p{ahead}"] = round(hp.t_end, 2)
        if len(self.plan_hours) > 6:
            # the inputs this plan expects 6 hours ahead, to set beside what came: weather forecast and price errors
            h, guess = self.plan_hours[6], self.plan_guess[6] if len(self.plan_guess) > 6 else None
            self.pred.setdefault(base + 6 * 3600, {})["f6"] = [round(h.t_out, 1), round(h.rad, 3), round(h.p_grid, 4), guess]

    async def _async_close_day(self, day: str) -> None:
        """Replay yesterday with what Roost set and with a steady thermostat, from the same start (same model, same
        weather, same prices): the difference is the saving."""
        entries = [e for e in self.hour_log if dt_util.as_local(datetime.fromtimestamp(e["ts"], tz=timezone.utc)).date().isoformat() == day]
        if len(entries) < 20:
            return
        res = await self.hass.async_add_executor_job(planner.replay_day, self.house, self.pump, self.settings(), entries)
        if res is not None:
            self.saving_days[day] = round(res[1] - res[0], 3)
            self.saving_detail[day] = res[2]
            self.saving_detail = dict(sorted(self.saving_detail.items())[-SAVING_DETAIL_DAYS:])
        by_hand = sum(1 for e in self.events if e.get("kind") == "by_hand" and str(e.get("t", "")).startswith(day))
        self.day_stats[day] = lookback.day_stats(entries, self.settings().comfort, by_hand,
                                                 res[0] if res else None, res[1] if res else None)
        await self.async_save()

    async def _async_replay_kept_days(self) -> None:
        """After an update that replays a day differently (planner.REPLAY_VERSION): every complete day still in the
        hourly log again, so the saving of the last week (and this month) is counted one way. Older days keep theirs."""
        today = dt_util.now().date().isoformat()
        days = sorted({dt_util.as_local(datetime.fromtimestamp(e["ts"], tz=timezone.utc)).date().isoformat() for e in self.hour_log})
        for day in days:
            if day < today:
                await self._async_close_day(day)
        self.replayed_with = planner.REPLAY_VERSION
        self.event("replayed", days=[d for d in days if d < today], version=planner.REPLAY_VERSION)
        await self.async_save()

    def history_payload(self, days: int = 7) -> dict:
        """Everything the card's look back needs (websocket roost/history): the hours, the events that explain them,
        the days in numbers."""
        cut = time.time() - days * 86400
        kinds = {"set", "by_hand", "pause", "resume", "mode", "learned", "set_failed", "login_needed", "window"}
        return {"hours": [e for e in self.hour_log if e["ts"] >= cut],
                "events": [e for e in self.events if e.get("kind") in kinds and _iso_ts(e.get("t")) >= cut],
                "days": dict(sorted(self.day_stats.items())[-62:]),
                "saving_detail": self.saving_detail, "next": self.next_breakdown(),
                "plan_changes": [c for c in self.plan_changes if c["ts"] >= cut],
                "comfort": self.settings().comfort, "currency": self.hass.config.currency or "EUR", "mode": self.mode}

    def next_breakdown(self) -> dict | None:
        """The saving per hour of the plan in force (planner.breakdown), with the time of each hour."""
        p = self.plan
        if p is None or not p.breakdown or self.plan_at is None:
            return None
        base = int(self.plan_at // 3600 * 3600)
        g = self.plan_guess
        # price not published yet: an estimate (with plan_on_guess the mean of the known prices, see planner.neutral_prices)
        return {**p.breakdown, "neutral": self.plan_on_guess,
                "hours": [{**r, "ts": base + r["i"] * 3600, "guess": bool(g[r["i"]]) if r["i"] < len(g) else False} for r in p.breakdown["hours"]]}

    def explain_saving(self, day: str = "yesterday") -> dict:
        """roost.explain_saving: where the saving of a day (replayed at the end of it) or of the next 24 hours (the plan
        in force) comes from, hour by hour against a steady thermostat at equal comfort, and how the plan changed."""
        cur = self.hass.config.currency or "EUR"
        changes = replan.prune(self.plan_changes, time.time())
        if day == "next_24h":
            bd = self.next_breakdown()
            return {"day": day, "currency": cur, "available": bd is not None, **(bd or {}), "plan_changes": changes}
        if day == "yesterday":
            day = (dt_util.now().date() - timedelta(days=1)).isoformat()
        bd = self.saving_detail.get(day)
        on_day = [c for c in changes if dt_util.as_local(datetime.fromtimestamp(c["ts"], tz=timezone.utc)).date().isoformat() == day]
        return {"day": day, "currency": cur, "available": bd is not None, **(bd or {}), "plan_changes": on_day}

    def saving_month(self) -> float:
        month = dt_util.now().date().isoformat()[:7]
        return round(sum(v for k, v in self.saving_days.items() if k.startswith(month)), 2)
