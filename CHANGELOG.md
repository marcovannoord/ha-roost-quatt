# Changelog

## v0.1.0 — Roost for Quatt

First version of the fork of Roost v0.7.7 for Quatt heat pumps.

- Reads the Quatt integration (home-assistant-quatt) instead of Weheat: the CIC's state, heat power, power input, flow temperatures and the OpenTherm thermostat's values, found by their keys.
- The heat pump's history comes from Home Assistant's long-term statistics of those sensors (no login, nothing leaves Home Assistant); seconds of heating per hour are estimated from them and counted live from the CIC's state from then on.
- Starting profiles for one Quatt outdoor unit and for a Quatt Duo.
- Electricity per hour and per day from the power input (a Quatt has no energy meter), while heating only: the units' standby (~10 W) is measured and left out, as a heat pump's own meter for heating does.
- A CIC that asks for a boiler which gives no heat (removed, or never there) does not make Roost treat it as a hybrid.
- Domain `roost_quatt`, card `custom:roost-quatt-card`, services `roost_quatt.*`.

_Below: the history of Roost itself._

## v0.7.7 — a thermostat in half degrees, the correction from hours without sun

**For everyone whose room temperature comes from the thermostat (no room sensor), and for better forecasts for everyone** — many thermostats show the room in half degrees. Roost took that rounding for an open window and for free heat, and then hardly heated. The correction from the last hours now only learns from hours without sun, which makes the forecasts a few hours ahead better.

### Fixes
- **Window open with a thermostat in half degrees**: a room that cools a tenth past a rounding point shows half a degree less at once, and near that point the reading flips back and forth. Roost took that for airing (0.5 °C within 15 minutes) — three times in one night with every window closed. A drop now also has to be two steps of the reading: 1 °C with a thermostat that shows half degrees, 0.5 °C with a room sensor as before
- **No correction from a reading in half degrees**: a room that cooled from 20.4 to 20.0 °C read as 20.0 for six hours, which the correction from the last hours took for 0.7 kW of free heat, so the plan hardly heated. A room reading that changes in steps of 0.3 °C or more now gives no correction (a step of 0.5 °C in one hour looks like 7 kW)

### Improvements
- **Correction from the last hours**: only hours without sun count. What sunny hours missed used to be carried ahead as extra sun for a day; on a year of data that made the forecasts 6 to 24 hours ahead worse. Without it they are about 5 % better, in autumn, winter and spring alike, and cost and comfort in the simulations stay the same. The nightly learning takes over what the sun really does
- The *Plan accuracy* sensor and the diagnostics no longer show `correction_sun_m2`
- Tip: a room sensor in the room of the thermostat (*Room temperature sensor* in the settings) gives Roost tenths of a degree instead of halves

### After updating
Update in HACS (or install the new `roost.zip`) and restart Home Assistant, then reload the dashboard (Ctrl+F5).

## v0.7.6 — a high lowest setpoint, a battery that keeps its charge, the tariff in the look back

**For everyone with a lowest setpoint above the day minimum or a home battery that keeps its charge for the evening** — a planner error with a high lowest setpoint is fixed, and a battery that holds its charge during the day is no longer counted on to cover the house. The look back report shows the tariff beside the price Roost counts with.

### Fixes
- **Planner**: with a lowest setpoint above the day minimum (for example 20 and 19.5), every plan stopped with an error once the room was cold; the lowest setting is now always allowed
- **Home battery**: a battery steered to keep its charge during the day for the evening was taken to cover the house whenever it had charge. Roost now learns from the battery's history in which hours it keeps its charge while the house uses the grid, and counts with the tariff in those hours (needs a grid meter and the battery's power, and about three days)

### Improvements
- **Look back report**: shows the tariff next to the price Roost counts with (*plan uses*). With a home battery these can differ: a kWh from the battery costs what it takes to buy it back later, plus the battery's losses

### After updating
Update in HACS (or install the new `roost.zip`) and restart Home Assistant, then reload the dashboard (Ctrl+F5).

## v0.7.5 — no hybrid without a gas boiler, a battery charged from the grid

**For everyone without a gas boiler whose unit was taken for a hybrid, and for everyone whose home battery also charges from the grid** — Roost now asks Weheat whether a gas boiler is installed, instead of guessing from the logs. A unit that only *asked* for a boiler a few times (all-electric units do that too) stored heat at most 0.5 °C above the room since v0.7.3, so it hardly heated ahead in cheap hours. And if your home battery is also charged from the grid (by Predbat, evcc, a supplier or a schedule), you can now let the heat pump use it when that is cheaper; by default the battery stays for the house.

