<p align="center"><img src="assets/icon.png" width="128" alt="Roost logo"></p>
<h1 align="center">Roost</h1>

<p align="center"><b>Smart heating planner for Weheat heat pumps.</b><br>
Plans your thermostat 24 hours ahead on price, weather and the heat your house stores — and learns your house by itself.</p>

<p align="center">
<a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=Akashironld&repository=ha-roost&category=integration"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open in HACS" height="36"></a>
<a href="https://ko-fi.com/akashironl/?hidefeed=true&widget=true&embed=true"><img src="https://storage.ko-fi.com/cdn/kofi2.png?v=3" alt="Buy me a coffee on Ko-fi" height="36"></a>
</p>

> **Status: beta.** Roost starts in **shadow mode**: it shows what it would do and why, without touching your
> thermostat, until you let it steer. Not affiliated with Weheat.
>
> 📖 **New here? Follow the [setup and user guide](docs/GUIDE.md)** — from installing to letting Roost steer, step by step.
> What to expect: [simulations](docs/SIMULATIONS.md).
>
> 🧪 **Testing the beta?** What to expect and what to report: [docs/TESTERS.md](docs/TESTERS.md).

<p align="center"><img src="assets/card-overview.png" width="520" alt="The Roost card: the plan for the next 24 hours, the expected room temperature, the tariff per hour and why"></p>

## What it does

- **Plans instead of reacting.** A 24-hour plan of thermostat settings that holds until something real changes. When an hour is cheap (or your
  solar earns little) and an expensive evening follows, it charges the floor a little; in the expensive hours the house
  lives off that heat. It weighs the price difference against the heat that leaks away and the better COP in the warm
  afternoon.
- **Keeps the water lukewarm.** It never asks for much more than the room temperature, so an OpenTherm thermostat keeps
  asking for low water temperatures and the heat pump keeps a high COP.
- **Learns your house** every night: heat loss, the heat the house stores, how long the floor holds it, the facade the
  sun comes in through, wind, internal gains per hour of the day. A new model is only used when it predicts better.
- **Learns your heat pump**: its COP, how it responds to the thermostat (an OpenTherm thermostat modulates and the heat
  pump follows slowly — Roost plans with that delay), its lowest output, when it makes hot water.
- **Starts from last winter.** It imports the heat pump's hourly history (a year) from Weheat, read-only,
  with its own Weheat login (you log in with your Weheat account in the setup) — so it knows your house from day one.
- **Checks itself.** Every night it replays the last week with the setpoints that were really on the thermostat (in
  mild weather the last heating weeks instead); when it predicts well enough it offers to take over. Between nights it
  corrects from the last hours — what sunny hours miss as extra sun, so a sunny afternoon does not warm the night.
- **Dynamic or fixed price**, solar, home battery (energy from the battery is valued at what refilling it costs), net
  metering or not.
- **Extra rooms**: radiators upstairs or a bedroom get a minimum in their own hours, so Roost never lets the heat pump
  rest longer than they can take.
- **Knows when you air the room.** A fast drop of the room temperature (or a window sensor) means a window is open:
  Roost waits instead of heating the outdoors, and does not learn from it.
- **Respects you.** At most one change an hour, steps aside for two hours when you change the thermostat, never below
  your minimums or its lowest setting, comfort suggestions instead of changing your settings by itself. When it stops
  steering (shadow, off or removed) it puts the thermostat back on your comfort temperature.
- **Away, pause and settings from the card.** Tap the mode label: off / shadow / active, pause two hours, away for a day,
  three days or a week (only a minimum, warm again in time), and every temperature and the comfort hours with − / +.
- **Watches over itself.** A thermostat that cannot be reached or changed, a check that no longer passes while it steers,
  learning that fails, a Weheat login that is needed again: a notice in Repairs and — only if you choose where they go —
  a notification on your phone, plus an optional weekly summary.
- **Shows where the heating electricity came from**: own solar, home battery or grid, per day and per period (hot water
  not counted).
- **Its own dashboard card** with the plan, the expected room temperature, the tariff per hour, **why each hour is what
  it is**, and what it saves; the plan and the last week as a **table**; and a **look back**: what was planned beside
  what happened, how well it predicted, a log of every change and why, and a report to keep.
- **Explains its saving.** Per hour, for yesterday and the next 24 hours, Roost beside the equally comfortable steady
  thermostat it is compared with, and every change of the plan with why (in the report and as `roost.explain_saving`).
  It never changes the thermostat because of a price that is not published yet.
- **Heating curve advice**: the flow temperatures your house needs, as the five points of the Weheat app, from your heat
  loss, your floor or radiators and the heat pump's own logs — beside what the heat pump really made, and for another
  indoor temperature if you like.

## The card

| | |
|:---:|:---:|
| <img src="assets/card-overview.png" width="400" alt="Overview"><br>**Overview** — what Roost does now and why, the plan for the next 24 hours with the tariff, and the next change | <img src="assets/card-table.png" width="400" alt="Table"><br>**Table** — the plan per hour with the reason, and the last 7 days: planned and set, room measured and expected, price, electricity |
| <img src="assets/card-curve.png" width="400" alt="Curve"><br>**Curve** — the heating curve your house needs as the five points of the Weheat app, beside every hour the heat pump ran | <img src="assets/card-lookback.png" width="400" alt="Look back"><br>**Look back** — what was planned beside what happened, how well the room was predicted 6 hours ahead, and a log of every change |

