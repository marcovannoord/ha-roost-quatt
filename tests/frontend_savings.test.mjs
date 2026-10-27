import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import assert from "node:assert/strict";

const elements = new Map();
const registry = { get: (name) => elements.get(name), define: (name, value) => elements.set(name, value) };
vm.runInNewContext(readFileSync(fileURLToPath(new URL("../custom_components/roost_quatt/frontend/roost-quatt-card.js", import.meta.url)), "utf8"), {
  HTMLElement: class {}, window: { customElements: registry }, console: { info() {} },
  setInterval() {}, clearInterval() {}, Date, Intl,
});
const Card = elements.get("roost-quatt-card");

function card(language = "nl") {
  const c = new Card();
  c._config = { language };
  c._hass = { locale: { language }, config: { currency: "EUR" } };
  c._histAt = Date.now();
  return c;
}

test("all languages explain why the saving is unavailable", () => {
  for (const lang of ["en", "nl", "de", "fr"]) {
    const c = card(lang);
    const text = c._savingQuality({ valid: false, reasons: ["energy_mismatch", "missing_context"] });
    assert.ok(text.length > 50);
    assert.ok(!text.includes("energy_mismatch") && !text.includes("missing_context"));
  }
});

test("a limited tariff horizon is visible and the missing 24-hour estimate is explained", () => {
  for (const lang of ["en", "nl", "de", "fr"]) {
    const c = card(lang);
    assert.equal(c._priceHorizon({}), "");
    assert.equal(c._priceHorizon({ price_limited_until: "invalid" }), "");
    const msg = c._priceHorizon({ price_limited_until: "2026-10-27T00:00:00+01:00" });
    assert.ok(msg.length > 50 && !msg.includes("{time}"));
    const reason = c._savingQuality({ valid: false, reasons: ["incomplete_forecast"] });
    assert.ok(reason.length > 40 && !reason.includes("incomplete_forecast"));
  }
});

test("storage labels are not presented as a causal finding of unnecessary hours", () => {
  const c = card();
  const ts = Math.floor(Date.now() / 3600000) * 3600 - 86400;
  const date = new Date(ts * 1000);
  const day = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  c._hist = { hours: [{ ts, T: 23, sp_t: 22.5, sp_plan: 22.5, reason: "store_cheap", e: 0.5 }],
    events: [], days: { [day]: { cost: 0.5, saving: -0.15 } } };
  const html = c._tableBack();
  assert.ok(html.includes("voorverwarmingslabel"));
  assert.ok(!html.includes("die niet nodig waren"));
});

test("invalid days show the validation reason instead of inventing a storage cause", () => {
  const c = card();
  const ts = Math.floor(Date.now() / 3600000) * 3600 - 86400;
  const date = new Date(ts * 1000);
  const day = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  c._hist = { hours: [{ ts, T: 20.5, sp_t: 20.5, sp_plan: 20.5, reason: "store_cheap" }], events: [],
    days: { [day]: { cost: 0.04, saving: null, quality: { valid: false, reasons: ["energy_mismatch"] } } } };
  const html = c._tableBack();
  assert.ok(html.includes("wijkt te veel af van de meter"));
  assert.ok(!html.includes("uur met een voorverwarmingslabel"));
  assert.equal(c._money(null), "\u2014");
});


test("weekly settings hide the legacy hour controls and remain available in every language", () => {
  const a = { comfort: 21, day_min: 20, night_min: 19, lowest_setpoint: 19,
    store_max: 23, day_from: 7, day_to: 22 };
  for (const lang of ["en", "nl", "de", "fr"]) {
    const c = card(lang);
    const weekly = c._settingsPanel({ ...a, weekly_comfort: true });
    const daily = c._settingsPanel(a);
    // v0.8.0: the weekly periods are edited in the card itself (no button to Configure)
    assert.ok(weekly.includes("data-wsave") && daily.includes('data-wmode="1"') && !daily.includes("data-wsave"));
    assert.ok(!weekly.includes('data-set="day_from"') && daily.includes('data-set="day_from"'));
    assert.ok(!weekly.includes("undefined") && !daily.includes("undefined"));
  }
});

