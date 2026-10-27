# Roost — setup and user guide

This guide takes you from nothing to Roost steering your heat pump, step by step, and explains what you see on the
way. It assumes you know your way around Home Assistant (adding integrations, editing a dashboard) but nothing about
Roost.

**Contents**

1. [What Roost does, in one minute](#1-what-roost-does-in-one-minute)
2. [Before you start: a checklist](#2-before-you-start-a-checklist)
3. [Install with HACS](#3-install-with-hacs)
4. [Add the integration, screen by screen](#4-add-the-integration-screen-by-screen)
5. [Add the card](#5-add-the-card)
6. [The first days: shadow mode](#6-the-first-days-shadow-mode)
7. [Letting Roost steer](#7-letting-roost-steer)
8. [Day to day](#8-day-to-day)
9. [Extra rooms (radiators upstairs, a bedroom)](#9-extra-rooms-radiators-upstairs-a-bedroom)
10. [All settings](#10-all-settings)
11. [Entities, services and automations](#11-entities-services-and-automations)
12. [Repairs: what each notice means](#12-repairs-what-each-notice-means)
13. [Troubleshooting](#13-troubleshooting)
14. [Reporting a problem](#14-reporting-a-problem)
15. [Privacy and safety](#15-privacy-and-safety)
16. [FAQ](#16-faq)
17. [Removing Roost](#17-removing-roost)

---

## 1. What Roost does, in one minute

Your heat pump follows a thermostat. Normally that thermostat sits at one temperature, or follows a fixed schedule.
Roost turns it into a **planner**:

- It makes a **24-hour plan** of thermostat settings, on the electricity price per hour, the weather forecast, your
  solar panels and home battery (if you have them) and **the heat your house can store** (a floor holds a lot). The
  plan **holds**: Roost makes it afresh only when something real changes — new prices, the room clearly off what the
  plan expected, a clearly different weather or solar forecast, a change of yours — so the thermostat does not go up
  and down with every small change.
- When an hour is cheap and an expensive evening follows, it **charges the floor** a little; in the expensive hours the
  house **lives off that heat** while the heat pump does less.
- It keeps the water **lukewarm** (the heat pump's efficiency, its COP, is best then), never lets the room get colder
  than your minimums, changes the thermostat **at most once an hour**, and steps aside for **two hours** when you
  change the thermostat yourself.
- It **learns your house and your heat pump by itself** — from Home Assistant's history and from the heat pump's own
  hourly logs at Weheat (a year back, read-only) — and checks every night how well its plans come true.
- It starts in **shadow mode**: it only shows what it would do. You decide when it may steer.

Roost is not made by or affiliated with Weheat. It only changes the setpoint of your thermostat — never anything in
the heat pump itself.

---

## 2. Before you start: a checklist

Tick these off first; each one saves you a support question later.

| | What | How to check |
|---|---|---|
| ☐ | **Home Assistant 2025.3 or newer**, with the recorder (default) | Settings → About |
| ☐ | **The Weheat integration works** | Settings → Devices & services → Weheat: your heat pump shows sensors such as *Heat pump state*, *Energy output heating*, *Electricity used heating* |
| ☐ | **Your thermostat is in Home Assistant** as a `climate` entity, and you can change its temperature from Home Assistant | Open the thermostat in Home Assistant and change the temperature: the real thermostat follows |
| ☐ | **The heat pump follows the thermostat** (not only its own heating curve) | In the Weheat app the heat pump is set to follow the thermostat (OpenTherm, or on/off via the thermostat). Roost also checks this itself and tells you if it does not |
| ☐ | **An electricity price** | A dynamic contract: a sensor with the prices of the coming hours (evcc, Nord Pool, Tibber, ENTSO-e, Frank Energie, …). A fixed contract: you just type in your rate |
| ☐ | **Nothing else steers the thermostat** | Turn off the thermostat's own schedule (and any automation, Node-RED flow or other integration that changes its setpoint) before you let Roost steer — otherwise they fight. Shadow mode is fine alongside them |
| ☐ | Optional: **a room temperature sensor** in the room of the thermostat | Better than the thermostat's own reading |
| ☐ | Optional: **solar power, solar forecast, home battery** sensors | From your inverter / battery integration, Solcast or Predbat |

**Which thermostats work?**

| Setup | How well |
|---|---|
| OpenTherm thermostat (Honeywell Lyric T6, Nest, Tado, Remeha, …) | Best. Roost learns how the heat pump responds to the setpoint from the Weheat history, including last winter |
| On/off thermostat, heat pump on its heating curve when the thermostat asks | Works. Roost records the setpoint itself, so the response is learned after a few weeks |
| Heat pump only on its own heating curve (ignores the thermostat) | Roost cannot steer, and says so in Repairs |
| Smart thermostat with its own schedule or learning (Nest, Tado) | Works once that schedule / auto-adjust is turned off. Roost notices a schedule that keeps changing the thermostat and tells you |

**Floor heating, radiators or both?** All work. Floor heating stores the most heat, so Roost can shift the most and
you save the most. With radiators the house itself is the buffer: Roost learns how much and shifts less.

---

## 3. Install with HACS

Roost is installed through [HACS](https://hacs.xyz) (the Home Assistant Community Store). The quickest way is this
button — it opens Roost in your own HACS:

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Akashironld&repository=ha-roost&category=integration)

Or by hand:

1. In Home Assistant open **HACS**.
2. Top right, click the **⋮** (three dots) → **Custom repositories**.
3. Paste the address of this repository, choose type **Integration**, click **Add**.
4. Search HACS for **Roost** and open it. While Roost is in beta its versions are *pre-releases*, which HACS hides
   by default: **⋮ → Redownload** → turn on **Show beta versions** → pick the newest version → **Download**.
5. **Restart Home Assistant** (Settings → System → ⏻ Restart). Roost is not visible before the restart.

---

## 4. Add the integration, screen by screen

Go to **Settings → Devices & services → + Add integration → Roost**. Roost fills in what it can find in your Home
Assistant; you check it. Every setting can be changed later (section [10](#10-all-settings)).

### Screen 1 — Roost

| Field | What to fill in |
|---|---|
| Name | Leave *Roost* (it becomes the start of the entity names) |
| Weheat heat pump | Your heat pump, from the Weheat integration |
| Thermostat | The thermostat that drives the heat pump. If you have one thermostat that heats and does not cool, it is filled in already (air conditioners are left out) |
| Import the heat pump's history from Weheat now | Leave **on**. Roost reads a year of the heat pump's hourly logs from Weheat (read-only) and learns your house from it: the newest month right away, the rest in the background (a month every half hour). Off: Roost learns from scratch, which takes a couple of weeks |

Click **Submit**: **Weheat's login page** opens. Log in with your Weheat account and allow it; you come back to the
next screen. Nothing else to fill in — see [The Weheat login](#the-weheat-login).

### Screen 2 — The house

| Field | What to fill in |
|---|---|
| Room temperature sensor | A sensor in the room of the thermostat. Roost proposes one in the same area, or in the living room. Leave empty to use the thermostat's own reading (many show only half degrees: Roost then sees a cooling room a step at a time) |
| Heat emitters | Floor heating, radiators, or both. Only the starting values; Roost learns your house from its data |
| Building data from the Dutch building register (BAG) | Netherlands only, off by default. Sends your Home Assistant home location **once** to PDOK (Kadaster) to look up the construction year, floor area and outside walls: better starting values (useful without the Weheat import) and only the facade directions your house really has. No address is kept |
| Window and door sensors (optional) | Roost recognises airing by itself (the room falling fast); with sensors it knows at once. See *Airing* in section 8 |

### Screen 3 — Electricity price

| Field | What to fill in |
|---|---|
| Electricity price | **Dynamic (price sensor)** for a dynamic contract with a price sensor in Home Assistant; **Dynamic, day-ahead prices built in** for a dynamic contract without one; **Fixed price (contract)** for a fixed rate |
| Electricity price sensor | Only for dynamic: the sensor whose attributes hold the prices of the coming hours. Roost proposes one it can read (evcc *tariff grid forecast*, Nord Pool, Tibber, ENTSO-e, Frank Energie, …) |
| Export price | Leave empty with net metering (export is then worth the import price). After net metering ends, choose your export price sensor |

With **day-ahead prices built in** Roost fetches the day-ahead (EPEX) prices itself, per quarter hour, from
[Energy-Charts](https://energy-charts.info) — no sensor or account needed. A next screen asks:

| Field | What to fill in |
|---|---|
| Bidding zone | Your country's day-ahead market (filled in from your Home Assistant country) |
| Multiplier, fixed amount per kWh | What a kWh costs = day-ahead × multiplier + fixed amount. Netherlands: (day-ahead + purchase fee + energy tax) × 1.21 → multiplier **1.21**, fixed amount **(purchase fee + energy tax) × 1.21**. Look the fee up in your contract, the energy tax at the Belastingdienst |
| Export has its own price | Off with net metering (export is worth the import price). On after net metering ends: export = day-ahead × multiplier + fixed amount (often multiplier 1 and a small negative amount: your supplier's export fee) |

Roost plans per hour: quarter-hour prices are averaged per hour, which is what an hour of heating costs. Energy-Charts
limits how often one address may ask, so Roost asks once an hour (every quarter hour in the afternoon until
tomorrow's prices are in).

With **Fixed price** a next screen asks your rate (all in: energy, taxes, VAT), optionally a low (night/weekend) rate
with its hours, and optionally a fixed export price. With a single fixed rate Roost still saves a little: it heats more
in the warmer hours, when the heat pump is more efficient, and uses your solar.

Tomorrow's prices usually arrive in the afternoon. Until then Roost fills the missing hours with the same hour a day
earlier (shown faded on the card).

### Screen 4 — Solar and home battery

Two ticks: *I have solar panels*, *I have a home battery*. Roost ticks them already when it finds such sensors.
Without either, the next screen is skipped.

Then only the fields for what you ticked (all optional; found entities are filled in):

| Field | Why Roost wants it |
|---|---|
| Solar power | To see real solar surplus right now |
| Solar forecast today / tomorrow | To plan heating on your own solar (Solcast, Predbat, Forecast.Solar, …) |
| Grid power + its sign | To tell real solar export from a battery that sells to the grid |
| Battery state of charge, battery power, capacity, max power, reserve | So energy from the battery is valued at what refilling it costs, and solar that fills the battery anyway is treated as free. Roost also learns how the battery is charged (from the grid or not, in which hours, how full) and the reserve it is seen to stop at, which replaces the setting. In an hour in which the battery usually charges from the grid it supplies nothing: extra use there costs that hour's price. Such a battery is steered by something that also decides when it discharges, so Roost follows its usual charge per hour of the day |
| The heat pump and the home battery | *Keep the battery for the house* (default): energy the heat pump takes from the battery costs what the house misses later — the hour the battery would run empty — so Roost heats in grid hours and leaves the battery to the house. *Use the battery when that is cheaper*: when Roost has learned that the battery also charges from the grid (whoever steers it: Predbat, evcc, your supplier, a schedule), energy from it costs the cheapest of its usual charging hours ahead (with the battery's losses), as long as it is not full after that hour. For a battery whose steering plans ahead and has room |
| House power | What your whole house uses, to learn its usage per hour of the day: with solar it tells which coming hours have a surplus. Shown with a battery; leave it empty and Roost works it out from grid power + solar power (+ battery power) |
| Preference for own energy | Extra cents per kWh from the grid, to prefer your own solar a bit more. 0 is fine |

### Screen 5 — Comfort

Filled in from your thermostat's last days when Home Assistant still has them.

| Field | Meaning |
|---|---|
| Comfort hours start / end | When you want the comfort temperature (e.g. 7 to 22) |
| Weekly periods (optional) | Instead of one daily interval: comfort periods per weekday, on quarter hours, as `07:00-09:00, 17:30-22:00`; a period may run through midnight (`22:00-02:00` continues the next day). Off by default; when on, the comfort hours above are not used and the card's comfort-hour buttons are replaced by this form |
| Comfort temperature | What you want in the comfort hours (Roost aims for this; it may go a little above while storing heat) |
| Never below in the day | Hard minimum in the comfort hours |
| Never below at night | Hard minimum outside them. Keep it within about 1.5 °C of the comfort temperature: a heat pump does badly with a deep night setback |
| Warmest while storing heat | How warm the room may get when Roost charges the floor before an expensive period. Equal to the comfort temperature switches storing off |

**Advanced** (folded away; the defaults suit most houses):

| Field | Default | When to change |
|---|---|---|
| Lowest thermostat setting | 19 °C | Roost never sets the thermostat lower. Lower lets a slow heat pump stop sooner, but if Home Assistant is down the thermostat stays where Roost left it |
| Setpoint at most this above the room | 1 °C | Keeps an OpenTherm thermostat asking for lukewarm water. Raise it if radiators upstairs stay cold. With a hybrid (a gas boiler next to the heat pump, as Weheat's heat pump data says; when that is unknown, a boiler asked for in Weheat's logs) Roost keeps it at 0.5 °C at most, so a storing step does not call the boiler |
| At most one change per | 60 min | Less often if your thermostat or heat pump does not like frequent changes |
| Pause after a change by hand | 2 h | How long Roost steps aside when you change the thermostat yourself |
| Night setback of the thermostat to compare with | 0 | Only for the savings figure: the steady thermostat Roost compares with |
| Weather forecast | Open-Meteo | Open-Meteo is free, needs no account, and gives radiation and wind (the house model uses both). A weather entity works too; radiation is then estimated from the sun's height and the cloud cover |

Click **Submit**. Roost is set up — in shadow mode — and starts importing and learning.

---

## 5. Add the card

**Edit dashboard → + Add card → search "Roost"**. The card shows:

- **Header**: what Roost is doing now and why (e.g. *expensive hour (46 ct): living off the heat in the floor*), and
  its mode (**SHADOW**, **ACTIVE**, **OFF**, **PAUSED**).
- **Tiles**: *Room* (and the heat stored in the floor), *Thermostat* (its setting now, and what Roost decides),
  *Planned* (the thermostat setting Roost wants, and the room temperature expected with it).
  The planned setting is a **thermostat setting**: with a slow heat pump Roost may set 19 °C while the room stays at
  21 °C — that means *don't heat now*, not *make the room 19 °C*.
- **Extra rooms** (if you added any): temperature, minimum and its hours; orange when below it.
- **Next 24 hours**: the planned thermostat setting (orange), the expected room temperature (white), the tariff per
  hour (bars, faded where the price is not known yet), and the comfort hours (green band). **Slide over the graph** to
  read each hour; when the planner counts another price than the tariff (a battery's refill cost, own solar) it says so.
  The line under the graph says **why** that hour is what it is (e.g. *18:00 · expensive hour (47 ct): living off the
  heat in the floor*, or *warm enough (21.2 °C): no heat needed*), from the room temperature the plan expects then.
- **Table** (the switch in the header, or tap the **Planned** tile): the plan per hour,
  Predbat-style — hours with the same setting and reason on one line (time, setting with ↑/↓ where it changes, room
  expected, tariff coloured cheap/dear, kWh) with the reason under it; below it the last 7 days per day (today open, the
  other days folded with their cost, saving and how well the room was predicted): what was planned → what was set, the
  room measured (and expected 6 hours before), price, electricity and why, with *by hand* and *window open* marked. A day that
  cost more than a steady thermostat says why (e.g. *4 h stored that were not needed: the room went up to 21.7 °C*).
  With solar or a home battery each day (and the look back's period) shows where the heating electricity came from:
  own solar, battery, grid — hot water not counted.
- **Mode**: tap the **ACTIVE / SHADOW / OFF** label to switch; *Active* asks for a second tap. Switching from *Active*
  to *Shadow* or *Off* (or removing Roost) sets the thermostat back to your comfort temperature. The menu also has
  *Pause 2 h*, *Resume now* while paused, *Away* (1 day / 3 days / 1 week, or *Home again*) and **⚙ Settings**: every
  temperature and the comfort hours with − / + (comfort, minimum by day and at night, comfort hours, lowest setpoint,
  store heat up to). They are Roost's own settings — the same as *Configure → Comfort*, which shows them too — and the
  one you change wins: the others follow it (comfort never below the day minimum, for example).
- **Curve** (the switch in the header): the heating curve advice in
  one view — the flow at 0 °C outside, the heat loss and the outdoor temperature from which the heat pump cycles; a
  graph of the flow temperature against the outdoor temperature, with the five points of the app evenly over the width:
  the advice (orange; dashed where it is calculated — colder than any hour measured — and in the zone where the heat
  pump cycles), the curve now (when Weheat gives it), what the house needs (blue, dashed; lighter in that zone, up to
  where the house needs no heat) and every
  hour the heat pump ran the whole hour as a dot (under OpenTherm or on its curve, as the legend says); then the
  five points with what the house needs and what was measured (and whether under OpenTherm or the curve), and the
  notes (*none* where the house needs no heat at all). **Indoor temperature − / +** shows the advice for another
  indoor temperature (what if — it changes neither Roost nor the thermostat). See [Heating curve advice](#heating-curve-advice).
- **Thermostat tile**: tap it for the thermostat's own controls (Home Assistant's dialog); Roost then pauses as after
  any change by hand.
- **The Roost icon** (top left) opens Roost in *Settings → Devices & services*.
- **Footer**: expected saving over the next 24 hours, yesterday and this month, against a steady thermostat; and the
  **plan error 6 h** from the nightly self-check, with *ready to steer* when Roost thinks it is — and then a
  **Let Roost steer** button (click twice).

### Look back

The switch **Overview / Table / Curve / Look back** in the card's header shows what happened instead of what is planned — in the same
place, so the card does not grow. Choose **24 h**, **48 h** or **7 d**:

- **Four numbers**: what heating cost (and the saving against the equally comfortable steady thermostat), how well the
  room was predicted 6 hours ahead, minutes below comfort (and the lowest room), and thermostat changes by Roost and
  by hand.
- **The graph**: the thermostat setting (orange) beside what Roost planned (orange, dashed) — where they part someone
  intervened; the measured room (white) beside what Roost predicted 6 hours earlier (blue, dashed) — the closer, the
  better the model; per hour the tariff and the heat delivered. **H** marks a change by hand (with the pause behind
  it), **M** a mode change, a red dot an hour that was 0.5 °C or more off. Slide over the graph for each hour: planned
  and real setting, room, price, heat and why.
- **Log** (folded; click to open): every change with its reason, and what happened an hour later against what was
  expected (✓, or *deviation*).
- **Report**: a page with the period's numbers, the graph, the log and the days, to keep or share (made in your
  browser, nothing is sent anywhere). It also shows **where the saving comes from**: per hour for yesterday and for
  the next 24 hours, Roost beside the steady thermostat it is compared with (setting, room, kWh, cost, saved), what
  the state at the end of the period still costs for each (a colder house is heat bought back later, a warmer one
  heat already bought), and every **plan change** of the last two days: the setting for that hour and the expected
  saving before → after, and why (new prices published, prices changed, weather forecast changed, room off from what
  was expected, correction from the last hours, settings, estimated prices left out, or simply a new hour; a saving
  that moves without any of these is not listed). The saving is also split into parts that add up: **less
  electricity** (waiting for the sun, not overheating, heating in warmer hours — of which in hours with sun, marked ☀
  in the table), **cheaper hours** and **heat left at the end**.

Roost keeps a week of hours and 60 days of day numbers for this; the history starts when you install 0.5.5.

Options (also in the visual editor): `compact: true` (header and tiles only, for a wall tablet), `show_tiles`,
`show_chart`, `show_curve`, `show_footer`, `view: table`, `view: curve` or `view: history` (open in the table, the curve or the look back — e.g. a
second card on an analysis page),
`history: false` (no look back switch), `language` (`en`, `nl`, `de`, `fr`), `time_format` (`24`, `12`), `title`.

```yaml
type: custom:roost-card
entity: sensor.roost_planned_setpoint
compact: true
```

---

### Heating curve advice

For a heat pump that runs on its **heating curve** (the thermostat only switches it on and off), the curve decides
how warm the water is: too warm costs efficiency, too cool leaves the house cold. Roost works out the curve your house
needs from the heat pump's own logs, every night:

1. **What the house needs**: per whole day the heat for space heating against the difference between room and
   outdoor temperature (a straight line: the heat loss). The cold days (5 °C or colder) above the line set a margin,
   so the curve covers the need on three cold days out of four (on a raw day the heat pump simply runs longer) (mild days spread far more — sun, people, cooking — and
   would make the curve needlessly warm).
2. **What your floor or radiators give off** at a given water temperature (the EN 442 relation, with the curvature of
   your kind of emitter from the setup), scaled from the hours the heat pump ran the whole hour on heating.
3. **The five points** of the Weheat app (−20, 9, 15, 20 and 25 °C outside), each just high enough that the straight
   line between them stays on or above what the house needs, for your comfort temperature.

The card shows per point the advice, the curve the heat pump has **now** (when Weheat gives Roost the installation's
settings) and the flow it **made** at that outdoor temperature. Above the outdoor temperature where the heat pump
mostly switches on and off anyway (measured from its logs), there is no advice: *leave* those points. The −20 °C point
is calculated beyond the coldest day measured. Set the points in the Weheat app.

With an OpenTherm thermostat (the usual way with Roost) the heat pump follows the thermostat, not the curve; the card
says so, and the advice applies when you switch the heat pump to its heating curve. The advice needs about 20 heating
days and 30 hours of steady heating with the flow temperature in the Weheat logs; after the update that brings it,
Roost reads the hourly logs of the past year again once to get it (in the background, about half an hour: the energy
per hour it has already). Roost keeps the Weheat hours and the past weather for 13 months.

## 6. The first days: shadow mode

In shadow mode Roost plans and shows everything, but never touches the thermostat. Use these days to look along:

1. **Weheat import** — the newest month comes in within a minute and Roost learns from it right away; the older months
   (up to a year) follow one by one in the background, because Weheat asks developers to call the energy logs at most
   once every half hour: a full year takes about six hours. Sensor *Weheat import progress* shows how far it is (%,
   with the months and the expected end in its details), *Configure → Mode* and the card say "3 of 12 months, done
   around 13:40"; sensor *Weheat import* turns to *Done* at the end. A restart carries on where it was, and still
   keeps Weheat's limits. *Waiting for the Weheat login*: Roost has no Weheat login yet or Weheat refused it — use
   *Re-authenticate* at Roost on the integration page.
2. **Learning** — right after the import, and every night at 03:30. Sensor *House model error* shows how well the house
   model predicts the room over the last week (°C; below about 0.6 is good). Its details hold what Roost learned (Settings → Devices &
   services → Roost → the sensor → ⋮ → **Details** → *Attributes*): heat loss, storage, floor delay, the facade the sun
   comes in through, and more.
3. **Self-check** — every night Roost replays the last 7 days with the setpoints that were really on the thermostat
   and compares with what happened. When the last week had too little heating (mild weather, or right after the
   import) it checks the newest week of the last two months that had enough; when there is none, it judges itself on
   the **last 8 heating weeks of the past year** (60+ heating hours each; 6 have to pass), so it can tell right away.
   Only without such weeks (no history) it waits for the heating season. Sensor *Plan accuracy* = how close it
   predicts the room 6 hours ahead (°C).
4. **Look at the card** in the morning and the evening: does the plan make sense? Does the expected room temperature
   follow the real one?

In mild autumn weather the heat pump hardly runs and there is little to save; the plan then mostly says *warm enough*.
That is normal.

---

## 7. Letting Roost steer

Roost tells you itself when it is ready, in three places — and before that, **when it expects to be**: right after
the Weheat import (plus about 15 minutes of learning) when the history is good enough, at the next nightly self-check,
after more heating hours, or only when the heating season starts. A setting that blocks it (the heat pump does not
follow the thermostat) is named instead of a time.

- **Settings → Devices & services → Roost → Configure → Mode.** It shows what the nightly self-check says, point by
  point (✅ or ⏳), with *Expected:* when it thinks it will be ready and *Checked on:* the last week or, in mild weather,
  the last heating weeks: the plan error 6 hours ahead (0.5 °C or less needed), heating hours (30 in a week needed),
  heat predicted against measured, whether the heat pump follows the thermostat and whether the setpoint moves it. Choose
  *Active* and submit — or *Shadow* / *Off* — right there.
- **The card** shows when it expects to be ready in its footer, and a green **Let Roost steer** button once it is
  (click twice, so it never happens by accident).
- **Settings → Repairs** gets a notice *ready to steer the heat pump*, and the entity *Ready to steer*
  (`binary_sensor.roost_ready_to_steer`) turns on — handy for a notification on your phone. Its details hold
  *waiting_for*, *expected* and, in mild weather, *heating_weeks_check*.

You can always switch yourself as well: entity **Roost Mode** (`select.roost_mode`).

Before you do:

- **Turn off everything else that changes the thermostat**: its own schedule, automations, Node-RED flows. Roost plans
  the whole day.
- Expect the thermostat to show settings that look odd (19 °C in the evening, 21.5 °C in the afternoon): they are
  levers, the room stays within your comfort settings. Check the *room expected* line, not the setpoint.

Back to shadow or off: `select.roost_mode` → *Shadow* / *Off*. In *Off* Roost does nothing at all.

---

## 8. Day to day

- **Changing the thermostat yourself is fine.** Roost steps aside for 2 hours (*Paused* on the card), then plans again
  from where the house is.
- **Comfort suggestions.** When you keep making the same change by hand (warmer in the evening, earlier in the
  morning) on three different days within two weeks, a notice in Repairs suggests a setting. One click to accept, or
  ignore it. Roost never changes your settings by itself.
- **Going away?** Tap the mode label in the card → *Away: 1 day / 3 days / 1 week* (or call `roost.away` with
  `until` or `days`, and `minimum`, default 16 °C). Roost then keeps only that minimum — no comfort hours — and plans
  the house warm again in time for when you are back (*Home again* ends it early, or `roost.home`). It pays most for a
  few days away: a slow, well-insulated house is often kept warm through a single day rather than reheated. Roost
  never sets the thermostat below its lowest setpoint: lower that too if the house may get colder than it.
- **Holidays and visitors** need nothing: the correction from the last hours notices a warmer or colder house within
  hours (from the hours without sun; with only a thermostat that shows half degrees there is no correction — a step
  of 0.5 °C would look like 7 kW).
- **Airing** needs nothing either. When the room falls fast — 0.5 °C within 15 minutes, which no house does by
  itself; 1 °C when the room temperature comes from a thermostat that shows half degrees, so its rounding is not taken
  for a window — or a window sensor you chose opens, Roost recognises an open window. With a **window sensor** Roost
  sets the thermostat to the lowest setpoint, so the heat pump stops heating the outdoors, and goes back to the plan
  when the window closes. Recognised from the room alone (which can be a false alarm) the card says *window open:
  Roost waits*: Roost does not touch the thermostat and waits until the room is back (at most three hours). Those hours are left out of what Roost learns from — the correction, the self-check, the heat
  pump's response and the house model — so airing never looks like a house that suddenly loses more heat. The look
  back marks it (**W** in the graph, and in the log).

---

## 9. Extra rooms (radiators upstairs, a bedroom)

The thermostat is in one room. Other rooms only get heat while the heat pump runs for that thermostat — so if Roost
lets the heat pump rest in an expensive evening, a bedroom upstairs with radiators may cool down. Tell Roost about such
rooms and it keeps their minimums in its plan:

**Settings → Devices & services → Roost → Add room**:

| Field | Meaning |
|---|---|
| Name | e.g. *Bedroom* |
| Temperature sensor | A sensor in that room: the radiator valve's own reading or a separate sensor |
| Kind of room | Sets a minimum and its hours (below). Outside them the room may be as cool as it likes, so a valve closed on purpose stays closed |
| Minimum, from, until | Leave empty for the kind's defaults, or set your own |

| Kind | Minimum | Hours |
|---|---|---|
| Bedroom | 16 °C | 19–23 h (cool for sleeping is fine) |
| Kids' room | 18 °C | 7–21 h |
| Study | 19 °C | 8–18 h |
| Bathroom | 20 °C | 6–9 h |
| Other | 17 °C | the comfort hours |

Roost learns per room how it cools and warms (nightly, from the sensor's history), shows the rooms on the card, and
raises a notice when a room keeps staying too cold (then the water may be too lukewarm for its radiators: raise
*Setpoint at most this above the room*, or check the valve). Change or delete a room from the same page.

---

## 10. All settings

Settings → Devices & services → Roost → **Configure**. The menu shows what is set now. Each part saves when you submit
it and brings you back to the menu (*✅ Saved: …*), so you can go on to the next part; **Done** closes. Closing the
window loses nothing that was submitted.

| Part | Holds |
|---|---|
| Mode | Off / shadow / active, with what the self-check says |
| The house and the thermostat | Thermostat, room sensor, heat emitters, building register |
| Electricity price | Dynamic or fixed, price sensors (a fixed rate on the next screen) |
| Solar and home battery | One screen: a block for solar panels and the grid meter, one for the home battery, each with its tick and sensors |
| Comfort | Comfort hours and temperatures, and under *Advanced* the regulation and the weather |
| Notifications | Off until you fill in where they go: a notify entity or service (e.g. `notify.mobile_app_my_phone`). Roost then tells you when the thermostat cannot be reached or changed, when its check no longer passes while it steers, when learning fails or the Weheat login is needed (each at most every 12 hours); and, when ticked, a summary every Monday morning (heating, cost, saving, comfort, and where the heating electricity came from) |

Extra rooms are on the integration page (*Add room*, and ⋮ → *Reconfigure* per room).

### The Weheat login

Roost reads your heat pump's history from Weheat read-only, with **its own Weheat login**. You make it in the setup:
after the first screen Weheat's login page opens — log in with your **Weheat account** and allow it. Nothing else to
fill in: Roost uses the app registration you already gave the Weheat integration (only if the Weheat integration has
none, Home Assistant first asks for *application credentials* for Roost: the same Client ID and Client Secret as for
the Weheat integration, from Weheat's knowledge base).

Roost keeps and refreshes that login itself, in its own config entry like any Home Assistant login. When Weheat no
longer accepts it (a changed password, a revoked link), Home Assistant shows **Re-authenticate** at Roost on the
integration page: click it and log in again. Installs from before 0.5.3 get that notice once.

---

## 11. Entities, services and automations

| Entity | What |
|---|---|
| `select.roost_mode` | Off / Shadow / Active |
| `sensor.roost_planned_setpoint` | The thermostat setting Roost wants now. Attributes: reason, decision, the 24-hour plan with the reason per hour (`plan_why`), extra rooms |
| `sensor.roost_heating_curve_advice` (hidden) | The advised flow temperature at 0 °C outside. Attributes: the five points (outdoor, advice, made), the curve now and how the heat pump is controlled (when Weheat gives them), the heat loss, the emitter and the outdoor temperature from which it cycles |
| `sensor.roost_expected_saving_next_24_h` | Against the lowest steady thermostat that is as comfortable as the plan |
| `sensor.roost_saving_yesterday`, `sensor.roost_saving_this_month` | Yesterday replayed with the same model, weather and prices |
| `sensor.roost_heating_cost_today` | Heat pump electricity for heating × the price of each hour |
| `sensor.roost_heating_electricity_today` | The kWh of heating electricity today |
| `sensor.roost_energy_value_now` | What a kWh is worth to Roost this hour (grid price, solar it would export, or the battery's refill cost) |
| `sensor.roost_heat_pump_model` | The learned heat pump: COP, lowest output, how it follows the thermostat, hot water hours (details) |
| `sensor.roost_plan_accuracy` | Nightly self-check: the room 6 hours ahead (°C) |
| `sensor.roost_room_expected_in_6_hours` | The room the plan expects in 6 hours — beside the room sensor in a history graph it shows how well Roost predicts |
| `sensor.roost_heat_planned_this_hour` | The heat the plan has the heat pump deliver this hour (kWh) |
| `sensor.roost_house_model_error` | How well the house model predicts the room over the last week (°C); the learned house in the details |
| `sensor.roost_weheat_import` | Status of the Weheat history import |
| `sensor.roost_weheat_import_progress` | How far the import is (%), the expected end in its details |
| `binary_sensor.roost_paused_changed_by_hand` | On while Roost steps aside after a change by hand |
| `binary_sensor.roost_heat_pump_follows_the_thermostat` | Off when the heat pump runs on its own heating curve |
| `binary_sensor.roost_ready_to_steer` | On when the nightly self-check says Roost can steer; what is still missing in its details |
| `button.roost_learn_now`, `button.roost_import_history_from_weheat` | Learn now; read the Weheat history again |

Switched off by default (enable them on the device page under *+ disabled entities* if you want): heating electricity today, energy value now, heat pump model.

**Services**

| Service | Fields | Does |
|---|---|---|
| `roost.pause` | `hours` (default 2) | Leave the thermostat alone for a while |
| `roost.resume` | — | End a pause and plan again |
| `roost.away` | `until` or `days`, `minimum` (default 16) | Nobody home: only the minimum, no comfort hours; warm again in time |
| `roost.home` | — | End away |
| `roost.set_settings` | any of `comfort`, `day_min`, `night_min`, `store_max`, `lowest_setpoint`, `day_from`, `day_to` | Roost's own temperatures and comfort hours (as in *Configure → Comfort*, not the thermostat); the one changed wins, the others follow. Also in the card: mode menu → ⚙ Settings |
| `roost.import_history` | `days` (default 365) | Read the heat pump's history from Weheat again and learn |
| `roost.explain_saving` | `day`: `yesterday` (default), `next_24h` or a date of the last week (`2026-10-19`) | Returns where the saving comes from, per hour against the steady thermostat, plus the plan changes and why (*Developer tools → Actions*, tick *return response*). The same as in the report |

**Example: pause while nobody is home**

```yaml
automation:
  - alias: Roost — pause while away
    triggers:
      - trigger: state
        entity_id: zone.home
        to: "0"
        for: "01:00:00"
    actions:
      - action: roost.pause
        data:
          hours: 12
```

**Example: a notification when Roost wants attention**

Repairs already appear in Home Assistant's notifications; for your phone:

```yaml
automation:
  - alias: Roost — plan error high
    triggers:
      - trigger: numeric_state
        entity_id: sensor.roost_plan_accuracy
        above: 1.0
    actions:
      - action: notify.mobile_app_your_phone
        data:
          message: "Roost's plan is off by {{ states('sensor.roost_plan_accuracy') }} °C — have a look."
```

---

## 12. Repairs: what each notice means

| Notice | Meaning | What to do |
|---|---|---|
| Ready to steer the heat pump | The self-check says Roost predicts well enough | Submit to switch to active, or ignore |
| The heat pump does not follow the thermostat | It heats while the thermostat asks for nothing: it runs on its own heating curve | In the Weheat app, set the heat pump to follow the thermostat |
| The setpoint hardly moves the heat pump | Learned: changing the thermostat barely changes the heat pump's output | As above; or the thermostat does not pass the setpoint on |
| The thermostat is also changed by a schedule | Changes Roost did not make come back at the same time every day | Turn off the thermostat's own schedule or the automation |
| No room temperature | Neither the room sensor nor the thermostat reports one | Check the sensor's battery / connection |
| Weheat heat pump not found | The Weheat sensors are not available | Check the Weheat integration |
| *Room* stays too cold | An extra room stayed below its minimum on several days | Check its radiator valve; raise *Setpoint at most this above the room* |
| Comfort suggestion | A setting learned from your changes by hand | Submit to accept, or ignore |
| The thermostat cannot be reached | The thermostat has been unavailable for 15 minutes or more while Roost steers; Roost leaves it alone meanwhile | Check the thermostat and its integration; the notice goes when it is back |
| The thermostat cannot be changed | Changing the thermostat failed three times in a row | Check the thermostat's integration (the error is in the notice) |
| Learning failed | The nightly learning hit an error; the previous model stays | Usually passes by itself; if it stays, report it (section [14](#14-reporting-a-problem)) |
| Steering without a full plan | For three hours no electricity price, room temperature or weather forecast; Roost plans on one flat price, or follows the comfort schedule | Check the price, room and weather sensors |
| The house stays below its minimum | The room has been well below its minimum for an hour while Roost steers | Check the heat pump and the thermostat |
| The price sensor has no forecast | The price sensor gives only the current price and it changes every hour; Roost estimates the hours ahead from day-ahead prices, or plans on one flat price | Choose a sensor with at least 24 hours of prices, or the built-in day-ahead prices with your contract's formula |

---

## 13. Troubleshooting

| You see | Likely cause | Fix |
|---|---|---|
| Card: *Not available* / *no plan yet* | No price, no weather or no room temperature | Check the price sensor has a forecast in its attributes; Open-Meteo reachable; room sensor working |
| Header: *no price* | The price sensor is unavailable or has no prices | Check the sensor; or switch to a fixed price |
| The thermostat shows 19 °C while it is cold outside | It is a lever: the floor is warm, the evening is expensive | Look at *room expected*. If the room really gets too cold, raise *Lowest thermostat setting* |
| The room gets too warm in the afternoon | Roost charges the floor | Lower *Warmest while storing heat* (equal to comfort switches it off) |
| Bedroom upstairs gets cold | Radiators get no water while the heat pump rests | Add the bedroom as an extra room (section [9](#9-extra-rooms-radiators-upstairs-a-bedroom)) |
| Savings negative | Heat stored at the end of the day counts for only part of what it cost until it is used; in mild weather there is little to save | Look at the month figure, not one day; the report (or `roost.explain_saving`) shows per hour where it went |
| *Weheat import*: waiting for the Weheat login | Roost has no Weheat login yet, or Weheat refused it | *Re-authenticate* at Roost on the integration page (section [10](#the-weheat-login)) |
| *Configure → Mode* says *Heating hours* ⏳ | Too little heating lately and no heating weeks in the history yet (a new install without the Weheat import). Hours the heat pump heated with the room well above the setpoint do not count: not the thermostat asking (its own heating curve?) — *unfollowed_hours* in *Plan accuracy*'s details | Wait for colder weather; if *unfollowed_hours* is high, check the heat pump follows only the thermostat (Weheat app) |
| *Plan accuracy* high (> 1 °C) | Little heating data yet, or a change in the house (a new window, a stove) | Wait a week; the nightly learning catches up |
| Roost keeps pausing | Something else changes the thermostat | Turn off the thermostat's schedule / other automations |
| Names are English in a Dutch Home Assistant | Entity names follow the *system* language | Settings → System → General → Language |

---

## 14. Reporting a problem

1. As soon as possible after the problem: **Settings → Devices & services → Roost → ⋮ → Download diagnostics**.
   The file holds Roost's settings, the state of every entity it reads, the learned models, the inputs and result of
   the current plan (so it can be replayed), the last 48 hours, **Roost's event log** (every thermostat change and why,
   changes by hand, repairs, errors — the last 300) and its last warnings from the log. No passwords or tokens; the
   home location is left out.
2. Open an issue on GitHub with the **Bug report** form, describe what happened and **when**, and drag the file in.

---

## 15. Privacy and safety

**What leaves your Home Assistant**

| To | What | When |
|---|---|---|
| Open-Meteo | Your home location (latitude/longitude) | Every 30 minutes for the forecast; once in a while for past weather |
| Energy-Charts (api.energy-charts.info), only with the built-in day-ahead prices | Your bidding zone (e.g. NL) | Once an hour |
| Weheat (auth.weheat.nl, api.weheat.nl) | Your Weheat login (made on Weheat's own page, refreshed by Home Assistant's OAuth helper); read-only requests, within Weheat's limits for developers | The history import (a month per request, at most a year back), and once a night for the last hours and the installation's settings (control method, heating curve) |
| PDOK (Kadaster), only if you turned it on | Your home location, once | Building register lookup |

Roost never sees your Weheat password (you type it on Weheat's page), never writes to the heat pump, has no account
and sends nothing anywhere else. Its Weheat login is kept like any Home Assistant login and is left out of the
diagnostics.

**Safety**

- Roost only changes the **thermostat setpoint**, never below *Lowest thermostat setting* (19 °C by default) — also
  what stays on it if Home Assistant goes down.
- It never lets the room go below your minimums on purpose, and corrects at once when it does.
- At most one change per hour; it steps aside when you change the thermostat yourself.
- Shadow mode and *Off* are always one click away.

---

## 16. FAQ

**How much does it save?** Honestly: it depends on your heat pump, your floor and your prices, and beta testers will
tell. In [closed-loop simulations](SIMULATIONS.md) against an equally comfortable steady thermostat (v0.7.1, 28
scenarios × 2 weeks, median 5 %): about 3–6 % with floor heating and a slow OpenTherm heat pump (it follows a new
setpoint over hours, so there is less to shift), about 5 % with a fixed price (heating in the warmer, more efficient
hours), 8–11 % with radiators or an on/off thermostat. Own solar and a home battery add to it. The card shows it against a steady thermostat that is as comfortable as Roost's
plan.

**Why does the expected saving change during the day?** Roost keeps the plan it made and works out every hour what
it gives with what it knows then. The plan itself is made afresh when tomorrow's prices are published (in the
afternoon), when the weather or solar forecast changes clearly, when the room is clearly warmer or colder than
expected, or when you change something; and the 24 hours move on an hour. The report and
`roost.explain_saving` list each change with the setting and expected saving before → after and why. Hours whose
price is not published yet are filled in from the same hour a day earlier; Roost never changes the thermostat because
of such an estimate: when only the estimates would make it do something else now, it plans as if those hours cost the
average of the known prices.

**How is the saving calculated?** Roost plays the same hours twice with the same house model, weather and prices:
once with its own settings, once with a steady thermostat — on the same 0.5 °C steps and exactly as comfortable as
Roost (when one step is a little too cold and the next too warm, the two are weighed). The difference in cost is the saving, plus the difference in what the house's state at the end
still costs: a house left colder must be heated back later, so turning down at the end of a day is not counted as a
saving. Yesterday is replayed after midnight with what really happened.

**Does it work with an air conditioner as well?** No, Roost is for a Weheat heat pump driven by a thermostat.

**My thermostat is not in Home Assistant.** Roost needs to change its setpoint: add it to Home Assistant first (most
OpenTherm and smart thermostats have an integration).

**Can I keep my own schedule?** In shadow mode, yes. In active mode Roost replaces it: put your wishes in the comfort
settings instead.

**What happens after a restart of Home Assistant?** Roost remembers everything (models, plan state, pauses) and carries
on.

---

## 17. Removing Roost

Settings → Devices & services → Roost → ⋮ → **Delete**. Your thermostat keeps its last setting: set it back to your
usual temperature. Then remove Roost in HACS if you like.
