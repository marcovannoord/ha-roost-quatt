<p align="center"><img src="assets/icon.png" width="128" alt="Roost logo"></p>
<h1 align="center">Roost for Quatt</h1>

<p align="center"><b>Smart heating planner for Quatt heat pumps.</b><br>
Plans your thermostat 24 hours ahead on price, weather and the heat your house stores, and learns your house by itself.</p>

> **A fork of [Roost](https://github.com/Akashironld/ha-roost) by Akashironld (MIT)**, which does the same for Weheat
> heat pumps. All of the planning, learning, self-checks and the dashboard card are Roost's. This fork swaps the
> Weheat parts for the Quatt ones. Not affiliated with Quatt or Weheat.

<p align="center"><a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=marcovannoord&repository=ha-roost&category=integration"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open in HACS" height="36"></a></p>
>
> **Status: beta.** It starts in **shadow mode**: it shows what it would do and why, without touching your
> thermostat, until you let it steer.

## How it works with a Quatt

The Quatt CIC's local API is read-only, so Roost does not command the heat pump. Instead it does what you would do:
it changes the **target temperature of your OpenTherm thermostat** (for example a Toon, Honeywell or Netatmo connected to
the CIC). The CIC then makes the heat pump follow that demand. Roost plans those setpoints:

- **Charge the house in cheap hours.** When an hour is cheap (or your solar earns little) and an expensive evening
  follows, it raises the setpoint a little; through the expensive hours the house lives off that stored heat. It weighs
  the price difference against the heat that leaks away and the better COP of a warm afternoon.
- **Keep the water lukewarm.** It never asks for much more than the room temperature, so the thermostat keeps asking
  the CIC for low water temperatures and the heat pump keeps a high COP.
- **Learn the house and the heat pump every night**: heat loss, stored heat, the sun on the facade, wind and internal
  gains, plus the Quatt's COP, its response to the thermostat and its lowest output. A new model is used only when
  it predicts better.
- **Start from last winter.** It reads up to a year of hourly history from **Home Assistant's own long-term
  statistics** of the Quatt sensors. Heat comes from the CIC's heat power (flow × ΔT), electricity from the units' power
  input, plus flow temperature, the thermostat's control setpoint and room temperature. No Quatt login is needed and no
  data leaves Home Assistant.
- **Quatt Duo aware.** It sees the second outdoor unit, starts from a Duo profile (about twice the output, and a COP that
  drops less at high output), and takes the house's supply temperature from the second unit's outlet.
- **Everything else from Roost**: built-in day-ahead prices (EPEX) or your own price sensor or fixed tariff, solar and
  home battery, extra rooms, window detection, pause, away, a nightly self-check before it offers to steer, saving
  explained per hour, heating-curve (flow temperature) advice, and a dashboard card with four views.

## Requirements

- Home Assistant 2025.5 or newer, with the recorder.
- The **[Quatt integration](https://github.com/marcoboers/home-assistant-quatt)** (home-assistant-quatt) with the local
  CIC connection. The Remote Mobile API is optional; Roost uses its number of heat pumps when present.
- An **OpenTherm thermostat connected to the Quatt CIC** and exposed in Home Assistant as a `climate` entity whose target
  temperature Home Assistant can set.
- An electricity price: a price sensor with a forecast (Nord Pool, ENTSO-e, Tibber, Frank Energie, …), the built-in
  day-ahead prices, or a fixed tariff.
- Optional: a room temperature sensor, solar and grid power, solar forecast, home battery, window sensors, a notify
  service.

Roost needs the CIC's `qc.supervisoryControlMode`, the heat power and the total power input. These are enabled by
default in the Quatt integration. The longer HA has recorded them, the better the first models are.

## Install

1. HACS → three dots → **Custom repositories** → add this repository as an *Integration*. Download it and restart Home
   Assistant.
2. **Settings → Devices & services → Add integration → Roost for Quatt.** Pick the **Quatt CIC** device and your
   thermostat. Leave "Import the heat pump's history now" on.
3. Check the detected house, price, solar and comfort settings, and submit.
4. Add the **Roost for Quatt** card to a dashboard (it registers itself as `custom:roost-quatt-card`).
5. Leave it in **shadow mode** until it offers to steer (a repair notice and the card say so).

### Before you let it steer

- **Turn off the thermostat's own schedule / program** (on a Toon: set it to manual / hold). Roost plans the whole
  day, and a schedule fighting it makes Roost pause after every change it did not make. Roost detects a recurring
  schedule and tells you.
- Turn off other automations that set the thermostat.
- Quatt's own features that run the heat pump on their own (boost, silent hours) are fine, but Roost learns them as
  part of how the heat pump behaves.

## Differences from Roost (Weheat)

| | Roost (Weheat) | Roost for Quatt |
|---|---|---|
| History | Weheat cloud logs, with its own Weheat login | HA long-term statistics of the Quatt sensors |
| Energy per hour | Weheat's energy meters | the hourly mean of the power sensors |
| Seconds of heating per hour | Weheat logs | estimated from min/mean/max power, then counted live from the CIC state |
| Hot water | modelled | none (a Quatt makes no hot water) |
| Heating curve advice | five points of the Weheat app | five points from −10 to 10 °C, as information for the thermostat's maximum water temperature |
| Hybrid detection | Weheat's boiler type | hours the boiler actually ran (a Duo without its boiler counts as all-electric) |

The planner, models and card behave as in Roost. The upstream user guide still applies where it doesn't mention
Weheat: [docs/GUIDE.md](docs/GUIDE.md), [design](docs/DESIGN.md), and the [upstream README](docs/README-upstream.md).

## Privacy

Roost for Quatt talks to Open-Meteo (weather, your home location), Energy-Charts (built-in day-ahead prices, only the
bidding zone) and, opt-in, PDOK (the Dutch building register, once). The Quatt data never leaves Home Assistant. No
telemetry.

## Credits

[Roost](https://github.com/Akashironld/ha-roost) by Akashironld: the whole planner, models, self-check and card. The
[Quatt integration](https://github.com/marcoboers/home-assistant-quatt) by marcoboers and patrickvorgers, whose entity
keys this fork reads.

MIT licensed, see [LICENSE](LICENSE).