test("partial comfort hours draw only the scheduled quarters", () => {
  const c = card();
  c._info = () => "";
  c._pwhy = () => "";
  const a = { start: "2026-10-26T07:00:00+01:00", comfort: 21, day_min: 20, night_min: 19,
    store_max: 23, plan: [[21,20.5,.2,25,25,0],[21,20.6,.2,25,25,0]],
    day_hours: [1,0], comfort_masks: [[false,false,true,true],[false,false,false,false]] };
  const html = c._chart(a);
  assert.equal((html.match(/class="band"/g) || []).length, 2);
  assert.ok(!html.includes("NaN"));
});

const plan = [[20.5,21.2,0,25,25,0],[20.5,21.1,0,24,24,0],[21.5,21.0,.4,22,22,0],[21.5,21.3,.5,23,23,0]];

test("v0.8.0 status line, tiles and pump row in every language", () => {
  for (const lang of ["en", "nl", "de", "fr"]) {
    const c = card(lang);
    c._siblings = () => ({});
    const a = { plan, start: new Date().toISOString(), room: 21.2, comfort: 21, thermostat: 20.5, storage_kwh: 1.7,
      plan_made: new Date().toISOString(), plan_made_why: "prices", price_limited_until: new Date(Date.now() + 9e6).toISOString(),
      fallback: "no_price", decision_code: "min_run", decision_args: { min: 12 }, room_recent: [[1, 20.8], [2, 21.0], [3, 21.1]],
      pump_runs: { today: { starts: 2, minutes: 160 }, yesterday: { starts: 7, minutes: 31 }, heating: true } };
    const html = c._status(a) + c._tiles({ state: "20.5" }, a, "ok", "x") + c._pumpRow(a);
    assert.ok(html.includes("chip warn") && html.includes("spark") && html.includes("nx up") && html.includes("badge"));
    assert.ok(!html.includes("undefined") && !html.includes("NaN"), html);
  }
});

test("the weekly editor draws overnight periods on the next day and edits by the quarter", () => {
  const c = card("nl");
  const week = { monday: [[1320, 120]], tuesday: [], wednesday: [], thursday: [], friday: [], saturday: [], sunday: [[420, 1440]] };
  const a = { weekly_comfort: true, comfort_week: week, day_from: 7, day_to: 22 };
  c._wkDay = 0;
  const html = c._weekEditor(a);
  assert.equal((html.match(/class="blk over"/g) || []).length, 1);         // Monday 22:00 runs on to Tuesday 02:00
  assert.ok(html.includes("22:00") && html.includes("02:00"));
  const fresh = card("nl");
  const draft = fresh._weekDraft({ day_from: 7, day_to: 22 });               // not weekly yet: the daily hours every day
  assert.equal(JSON.stringify(draft.friday), "[[420,1320]]");
});

test("the savings calendar marks counted and excluded days", () => {
  const c = card("nl");
  const d = new Date(), key = (n) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(n).padStart(2, "0")}`;
  c._sib = () => ({ state: "1.2", attributes: { included_days: [key(1)], excluded_days: [key(2)], day_reasons: { [key(2)]: ["settings_changed"] } } });
  const html = c._calendar();
  assert.ok(html.includes('class="cd ok"') && html.includes('class="cd bad"') && !html.includes("undefined"));
});

test("the month's saving is a pill that opens the calendar", () => {
  const c = card("nl");
  c._sib = (k) => (k === "saving_month" ? { state: "1.5", attributes: { included_days: ["x"], days_expected: 12 } } : null);
  const a = { plan, start: new Date().toISOString() };
  const closed = c._status(a);
  assert.ok(closed.includes("calpill") && closed.includes("1/12"));
  c._calOpen = true;
  assert.ok(c._status(a).includes("calpill on"));
});

test("the plan graph is drawn in the card's pixels and empty bits stay hidden", () => {
  const c = card("nl");
  c._info = () => ""; c._pwhy = () => "";
  const a = { start: new Date().toISOString(), comfort: 21, day_min: 19, night_min: 19, store_max: 25, plan, day_hours: [1, 1, 1, 1] };
  c._chartW = 1032;
  assert.ok(c._chart(a).includes('viewBox="0 0 1000 172"'));
  c._chartW = undefined;
  assert.ok(c._chart(a).includes('viewBox="0 0 440 172"'));
  const quiet = [[20.5, 21, 0, 25, 25, 0]];
  assert.ok(!c._chart({ ...a, plan: quiet }).includes("l pump"));
  assert.equal(c._pumpRow({ pump_runs: { today: { starts: 0 }, yesterday: { starts: 0 }, heating: false } }), "");
  c._config = { language: "nl", show_status: false };
  assert.equal(c._status({ plan }), "");
});