<sub>Overview, table and look back: Roost's own planner and control on two simulated winter days with dynamic prices
(an example, not a promise); the curve: a real house.</sub>

## Quick start

1. **HACS**: click the button below (or HACS → ⋮ → *Custom repositories* → add this repository as an
   *Integration*) → open **Roost** → ⋮ → *Redownload* → turn on **Show beta versions** (the beta versions are
   pre-releases) → download → restart Home Assistant.

   [![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Akashironld&repository=ha-roost&category=integration)
2. **Settings → Devices & services → Add integration → Roost**
   ([![Add the integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=roost)). Pick your Weheat heat pump and thermostat; Roost fills in
   what it finds (room sensor, price sensor, solar and battery, your comfort temperatures) — check it and submit.
3. **Add the card**: edit a dashboard → *Add card* → *Roost*.
4. Watch it in **shadow mode** for some days. *Configure → Mode* shows what its self-check says and when it expects to
   be ready; when it is, the card shows *Let Roost steer* and a notice in **Settings → Repairs** offers it. Turn off any other schedule or automation on the thermostat first.

Everything else — every screen, every setting, the card, repairs, troubleshooting — is in the
**[guide](docs/GUIDE.md)**.

## Requirements

- Home Assistant **2025.3** or newer, with the recorder.
- A **Weheat** heat pump with the official Weheat integration.
- The **thermostat** that drives it, as a `climate` entity in Home Assistant (OpenTherm best; on/off works). The heat
  pump must follow the thermostat, not only its own heating curve — Roost checks this.
- An **electricity price**: a sensor with the prices of the coming hours (evcc, Nord Pool, Tibber, ENTSO-e, Frank
  Energie, Zonneplan, … are read automatically) — or, without one, the **built-in day-ahead prices** with your
  supplier's formula — or your fixed contract's rate.
- Optional: a room sensor, solar and battery sensors (the house's use is worked out from grid + solar when there is no
  house power sensor), solar forecast, extra room sensors, window sensors, a notify service for notifications.

Roost speaks English, Dutch, German and French (the setup, the card and the notices).

## Thermostats and heating

| Setup | How well |
|---|---|
| OpenTherm thermostat (Lyric T6, Nest, Tado, Remeha, …) | Best: the heat pump's response is learned from the Weheat history, also last winter |
| On/off thermostat, heat pump on its heating curve when asked | Works: Roost records the setpoint itself and learns the response in a few weeks |
| Heat pump only on its own heating curve | Roost cannot steer, and says so — its heating curve advice still helps you set that curve |

Floor heating stores the most heat, so Roost can shift the most; with radiators the house itself is the buffer and the
saving is smaller. A thermostat with its own schedule or learning works against Roost: turn that off (Roost notices it).

## Reporting a problem

**Settings → Devices & services → Roost → ⋮ → Download diagnostics**, then open a
[bug report](https://github.com/Akashironld/ha-roost/issues/new/choose) and drag the file in. It holds Roost's event log
(every thermostat change and why), the plan's inputs and the learned models — no passwords, no home location.

## Privacy

Roost talks to **Open-Meteo** (weather, with your home location), to **Weheat** (read-only, with the Weheat login you make in
the setup, for the history and the installation's settings), with the built-in day-ahead prices to **Energy-Charts** (only
the bidding zone) and — only if you turn it on — once to **PDOK** (Dutch building register). Notifications go only to the
notify service you choose in Home Assistant. Nothing else, no account, no telemetry. Details in the [guide](docs/GUIDE.md#15-privacy-and-safety).

## How it decides

Per quarter of an hour the planner simulates the thermostat and the heat pump's learned response, the heat going into
the floor first and reaching the room with the learned delay, losses to outside with wind, sun on the facade and
internal gains. The cost of an hour is the electricity (heat ÷ COP) times the energy value of that hour, plus comfort
penalties and a small cost per change; extra rooms add their own. A dynamic-programming search over 36 hours finds a
plan, which is then refined with the heat pump's real delay. The plan holds and is made afresh
only for a reason (new prices, the room off the plan, a changed forecast, a change of yours). More in [docs/DESIGN.md](docs/DESIGN.md).

## Credits

Built-in day-ahead prices: [Energy-Charts](https://energy-charts.info) (Fraunhofer ISE), licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Weather: [Open-Meteo](https://open-meteo.com) (CC BY 4.0).

## Support

Issues and ideas: [GitHub issues](https://github.com/Akashironld/ha-roost/issues).

Roost is free and open source. If it saves you some money (or keeps your evening warm for less) and you'd like to say
thanks, you can buy me a coffee ☕ — the button opens the Ko-fi tip panel straight away, no account needed:

<a href="https://ko-fi.com/akashironl/?hidefeed=true&widget=true&embed=true"><img src="https://storage.ko-fi.com/cdn/kofi2.png?v=3" alt="Buy me a coffee on Ko-fi" height="36"></a>

Vind je het handig? Een koffie via [Ko-fi](https://ko-fi.com/akashironl/?hidefeed=true&widget=true&embed=true) wordt zeer gewaardeerd. ☕