### Fixes
- **Hybrid heat pumps**: whether a gas boiler is there comes from Weheat's heat pump data (*boiler type*: none, on/off or OpenTherm). The hours in which the unit asked for a boiler only decide when Weheat does not say. Without a boiler *Setpoint at most this above the room* counts again; with one Roost keeps it at 0.5 °C, now also before the boiler shows up in the logs
- **Setpoint at most this above the room** now also holds for a setpoint already set: turning it down (or a room that cooled) brings a setpoint that is too far above the room down, instead of keeping it — an OpenTherm thermostat 1.3 °C above its reading asked the unit for 37 °C water instead of 32. A setpoint may stay a quarter degree past the limit, so a room a tenth cooler does not make it step down and up again
- The plan sensor shows `hybrid`; diagnostics also show the heat pump's model, boiler type and hot water tank as Weheat knows them, and what Roost learned about the battery

### Improvements
- **Home battery charged from the grid**: Roost learns from the battery, grid and solar sensors (5-minute statistics of the last two weeks) whether and when the battery charges from the grid — all it charges beyond the solar left over. In such an hour the battery supplies nothing, so extra use costs that hour's price: a cheap midday hour in which the battery charges is no longer taken for an expensive battery hour, and the floor is charged in it. A battery that is charged from the grid is steered by something that also decides when it discharges (selling in the evening peak, keeping a charge for the morning): Roost follows its usual charge per hour of the day instead of working it out from solar and the house alone. The reserve the battery is seen to stop at replaces the *reserve* setting
- **New choice under the home battery, *The heat pump and the home battery***: *Keep the battery for the house* (default, as before) or *Use the battery when that is cheaper*: energy taken from a battery that charges from the grid then costs the cheapest of its usual charging hours ahead (÷ 0.9 for the losses) when that is cheaper than the hour it would run empty; only hours after which the battery is usually not full count

### After updating
Update in HACS (or install the new `roost.zip`) and restart Home Assistant, then reload the dashboard (Ctrl+F5).

## v0.7.4 — settings from the card without a restart, the week's saving recounted

**For everyone** — changing a temperature in the card no longer restarts Roost (the card showed *Not available* for a moment); the saving of the days Roost still keeps is counted again the current way, so this month's figure is fairer; and the table shows electricity for the past days too.

### Fixes
- **⚙ Settings in the card** (`roost.set_settings`) no longer reloads Roost: Home Assistant checks for a reload while the setting is saved, and Roost marked the change as one it takes over only after that
- **The saving of the last week** is replayed once after this update the way v0.7.3 counts it (the end counted the right way round, the steady thermostat weighed between two steps). Days before that keep the saving they had, so *this month* moves only by the days still kept; the report shows the saving in parts for yesterday right away
- **Table, last 7 days**: the kWh column shows electricity, as in the plan above it — it showed the heat delivered, three to four times as much and not comparable

### After updating
Update in HACS (or install the new `roost.zip`) and restart Home Assistant, then reload the dashboard (Ctrl+F5).

## v0.7.3 — the saving in parts, hybrids, a steadier comparison

