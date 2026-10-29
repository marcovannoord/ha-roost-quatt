# Testing Roost (beta)

Thanks for trying Roost while it is in beta! This page is about testing: what to expect, how to install and update,
and what is useful to report. Every screen, setting and the card are in the [setup and user guide](GUIDE.md).

## What to expect

- **Roost starts in shadow mode.** It plans and shows what it would do and why, but does not touch your thermostat.
  It only steers after its self-check is happy **and you switch it on** (*Configure → Mode*, or the card's
  *Let Roost steer* button). You can switch back to shadow or off at any time.
- **It is a beta.** Expect rough edges: odd plans, unclear texts, a setting that does not fit your home. That is what
  this test is for.

## Install

With [HACS](https://hacs.xyz):

1. **HACS → ⋮ → Custom repositories**: paste `https://github.com/Akashironld/ha-roost`, type **Integration**, **Add**.
2. Search HACS for **Roost** and open it. The beta versions are *pre-releases*, which HACS hides by default: **⋮ →
   Redownload**, turn on **Show beta versions**, pick the newest version → **Download**. Restart Home Assistant.
3. **Settings → Devices & services → Add integration → Roost**, and go on with section 4 of the
   [guide](GUIDE.md#4-add-the-integration-screen-by-screen).
4. After the first setup screen Weheat's login page opens: log in with your Weheat account (nothing else to fill in).
   Roost then imports your heat pump's history from Weheat (read-only); a year takes a few hours in the background.

Without HACS: download **`roost.zip`** from the newest [release](https://github.com/Akashironld/ha-roost/releases),
unzip it into `custom_components/roost` in your Home Assistant configuration folder (so that
`custom_components/roost/manifest.json` exists) and restart.

## Updates

- HACS offers new beta versions by itself (*Settings → Updates*) once *Show beta versions* is on for Roost (also the
  switch *Roost pre-release* on the HACS device). To hear about them on GitHub: on the repository page **Watch →
  Custom → Releases**.
- Without HACS: download the new `roost.zip`, **delete the old files** in `custom_components/roost`, unzip the new ones
  there and restart. Your settings and what Roost learned stay (Home Assistant keeps them, not that folder).
- Updating from 0.5.2: Home Assistant shows *Re-authenticate* at Roost once — click it and log in with your Weheat
  account.
- Updating to 0.6.0: Roost reads the past year of hourly logs from Weheat once more, in the background (about half an
  hour); the heating curve advice appears after that.
- Updating to 0.8.0: savings of the days before the update are no longer counted (they were not checked against what
  was measured), so this month's saving starts again; the next 24 hours' saving is empty in the morning until
  tomorrow's prices are published. The nightly learning refits how the heat pump responds.

## What I would like to hear

- **Problems**: *Issues → New issue → Bug report*. Please attach the **diagnostics file** (*Settings → Devices &
  services → Roost → ⋮ → Download diagnostics*): it holds what Roost learned, its plan and its decisions, without
  passwords or tokens. It saves a lot of back and forth.
- **After a week in shadow mode**: do its plans make sense to you? Would you have done the same? Is anything on the
  card or in the texts unclear?
- **Your setup**: thermostat (OpenTherm or on/off), dynamic or fixed price, solar or battery — it helps to know which
  combinations were tested.
- **The heating curve advice** (*Curve* in the card): does it look right for your house, and what is your curve now?
- **Since 0.8.0**: does the heat pump run in fewer, longer runs (the card shows starts and run length today against
  yesterday)? Does the room stay where you want it? And the days in the savings calendar that are not counted: what
  reason does the card give?

## Stopping

Remove the integration (*Settings → Devices & services → Roost → ⋮ → Delete*), then remove Roost in HACS (or delete
the folder `custom_components/roost`) and restart. If Roost was steering it puts the thermostat back on your comfort
temperature when you remove it; turn your usual schedule back on if you had one.