**For everyone who looks at the saving, and for hybrid heat pumps** — the steady thermostat Roost compares with no longer jumps half a degree too warm (which made the expected saving jump, #5), the saving is shown in parts (also what waiting for the sun saved), and a hybrid keeps its gas boiler out of storing heat.

### Fixes
- **The steady thermostat to compare with** (#5): on 0.5 °C steps the one just below fell a hair short of Roost's comfort, so a whole step higher was taken — 21 °C all day for a comfort of 20.5 °C — and the expected saving jumped by what that step costs (0.23 € one moment, 0.02 € a quarter later). When one step is a little too cold and the next too warm, the two are now weighed to exactly Roost's comfort
- **Hybrid heat pumps** (#5): when Weheat's logs show a gas boiler ran, Roost puts the thermostat at most 0.5 °C above the room, so storing heat does not call the boiler (whatever *Setpoint at most this above the room* says)

### Improvements
- **The saving in parts** (report and `roost.explain_saving`): less electricity (waiting for the sun, not overheating, warmer hours), of which in hours with sun (☀ in the table), heating in cheaper hours, and heat left at the end — they add up to the saving
- **Plan changes**: a change of the expected saving that nothing explains is no longer listed as *recalculated*; a change of the setting names its largest cause
- **House model error** is measured over the last week instead of the last three days, so a few odd days (a thermostat held by hand, a sunny weekend) no longer make it jump; the model is still chosen on the newest days
- **Reasons**: *warming the floor ahead of dearer hours (43 ct from 7:00)* for an hour that is warmer than holding the room needs but not among the cheap hours

### After updating
Update in HACS (or install the new `roost.zip`) and restart Home Assistant, then reload the dashboard (Ctrl+F5) for the new card.

## v0.7.2 — Settings in the card open at the first tap

**For everyone who uses the card's settings** — tapping ⚙ Settings in the mode menu gave the error *required key not provided at 'option'* and closed the menu; it opens at the first tap now.

### Fixes
- **Card**: ⚙ Settings in the mode menu no longer also tries to switch the mode (an error, and the menu closed); the settings open at the first tap

### After updating
Update in HACS (or install the new `roost.zip`) and restart Home Assistant, then reload the dashboard (Ctrl+F5) for the new card.

## v0.7.1 — slow heat pumps save again, house power stays empty

**For everyone with a slow (OpenTherm) heat pump, and everyone who emptied a sensor field** — v0.7.0 fixed how the heat left at the end is counted, but the cost Roost gives each thermostat change was still tuned to the old count, so a slow heat pump hardly moved and saved less than before; and a sensor Roost recognises by its name came back in an emptied field (#3).

### Fixes
- **Slow heat pumps** (OpenTherm, modulating): each thermostat change now counts 5 ct in the plan instead of 15 ct. In the simulations the saving against a steady thermostat is back at or above v0.6.1 in most cases (median over 28 scenarios 2.6 % → 5.3 %; a winter month with a slow heat pump 4.2 % → 6.0 %, a fixed price 0 % → 5 %). Roost changes the thermostat about 3–4 times a day (still at most once an hour), and in a cold month the room is a little more often just below comfort (about 0.3 °C·h a day), never below your minimum
- **Configure → Solar and home battery** no longer fills a field you emptied with a sensor it recognises by its name; detected sensors are only suggested for a block you have not set up yet, and a sensor with *battery* in its name is never taken for house power (#3)
- **Away**: while the house is still empty at the end of the plan, Roost only needs the away minimum then, not the comfort temperature — it no longer keeps an empty house warm for nothing

### After updating
Update in HACS (or install the new `roost.zip`) and restart Home Assistant. If house power came back after you emptied it, empty it once more in *Configure → Solar and home battery*.

## v0.7.0 — where the saving comes from

**For everyone** — the report shows per hour where the saving comes from and why the plan changed (#1); houses that warm up quickly (radiators) no longer heat ahead on a fixed price (#4). Yesterday's saving is now counted fairly: a house left colder at the end of the day is no longer counted as a saving, so the figure can be lower than before.

### Fixes
- **Fast houses** (radiators, a short delay): the planner threw away heat still on its way to the room, so it thought the room would sink and planned higher than needed — with one fixed price it heated ahead for nothing (#4)
- **A fixed price** is never called cheap or expensive in the reasons any more (#4)
- **Heat left at the end** was counted the wrong way round in the replay of yesterday and in the planning of slow (OpenTherm) heat pumps: a colder house at the end looked like a saving. Now a colder house counts as heat to buy back later. The saving of yesterday and this month can be lower than before; slow heat pumps no longer turn down the next morning only because it looked cheaper
- **The steady thermostat** Roost compares with is on the same 0.5 °C steps as the plan, as a real thermostat is; between them it made an even plan look more expensive

### Improvements
- **Where the saving comes from** (#1): the report (*Look back → Report*) shows per hour for yesterday and the next 24 hours what Roost does beside the steady thermostat (setting, room, kWh, cost, saved) and what the state at the end still costs; the same as `roost.explain_saving` (day: `yesterday`, `next_24h` or a date of the last week) and in the diagnostics
- **Plan changes** (#1): every new plan that changes the setting for now or the expected saving by 5 ct or more is kept for two days with the setting and the saving before → after and why: new prices published, prices changed, weather forecast changed, room off from what was expected, correction from the last hours, settings, estimated prices left out, or a new hour
- **Estimated prices**: hours whose price is not published yet are filled in from a day earlier; Roost no longer changes the thermostat because of them — when only the estimates would make it do something else now, it plans as if those hours cost the average of the known prices

### After updating
Update in HACS (or install the new `roost.zip`) and restart Home Assistant, then reload the dashboard (Ctrl+F5) for the new card. The saving per hour of yesterday appears after the first midnight, plan changes from the first new plan on.

## v0.6.1 — a field left empty stays empty

**For everyone who changes settings** — a sensor left empty in *Configure* (house power, solar, battery, room or window sensors) is now really gone; before, the one chosen in the setup came back (#3).

### Fixes
- A field left empty in *Configure* no longer falls back to what was chosen in the setup (#3)

### After updating
Update in HACS (or install the new `roost.zip`) and restart Home Assistant. If you cleared a field before, it is gone now; nothing else to do.

## v0.6.0 — plan table, heating curve advice

**For everyone** — see why Roost plans each hour, the plan as a table, and the heating curve your house needs; the electricity and cost of today survive a restart (#2). After updating Roost reads the past year of hourly logs from Weheat once more (about half an hour, in the background).

### Fixes
- **Today's heating electricity and cost** no longer start at zero after a restart of Home Assistant (#2)
- **Learning**: the newest heating days count as *the house changed* only when they lie within 60 days and the test days were heated — in autumn the 30 newest heating days reached back to spring and a season was taken for a changed house; a model taken that way is replaced by the year's model
- **Learning**: the generic starting house no longer replaces a learned model on mild days without heating, and Roost does not learn when the newest hours are missing (just after a start)
- **Cheap and expensive** in the reasons are judged on the price the planner counts (own solar, the battery's refill cost or the tariff), so a reason no longer calls 46 ct cheap while the battery supplied at 29 ct
- The look back's 24 h / 48 h / 7 d buttons no longer jump back to the plan

### Improvements
- **Why each hour** (#1): a line under the plan says why the hour under your finger is what it is; the sensor carries a reason per hour (`plan_why`)
- **Table**: the plan per hour — hours with the same setting and reason on one line, with setting, room expected, tariff, kWh and why — and the last 7 days per day: planned and set, room measured and expected, price, heat, why, changes by hand and windows open
- **Heating curve advice** (*Curve* in the card, sensor `heating_curve_advice`): the flow temperatures your house needs as the five points of the Weheat app, from your heat loss, your floor or radiators and the heat pump's own logs; beside them what the house needs without margin and what the heat pump really made (and whether under OpenTherm or its curve), the zone where it cycles, and the curve it has now when Weheat gives it
- **Card**: tap the mode label to switch Off / Shadow / Active (Active asks twice), pause 2 hours or resume; the Planned tile shows the next change and opens the table; the Thermostat tile opens the thermostat's controls; the Roost icon opens the integration; a warning when Roost steers while its check has not passed
- **House power is optional**: without it Roost learns the usage per hour from grid power + solar power (+ battery power); the setup explains the field
- **Weheat history**: the flow and return temperature, thermostat demand, backup heater, gas boiler, compressor limits and errors are kept per hour (for later use without a new import); 13 months are kept; new fields are read from the hourly logs only, so that takes half an hour instead of hours
- Helper sensors (Weheat import, its progress, energy value, heat pump model, heating curve advice) are hidden in entity lists; the card still uses them
- **Away** (card menu or `roost.away`): only a minimum (default 16 °C), no comfort hours, warm again in time; `roost.home` ends it
- **Settings from the card**: tap the mode label → ⚙ Settings for every temperature and the comfort hours with − / + (`roost.set_settings`); they are the same settings as *Configure → Comfort*
- The first view of the card is called **Overview**
- **Heating curve view**: the five points evenly over the width, every steady hour as a dot, dashed where the line is calculated or in the cycling zone, and an indoor temperature − / + to see the advice for a warmer or cooler house (what if)
- **Notifications** (off until you choose where they go, *Configure → Notifications*): thermostat unreachable or not changeable, check no longer passing while steering, learning failed, Weheat login needed; optionally a weekly summary on Monday morning
- **Where the heating electricity came from**: own solar, home battery or grid, per day in the table and over the look back's period (hot water not counted)
- **Why a day cost more** than a steady thermostat: the table says it per day
- When Roost stops steering (Shadow, Off or removed) the thermostat goes back to your comfort temperature; an unreachable thermostat is left alone and a repair notice says so, as do repeated failures to change it

### After updating
Update in HACS (or install the new `roost.zip`) and restart Home Assistant, then reload the dashboard (Ctrl+F5) for the new card. Roost then reads the past year of hourly logs from Weheat once more (about half an hour); the heating curve advice appears after that.

## v0.5.6 — window open, German and French

**For everyone** — Roost now recognises airing: it waits instead of heating the outdoors, and does not learn from it.

### Improvements
- **Window open**: a fast drop of the room temperature (0.5 °C within 15 minutes) or a window/door sensor you chose (optional, *Configure → The house*) means a window is open. Roost does not change the thermostat until the room is back (at most three hours), the card says *window open: Roost waits*, and those hours are left out of the correction, the self-check, the heat pump's response and the house model. The look back marks it
- The hourly log is saved every hour, so a restart, crash or power cut loses at most an hour of the look back
- **German and French**: the setup, the settings, the notices and the card
- *Ready to steer* in mild weather no longer flips between nights: the heating weeks are fixed calendar weeks, and the verdict rests on the medians over 8 weeks (with at least 4 passing on their own)
- The README shows the card; the simulations add a winter month (28 days with a cold week: 3.8–8.8 % saving, never below the minimum); the diagnostics hold the full week of hours

### Fixes
- The card's address carries a fingerprint of the file, so a browser fetches the card again whenever it changed — also after installing a zip over the same version

## v0.5.5 — look back

**For everyone** — see what Roost planned beside what happened: a look back in the card, a log of every change and why, a report to keep.

### Improvements
- **Look back in the card**: the switch *Ahead / Look back* in the header shows the last 24 hours, 48 hours or 7 days in the same place: the thermostat setting beside what Roost planned, the measured room beside what Roost predicted 6 hours earlier, the tariff and the heat per hour, changes by hand and mode changes marked. Four numbers on top: cost and saving, how well the room was predicted, minutes below comfort, changes by Roost and by hand
- **Log** (folded): every change with its reason, and what happened an hour later against what was expected
- **Report**: a page with the period's numbers, graph, log and days, made in your browser
- **Day numbers** for 60 days: electricity, heat, COP, cost, saving, comfort, changes, how well the plan predicted
- New sensors with history: *Room expected in 6 hours* and *Heat planned this hour* — beside the room sensor in any history graph
- Card options `view: history` (a second card that opens in the look back) and `history: false`

### After updating
Update in HACS (or install the new `roost.zip`) and restart Home Assistant. The look back fills from then on: Roost now keeps a week of hours.

## v0.5.4 — built-in day-ahead prices, Zonneplan

**For everyone with a dynamic contract** — no price sensor needed any more: Roost can fetch the day-ahead prices itself. And Zonneplan's price sensor now works.

### Improvements
- **Day-ahead prices built in**: under *Electricity price* choose *Dynamic, day-ahead prices built in*. Roost fetches the day-ahead (EPEX) prices per quarter hour from Energy-Charts — no sensor or account — and plans with your supplier's formula: day-ahead × multiplier + fixed amount (Netherlands: multiplier 1.21, fixed amount (purchase fee + energy tax) × 1.21). Export can have its own formula once net metering ends
- **Zonneplan**: the forecast of *Current electricity tariff* (per hour) and *Current quarter hourly electricity tariff* is read; Roost matches the forecast's scale to the sensor's own value (Zonneplan keeps its forecast in 1e-7 euro)
- Any price forecast in other units than its sensor is scaled the same way

### After updating
Update in HACS (or install the new `roost.zip`) and restart Home Assistant. To use the built-in prices: *Settings → Devices & services → Roost → Configure → Electricity price*.

## v0.5.3 — log in with your Weheat account

**For everyone on 0.5.2** — Roost now logs in to Weheat itself: after updating, click *Re-authenticate* at Roost once. Also a calmer night forecast after a sunny day, a settings menu that stays open, and *Ready to steer* in mild weather.

### Improvements
- **Log in with your Weheat account**: in the setup, after the first screen, Weheat's login page opens — nothing to fill in (Roost uses the app registration the Weheat integration already has). Roost keeps and refreshes that login itself and no longer borrows the Weheat integration's token; when Weheat no longer accepts it, Home Assistant shows *Re-authenticate*. The choice under *Reconfigure → Weheat login* is gone
- **Ready to steer in mild weather**: when the last week had too little heating, Roost judges itself on the last 8 heating weeks of the past year (6 have to pass) instead of waiting for the heating season; *Configure → Mode* says what it was checked on
- **Settings menu**: each part saves and brings you back to the menu (*✅ Saved: …*); *Done* closes. Solar and the home battery are one screen, a block each with its tick and its sensors (before, the sensors only came after submitting the ticks)

### Fixes
- **The room hardly cooling at night in the plan**: after a sunny afternoon (sun on the facade, or on the room sensor) the correction from the last hours added up to 1 kW all night. What sunny hours miss now counts as extra sun — it follows the sun ahead and is gone at night; only what dark hours miss stays a constant correction
- The reason said *charging the floor on own solar* while no heat went in (the room at 24 °C, the thermostat at 21): with no heat planned and the room above the setpoint it now says *warm enough*
- *Expected ready to steer* said a date when the heating pace could never fill a week; now *when the heating season starts*
- Roost's background work (import, learning) stops cleanly with Home Assistant

### After updating
Install the new `roost.zip` as in [docs/TESTERS.md](docs/TESTERS.md) and restart Home Assistant, then *Settings → Devices & services → Roost → Re-authenticate*, and log in with your Weheat account.

## v0.5.2 — first beta for testers

**For the private beta testers** — the first version to install: everything in the sections below, in one beta.
Roost starts in shadow mode and only steers when you switch it on.

### Changes
- **Install and update without HACS** while the repository is private: [docs/TESTERS.md](docs/TESTERS.md). Every
  release now comes with `roost.zip` (the integration folder) and is marked as a pre-release until 1.0
- What changed before this version is in the sections below

### After updating
First install: follow [docs/TESTERS.md](docs/TESTERS.md), then the [guide](docs/GUIDE.md) from section 4.

## v0.5.0 — beta (unreleased)

- Weheat history within Weheat's limits for developers (logs at most every 2 minutes, energy logs at most every half
  hour): a month per call (longer is refused), newest month first, Roost learns after the first month and the rest
  comes in the background (a year takes some hours); a restart carries on where it was; from the commissioning date
  at most a year back. Every call is in the event log
- Learning: never more than a year; recent heating counts most — counted in heating days, so a summer without heating
  does not age last winter; days without heating count a quarter; a model of only the newest heating days takes over
  when it clearly predicts better (a house that was insulated)
- Mode in Roost itself: *Configure → Mode* shows what the self-check says (plan error, heating hours, heat, follows,
  lever) and switches off / shadow / active; a *Ready to steer* binary sensor; the card shows a *Let Roost steer*
  button when it is ready (click twice)
- Calmer: a thermostat change has to be worth more (about 1–2 a day instead of ~5), and the comfort temperature weighs
  more, so fewer changes do not cost comfort — chosen with closed-loop simulations of eight kinds of houses
  ([docs/SIMULATIONS.md](docs/SIMULATIONS.md), `tools/sim/sim.py`)
- The saving shown is against a steady thermostat that is as comfortable as Roost's plan (it could be colder before,
  which made a comfortable plan look expensive)
- A setup and user guide ([docs/GUIDE.md](docs/GUIDE.md)); the README is now a front page with a quick start
- When it expects to be ready to steer: after the import, at the next self-check, after more heating, in the heating
  season — or which setting blocks it. In *Configure → Mode*, the card and the *Ready to steer* sensor
- How far the Weheat import is: sensor *Weheat import progress* (%), and "3 of 12 months, done around 13:40" in
  *Configure → Mode* and on the card. The time of the last Weheat call is kept, so a restart during the import still
  keeps Weheat's limits
- The self-check uses the newest week of the last two months with enough heating when the last week had too little
  (mild weather, right after the import), so Roost can say right away whether it is ready; a spring week is not
  used to judge steering in autumn
- Optional: Roost's own Weheat login (*Reconfigure → Weheat login*): log in with your Weheat account on Weheat's page,
  nothing to fill in (Roost uses the app registration the Weheat integration already has). Roost keeps and refreshes
  it itself, so the import never waits for the Weheat integration's login. Default stays the Weheat integration's
  login
- Hours the heat pump heated without the thermostat asking (the room well above its setpoint, beyond what the learned
  response explains — e.g. its own heating curve in spring and autumn) are left out of learning the response and of
  the self-check, and counted (*unfollowed_hours*)
- The heat pump's response fit leaves out its worst 10 % of windows (cooking, a door open, the unit doing something
  else), so a few odd hours do not steer it
- Simulations of seven more kinds of houses and prices (old house, new build, apartment, cold snap, volatile prices,
  a heat pump that responds differently than learned, autumn with an own heating curve): 1.5–10 % saving at about the
  steady thermostat's comfort ([docs/SIMULATIONS.md](docs/SIMULATIONS.md))
- A house that changed (insulated): the heat pump's response is learned from the new house's days only, like the
  house model (in the simulation it was too cold before: 15–20 °C·h a week below comfort, now ~1)

## v0.4.1 — setup by subject (unreleased)

- Setup and options by subject: the heat pump and thermostat, the house, the electricity price, solar and home
  battery (two ticks first: only the fields for what the house has), comfort with the regulation and the weather
  folded away under *Advanced*. The options menu shows what is set now; each part saves when submitted
- Likely entities are filled in: the thermostat (a climate entity that heats and does not cool), the room sensor (in
  the thermostat's area, else the living room), price sensors with a forecast, solar/grid/battery/house power of one
  inverter, solar forecasts
- Bug reports: Roost keeps an event log (every thermostat change and why, changes by hand, mode, learning, import,
  repairs, plans it could not make, errors; the last 300, kept over restarts) and its last warnings and errors; the
  diagnostics download now holds those, the versions, the state of every entity Roost reads and the inputs of the
  current plan (to replay it), without the home location. The bug report form explains how to get it
- Comfort settings filled in from the thermostat's last days: the comfort hours, the comfort temperature, the night
  minimum (at most 1.5 °C below comfort: a heat pump does badly with a deep setback)

## v0.4.0 — extra rooms (unreleased)

- Extra rooms the heat pump also heats (radiators upstairs, a bedroom): *Add room* on the integration page, with a
  sensor and a kind (bedroom, kids' room, study, bathroom, other) that sets a minimum and its hours; outside them the
  room may be cool. Roost learns per room how it cools and warms, keeps the minimums in the plan, shows the rooms on the
  card and raises a repair when a room keeps staying too cold
- Needs Home Assistant 2025.3 or newer (rooms are config subentries)

## v0.3.6 — fixed price contracts, comfort suggestions, sun on the facades, internal gains per hour, building register (unreleased)

- Price: dynamic (a price sensor, as before) or a fixed contract: one rate, optionally a low rate with its hours and
  the weekend, optionally a fixed export price (empty = net metering)
- Comfort suggestions: changes made by hand while Roost steers are remembered; when the same kind of change comes back
  on three different days within two weeks, a repair suggests a setting (warmer or cooler in the day, comfort hours
  earlier or later). One click to accept, or ignore it — never changed by itself
- Sun on the facades: the weather now includes direct and diffuse radiation; the house model tries every facade
  direction (east to west, half and fully vertical) next to global radiation and keeps the one that predicts alternate
  weeks best (the author's house: south-east, about 5 % better)
- Internal gains per hour of the day (cooking, people, a thermostat in the sun), at half strength and at most 1 kW,
  kept only when it predicts better
- The weather archive is read again once, for the direct and diffuse radiation
- Optional (off by default, the Netherlands only): building data from the BAG through PDOK, looked up once at the
  home location — construction year and floor area give starting values for the house model, the outside walls
  (walls shared with neighbours left out) limit the facade directions tried. No address is kept; off removes it.
  Not used when the home location is not in or within 25 m of the dwelling; for flats only year and area
- Options: each part saves when it is submitted (the separate *Save* step was easy to miss)
- Weheat import: a status with translated states (done, importing, waiting for the Weheat login, failed)
- Comfort option *Lowest thermostat setting* (default 19 °C): Roost never sets the thermostat lower — also what
  stays on it if Home Assistant is down (it was the night minimum − 1, at most 18)
- Own record of the thermostat's setpoint and reading per hour (120 days), for hours the Weheat logs do not have it
  (an on/off thermostat): the response and the self-check then learn as well
- Repair when changes Roost did not make come back at the same time every day (a schedule in the thermostat, or
  another automation); those changes do not count for comfort suggestions
- Repair when the learned response shows the setpoint hardly moves the heat pump (its own heating curve); not ready
  to steer then
- Setting *Heat emitters* (floor heating, radiators, both): starting values for the house (buffer, delay) and the
  COP, and the wording (the floor, or the house, as the buffer)
- Card: under *Planned* the room temperature expected with it (the planned setpoint is a thermostat setting and
  may be well below the room for a slow unit); clearer reasons: charging the floor, living off the heat in the floor

## v0.2.0 — self-learning: self-check, correction, response to the thermostat, hot water (unreleased)

- Self-check every night: the last 7 days replayed with the setpoints that were really on the thermostat (so it also
  works in shadow mode); the room 1, 6 and 24 hours ahead and the heat and electricity against the meters. New sensor
  *Plan accuracy*; when Roost predicts well enough over enough heating hours and the heat pump follows the thermostat,
  a repair *ready to steer* offers to switch to active (your decision; never automatic)
- Correction from the last hours: when the room got warmer or colder than predicted (sun, visitors, an open window),
  the plan takes that as extra heat, fading out over the coming hours
- The heat pump's response to the thermostat is learned from the Weheat logs (which now include the setpoint and the
  thermostat's own reading per hour). An OpenTherm thermostat modulates: the unit asks for about the house's loss plus
  a gain per degree below the setpoint and follows with a delay (the author's unit: 0.9 × loss + 1 kW per °C, 35 % of
  a change per hour; it kept heating with the room a degree above the setpoint). Also learned: how the thermostat reads
  against the room sensor, the lowest steady output and the COP while cycling below it
- Planner: for a unit that follows slowly, the plan from the search is improved with the real delay (blocks of 1–4
  hours), starting also from a steady thermostat, so it never plans worse than that; the shown plan follows the delay
  from the unit's measured output; "setpoint at most 1 °C above the room" and the steady thermostat to compare with now
  count from what the thermostat reads (the setpoints shown are thermostat settings)
- Hot water: the share of each hour of the week the unit spends on hot water (schedule, legionella) is learned; the
  planner knows no space heating happens then and heats before or after
- Every night the hours since the last Weheat import are read (read-only) before learning; an install imported by an
  older version reads its history again once, for the setpoints
- Card: plan error 6 h and *ready to steer* in the footer

## v0.1.2 — compact card, reasons in your language, prices beyond the forecast (unreleased)

- Card: `compact` option (header and tiles only, for a wall tablet); a `show_…` option set yourself still wins
- Card: the reason and the decision now follow your language (English, Dutch); the planned-setpoint sensor gets
  `reason_code`/`reason_args` and `decision_code`/`decision_args` next to the English text
- Prices: hours the price forecast does not reach yet (tomorrow's day-ahead prices arrive in the afternoon) get the
  price of the same hour a day earlier (remembered, and read from the recorder at start-up) instead of the last known
  price for the whole night
- Card: the bars show the import tariff; hours with a guessed price are faded; sliding over the graph also shows the
  price the planner counts when that differs (the home battery's refill cost, or own solar)
- Weheat lookup uses `DeviceEntry.config_entry_id` where Home Assistant has it (`config_entries` is deprecated)

## v0.1.0 — first version (unreleased)

Roost: smart heating planner for Weheat heat pumps.

- 24-hour plan of thermostat setpoints (dynamic programming over room temperature and the heat stored in the floor),
  planned over 36 hours, renewed every 15 minutes; never more than 1 °C above the room (lukewarm water, high COP)
- Stores heat when an hour is cheap or solar earns little and an expensive one follows; the only setting is how warm
  the house may get while storing
- House model learned every night (heat loss, storage, floor lag, solar gain, wind, internal gains), checked on the
  temperatures and the daily energy balance; adopted only when it predicts better
- Heat pump model: COP against outdoor temperature and output, outdoor-sensor bias, maximum output (Blackbird P80/P60 profiles)
- Import of the heat pump's hourly history from Weheat through the Weheat integration's login (read-only)
- Own energy value per hour: real solar only (export minus battery discharge, at most the solar power), a battery that
  fills anyway, battery refill price, grid price
- Control: shadow / active, at most one change per hour, a change by hand pauses for two hours, never below the minimum
- Saving against a steady thermostat: next 24 hours, yesterday, this month
- Repairs: heat pump not following the thermostat, no room temperature, Weheat sensors missing, learning failed
- Dashboard card with the 24-hour plan, English and Dutch, light and dark theme, visual editor
- Diagnostics download
