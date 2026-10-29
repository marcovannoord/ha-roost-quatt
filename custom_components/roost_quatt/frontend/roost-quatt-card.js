/* Roost card - served by the roost integration. */
(() => {   // own scope: safe if the file is loaded twice as a classic script (legacy frontend + a manual resource)
const CARD_VERSION = "0.8.1";

// Plain ES2017 on purpose (no ?. / ??), ASCII only (\u escapes): wall tablets often run an older browser.
const nn = (a, b) => (a === null || a === undefined ? b : a);
const DEG = "\u00b0C";

const T = {
  en: { title: "Roost", room: "Room", thermostat: "Thermostat", planned: "Planned", next24: "Next 24 hours",
        setpoint: "setpoint", expected: "room expected", price: "tariff", guessed: "estimated", uses: "plan uses", comfort: "comfort hours", now: "now",
        night: "night", saving24: "expected saving", month: "this month", yesterday: "yesterday", vs: "vs steady", accuracy: "plan error 6 h", ready: "ready to steer", min: "min", steer: "Let Roost steer", sure: "Sure? Click again", importing: "Import from the statistics", months: "months", done_at: "done", eta: { import: "after the import", heating: "after more heating hours", heating_season: "in the heating season", check: "maybe at the next check", lever: "not yet (setpoint has no effect)", following: "not yet (heat pump not following)" },
        active: "ACTIVE", shadow: "SHADOW", off: "OFF", paused: "PAUSED", scrub: "slide over the graph",
        stored: "stored", unavailable: "Not available", pick: "Pick the 'Planned setpoint' sensor of the Roost integration.",
        noplan: "no plan yet", heating: "heat pump heating", e_entity: "Sensor", e_title: "Title", e_language: "Language",
        e_time_format: "Time format", e_auto: "Like Home Assistant", e_show_tiles: "Tiles", e_show_chart: "24-hour plan",
        e_show_footer: "Saving", e_show_curve: "Heating curve advice", e_compact: "Compact (e.g. a wall tablet)", e_history: "Look back (button)", e_view: "Opens in",
        v_plan: "Overview", v_history: "Look back", tab_curve: "Curve", v_curve: "Heating curve advice", go_integration: "Open Roost in Settings", tab_table: "Table", t_time: "Time", t_why: "Why", t_back7: "Last 7 days", t_today: "Today", t_exp: "exp.", t_set: "Setting", t_room: "Room", mo_off: "Off", mo_shadow: "Shadow", mo_active: "Active", mh_off: "Roost does nothing", mh_shadow: "Roost plans, the thermostat is left alone", mh_active: "Roost sets the thermostat", mo_resume: "Resume now", mo_sure: "Sure? Tap again", v_table: "Table", set_btn: "Settings", s_comfort: "Comfort (day)", s_day_min: "Minimum by day", s_night_min: "Minimum at night", s_hours: "Comfort hours", s_lowest: "Lowest setpoint", s_store: "Store heat up to", mo_away: "Away", away_1: "1 day", away_3: "3 days", away_7: "1 week", mh_away: "only the minimum ({min} \u00b0C), warm again on time", mo_home: "Home again", mh_home: "the comfort hours count again", st_away: "AWAY", comfort_lbl: "Comfort", src_title: "Heating electricity", src_sun: "solar", src_bat: "battery", src_grid: "grid", t_loss_store: "{h} hours labelled as heat storage; highest measured room {max} \u00b0C. This does not establish which hours were unnecessary.", t_loss_other: "The model estimate is negative; its cause has not been established.", next_at: "at {t} \u2192 {sp}", mo_pause: "Pause 2 h", mh_pause: "Roost leaves the thermostat alone for 2 hours", warn_notready: "Roost steers with the model it had: the check of the house model has not passed (yet).",
        ahead: "Overview", back: "Look back", h_cost: "Cost", h_saving: "Estimated saving", h_pred: "Forecast 6 h", h_largest: "largest",
        h_below: "Below comfort", h_lowest: "lowest", h_changes: "Changes", h_byhand: "by hand", h_byroost: "Roost",
        h_log: "Log", h_report: "Report", h_loading: "Loading the last days\u2026",
        h_nodata: "No history yet: Roost keeps every hour from now on.", h_sp_t: "thermostat setpoint", h_sp_p: "planned",
        h_room: "room measured", h_pred6: "room predicted 6 h before", h_heat: "heat kWh", h_pause: "pause",
        h_expected: "expected", h_dev: "deviation", h_room_after: "room", h_set_hand: "by hand, Roost pauses {h} h",
        h_pause_ev: "paused {h} h", h_resume: "resumed", h_mode: "mode", h_learned: "learned the house again",
        h_window: "window open", h_window_end: "window closed, room back", h_win_mark: "W", h_period: "Period", h_day: "Day", h_kwh: "kWh", h_cop: "COP", h_deficit: "\u00b0C\u00b7h below",
        p_title: "The saving in parts", p_less: "Less electricity (waiting for the sun, no overheating, warmer hours)", p_sun: "of which in hours with sun", p_cheap: "Heating in cheaper hours", p_end: "Heat left at the end", r_sav: "Hourly model comparison with a weather-adjusted comfort reference", r_yday: "Yesterday", r_next: "Next 24 hours (plan)", r_hour: "Hour", r_out: "Outdoor", r_roost: "Roost", r_steady: "Comfort reference", r_diff: "Saved", r_sp: "setpoint", r_room: "room", r_cost: "cost", r_sum: "Total", r_end: "What the state at the end still costs (heat short of comfort bought back later, or heat left over)", r_total: "Saving", r_note: "Both costs are simulated with the same house model, weather and prices. The reference changes its setpoint with the weather. Main-room comfort shortfall: Roost {a}, reference {b} degree-hours. See the quality assessment above.", r_uses_note: "\u201cPlan uses\u201d is what Roost counts per kWh from the grid or the home battery in that hour: the tariff, or, while the home battery supplies the house, the price of buying that kWh back later plus battery losses (plus the preference for own energy, if set).", r_none: "Not available yet: a day is replayed after midnight.", r_changes: "Plan changes", r_ch_sp: "Setpoint this hour", r_ch_sav: "Expected saving 24 h", r_nochg: "No changes in this period.", c_prices_published: "new prices published ({n} h)", c_prices_changed: "prices changed ({n} h)", c_forecast: "weather forecast changed", c_room: "room {r} \u00b0C, expected {e} \u00b0C", c_correction: "correction from the last hours changed", c_settings: "settings changed", c_estimated: "estimated prices (not published yet) left out", c_new_hour: "a new hour: the 24 hours moved on", c_other: "recalculated with the latest readings" },
  nl: { title: "Roost", room: "Kamer", thermostat: "Thermostaat", planned: "Gepland", next24: "Komende 24 uur",
        setpoint: "setpoint", expected: "kamer verwacht", price: "tarief", guessed: "geschat", uses: "rekent met", comfort: "comforturen", now: "nu",
        night: "nacht", saving24: "verwachte besparing", month: "deze maand", yesterday: "gisteren", vs: "t.o.v. vast", accuracy: "planfout 6 u", ready: "klaar om te sturen", min: "min", steer: "Laat Roost sturen", sure: "Zeker? Klik nogmaals", importing: "Import uit de statistieken", months: "maanden", done_at: "klaar", eta: { import: "na de import", heating: "na meer stookuren", heating_season: "in het stookseizoen", check: "mogelijk bij de volgende controle", lever: "nog niet (setpoint werkt niet)", following: "nog niet (warmtepomp volgt niet)" },
        active: "ACTIEF", shadow: "MEEKIJKEN", off: "UIT", paused: "GEPAUZEERD", scrub: "schuif over de grafiek",
        stored: "opgeslagen", unavailable: "Niet beschikbaar", pick: "Kies de sensor 'Gepland setpoint' van de integratie Roost.",
        noplan: "nog geen plan", heating: "warmtepomp stookt", e_entity: "Sensor", e_title: "Titel", e_language: "Taal",
        e_time_format: "Tijdnotatie", e_auto: "Zoals Home Assistant", e_show_tiles: "Tegels", e_show_chart: "24-uursplan",
        e_show_footer: "Besparing", e_show_curve: "Stooklijnadvies", e_compact: "Compact (bijv. een wandtablet)", e_history: "Terugblik (knop)", e_view: "Opent in",
        v_plan: "Overzicht", v_history: "Terugblik", tab_curve: "Stooklijn", v_curve: "Stooklijnadvies", go_integration: "Roost openen in Instellingen", tab_table: "Tabel", t_time: "Tijd", t_why: "Waarom", t_back7: "Afgelopen 7 dagen", t_today: "Vandaag", t_exp: "verw.", t_set: "Setpoint", t_room: "Kamer", mo_off: "Uit", mo_shadow: "Meekijken", mo_active: "Actief", mh_off: "Roost doet niets", mh_shadow: "Roost plant, de thermostaat blijft met rust", mh_active: "Roost zet de thermostaat", mo_resume: "Nu hervatten", mo_sure: "Zeker? Tik nogmaals", v_table: "Tabel", set_btn: "Instellingen", s_comfort: "Comfort (overdag)", s_day_min: "Minimum overdag", s_night_min: "Minimum 's nachts", s_hours: "Comforturen", s_lowest: "Laagste setpoint", s_store: "Warmte opslaan tot", mo_away: "Afwezig", away_1: "1 dag", away_3: "3 dagen", away_7: "1 week", mh_away: "alleen het minimum ({min} \u00b0C), op tijd weer warm", mo_home: "Weer thuis", mh_home: "de comforturen tellen weer", st_away: "AFWEZIG", comfort_lbl: "Comfort", src_title: "Stroom voor verwarming", src_sun: "zon", src_bat: "accu", src_grid: "net", t_loss_store: "{h} uur met een voorverwarmingslabel; hoogste gemeten kamer {max} \u00b0C. Dit bepaalt niet welke uren onnodig waren.", t_loss_other: "De modelschatting is negatief; de oorzaak is niet vastgesteld.", next_at: "om {t} \u2192 {sp}", mo_pause: "2 uur pauze", mh_pause: "Roost laat de thermostaat 2 uur met rust", warn_notready: "Roost stuurt met het model dat het had: de controle van het huismodel is (nog) niet geslaagd.",
        ahead: "Overzicht", back: "Terugblik", h_cost: "Kosten", h_saving: "Geschatte besparing", h_pred: "Voorspelling 6 u", h_largest: "grootst",
        h_below: "Onder comfort", h_lowest: "laagst", h_changes: "Wijzigingen", h_byhand: "met de hand", h_byroost: "Roost",
        h_log: "Logboek", h_report: "Rapport", h_loading: "De laatste dagen laden\u2026",
        h_nodata: "Nog geen geschiedenis: Roost bewaart vanaf nu elk uur.", h_sp_t: "setpoint thermostaat", h_sp_p: "gepland",
        h_room: "kamer gemeten", h_pred6: "kamer voorspeld 6 u eerder", h_heat: "warmte kWh", h_pause: "pauze",
        h_expected: "verw.", h_dev: "afwijking", h_room_after: "kamer", h_set_hand: "met de hand, Roost pauzeert {h} u",
        h_pause_ev: "gepauzeerd {h} u", h_resume: "hervat", h_mode: "modus", h_learned: "huis opnieuw geleerd",
        h_window: "raam open", h_window_end: "raam dicht, kamer terug", h_win_mark: "R", h_period: "Periode", h_day: "Dag", h_kwh: "kWh", h_cop: "COP", h_deficit: "\u00b0C\u00b7u onder",
        p_title: "De besparing in delen", p_less: "Minder stroom (wachten op de zon, niet te warm, warmere uren)", p_sun: "waarvan in uren met zon", p_cheap: "Stoken in goedkopere uren", p_end: "Warmte over aan het eind", r_sav: "Modelvergelijking per uur met een weersafhankelijke comfortreferentie", r_yday: "Gisteren", r_next: "Komende 24 uur (plan)", r_hour: "Uur", r_out: "Buiten", r_roost: "Roost", r_steady: "Comfortreferentie", r_diff: "Bespaard", r_sp: "setpoint", r_room: "kamer", r_cost: "kosten", r_sum: "Totaal", r_end: "Wat de stand aan het eind nog kost (warmte onder comfort later terugkopen, of warmte over)", r_total: "Besparing", r_note: "Beide kosten zijn gesimuleerd met hetzelfde huismodel, weer en dezelfde prijzen. De referentie past haar setpoint aan het weer aan. Comforttekort hoofdruimte: Roost {a}, referentie {b} graaduren. Zie de kwaliteitsbeoordeling hierboven.", r_uses_note: "\u201cRekent met\u201d is wat Roost per kWh uit het net of de thuisaccu telt in dat uur: het tarief, of, zolang de thuisaccu het huis voedt, de prijs om die kWh later terug te kopen plus accuverlies (plus de voorkeur voor eigen energie, als ingesteld).", r_none: "Nog niet beschikbaar: een dag wordt na middernacht nagespeeld.", r_changes: "Planwijzigingen", r_ch_sp: "Setpoint dit uur", r_ch_sav: "Verwachte besparing 24 u", r_nochg: "Geen wijzigingen in deze periode.", c_prices_published: "nieuwe prijzen gepubliceerd ({n} u)", c_prices_changed: "prijzen gewijzigd ({n} u)", c_forecast: "weersverwachting gewijzigd", c_room: "kamer {r} \u00b0C, verwacht {e} \u00b0C", c_correction: "correctie uit de laatste uren gewijzigd", c_settings: "instellingen gewijzigd", c_estimated: "geschatte prijzen (nog niet gepubliceerd) buiten beschouwing", c_new_hour: "nieuw uur: de 24 uur schuiven door", c_other: "opnieuw berekend met de laatste metingen" },
  de: { title: "Roost", room: "Raum", thermostat: "Thermostat", planned: "Geplant", next24: "N\u00e4chste 24 Stunden",
        setpoint: "Sollwert", expected: "Raum erwartet", price: "Tarif", guessed: "gesch\u00e4tzt", uses: "Plan rechnet mit", comfort: "Komfortstunden", now: "jetzt",
        night: "Nacht", saving24: "erwartete Ersparnis", month: "diesen Monat", yesterday: "gestern", vs: "gg\u00fc. konstant", accuracy: "Planfehler 6 h", ready: "bereit zum Steuern", min: "Min", steer: "Roost steuern lassen", sure: "Sicher? Nochmal klicken", importing: "Import aus den Statistiken", months: "Monate", done_at: "fertig", eta: { import: "nach dem Import", heating: "nach mehr Heizstunden", heating_season: "in der Heizsaison", check: "vielleicht bei der n\u00e4chsten Pr\u00fcfung", lever: "noch nicht (Sollwert wirkt nicht)", following: "noch nicht (W\u00e4rmepumpe folgt nicht)" },
        active: "AKTIV", shadow: "MITLESEN", off: "AUS", paused: "PAUSIERT", scrub: "\u00fcber die Grafik streichen",
        stored: "gespeichert", unavailable: "Nicht verf\u00fcgbar", pick: "W\u00e4hle den Sensor 'Geplanter Sollwert' der Roost-Integration.",
        noplan: "noch kein Plan", heating: "W\u00e4rmepumpe heizt", e_entity: "Sensor", e_title: "Titel", e_language: "Sprache",
        e_time_format: "Zeitformat", e_auto: "Wie Home Assistant", e_show_tiles: "Kacheln", e_show_chart: "24-Stunden-Plan",
        e_show_footer: "Ersparnis", e_show_curve: "Heizkurven-Empfehlung", e_compact: "Kompakt (z. B. ein Wandtablet)", e_history: "R\u00fcckblick (Schalter)", e_view: "\u00d6ffnet in",
        v_plan: "\u00dcbersicht", v_history: "R\u00fcckblick", tab_curve: "Kurve", v_curve: "Heizkurven-Empfehlung", go_integration: "Roost in den Einstellungen \u00f6ffnen", tab_table: "Tabelle", t_time: "Zeit", t_why: "Warum", t_back7: "Letzte 7 Tage", t_today: "Heute", t_exp: "erw.", t_set: "Sollwert", t_room: "Raum", mo_off: "Aus", mo_shadow: "Mitschauen", mo_active: "Aktiv", mh_off: "Roost tut nichts", mh_shadow: "Roost plant, das Thermostat bleibt unber\u00fchrt", mh_active: "Roost stellt das Thermostat", mo_resume: "Jetzt fortsetzen", mo_sure: "Sicher? Nochmals tippen", v_table: "Tabelle", set_btn: "Einstellungen", s_comfort: "Komfort (tags\u00fcber)", s_day_min: "Minimum tags\u00fcber", s_night_min: "Minimum nachts", s_hours: "Komfortstunden", s_lowest: "Niedrigster Sollwert", s_store: "W\u00e4rme speichern bis", mo_away: "Abwesend", away_1: "1 Tag", away_3: "3 Tage", away_7: "1 Woche", mh_away: "nur das Minimum ({min} \u00b0C), rechtzeitig wieder warm", mo_home: "Wieder zu Hause", mh_home: "die Komfortstunden z\u00e4hlen wieder", st_away: "ABWESEND", comfort_lbl: "Komfort", src_title: "Heizstrom", src_sun: "Sonne", src_bat: "Akku", src_grid: "Netz", t_loss_store: "{h} Stunden als W\u00e4rmespeicherung markiert; h\u00f6chste Raumtemperatur {max} \u00b0C. Daraus folgt nicht, welche Stunden unn\u00f6tig waren.", t_loss_other: "Die Modellsch\u00e4tzung ist negativ; die Ursache ist nicht ermittelt.", next_at: "um {t} \u2192 {sp}", mo_pause: "2 Std. Pause", mh_pause: "Roost l\u00e4sst das Thermostat 2 Stunden in Ruhe", warn_notready: "Roost steuert mit dem bisherigen Modell: die Pr\u00fcfung des Hausmodells ist (noch) nicht bestanden.",
        ahead: "\u00dcbersicht", back: "R\u00fcckblick", h_cost: "Kosten", h_saving: "Gesch\u00e4tzte Ersparnis", h_pred: "Vorhersage 6 h", h_largest: "gr\u00f6\u00dfte",
        h_below: "Unter Komfort", h_lowest: "niedrigste", h_changes: "\u00c4nderungen", h_byhand: "von Hand", h_byroost: "Roost",
        h_log: "Protokoll", h_report: "Bericht", h_loading: "Die letzten Tage werden geladen\u2026",
        h_nodata: "Noch kein Verlauf: Roost speichert ab jetzt jede Stunde.", h_sp_t: "Sollwert Thermostat", h_sp_p: "geplant",
        h_room: "Raum gemessen", h_pred6: "Raum 6 h vorher vorhergesagt", h_heat: "W\u00e4rme kWh", h_pause: "Pause",
        h_expected: "erw.", h_dev: "Abweichung", h_room_after: "Raum", h_set_hand: "von Hand, Roost pausiert {h} h",
        h_pause_ev: "pausiert {h} h", h_resume: "fortgesetzt", h_mode: "Modus", h_learned: "Haus neu gelernt",
        h_window: "Fenster offen", h_window_end: "Fenster zu, Raum zur\u00fcck", h_win_mark: "F", h_period: "Zeitraum", h_day: "Tag", h_kwh: "kWh", h_cop: "COP", h_deficit: "\u00b0C\u00b7h darunter",
        p_title: "Die Ersparnis in Teilen", p_less: "Weniger Strom (auf die Sonne warten, nicht \u00fcberheizen, w\u00e4rmere Stunden)", p_sun: "davon in Stunden mit Sonne", p_cheap: "Heizen in g\u00fcnstigeren Stunden", p_end: "W\u00e4rme \u00fcbrig am Ende", r_sav: "St\u00fcndlicher Modellvergleich mit einer wetterabh\u00e4ngigen Komfortreferenz", r_yday: "Gestern", r_next: "N\u00e4chste 24 Stunden (Plan)", r_hour: "Stunde", r_out: "Au\u00dfen", r_roost: "Roost", r_steady: "Komfortreferenz", r_diff: "Gespart", r_sp: "Sollwert", r_room: "Raum", r_cost: "Kosten", r_sum: "Summe", r_end: "Was der Zustand am Ende noch kostet (W\u00e4rme unter Komfort sp\u00e4ter nachkaufen, oder \u00fcbrige W\u00e4rme)", r_total: "Ersparnis", r_note: "Beide Kosten sind mit demselben Modell, Wetter und Preisen simuliert. Die Referenz passt den Sollwert dem Wetter an. Komfortdefizit im Hauptraum: Roost {a}, Referenz {b} Gradstunden. Siehe Qualit\u00e4tsbewertung oben.", r_uses_note: "\u201ePlan rechnet mit\u201c ist, was Roost pro kWh aus dem Netz oder dem Hausspeicher in dieser Stunde ansetzt: den Tarif oder, solange der Hausspeicher das Haus versorgt, den Preis, diese kWh sp\u00e4ter nachzukaufen, plus Speicherverluste (plus den Vorzug f\u00fcr eigene Energie, falls eingestellt).", r_none: "Noch nicht verf\u00fcgbar: ein Tag wird nach Mitternacht nachgespielt.", r_changes: "Plan\u00e4nderungen", r_ch_sp: "Sollwert diese Stunde", r_ch_sav: "Erwartete Ersparnis 24 h", r_nochg: "Keine \u00c4nderungen in diesem Zeitraum.", c_prices_published: "neue Preise ver\u00f6ffentlicht ({n} h)", c_prices_changed: "Preise ge\u00e4ndert ({n} h)", c_forecast: "Wettervorhersage ge\u00e4ndert", c_room: "Raum {r} \u00b0C, erwartet {e} \u00b0C", c_correction: "Korrektur aus den letzten Stunden ge\u00e4ndert", c_settings: "Einstellungen ge\u00e4ndert", c_estimated: "gesch\u00e4tzte Preise (noch nicht ver\u00f6ffentlicht) au\u00dfer Acht gelassen", c_new_hour: "neue Stunde: die 24 Stunden r\u00fccken weiter", c_other: "neu berechnet mit den letzten Messwerten" },
  fr: { title: "Roost", room: "Pi\u00e8ce", thermostat: "Thermostat", planned: "Pr\u00e9vu", next24: "24 prochaines heures",
        setpoint: "consigne", expected: "pi\u00e8ce pr\u00e9vue", price: "tarif", guessed: "estim\u00e9", uses: "le plan compte", comfort: "heures de confort", now: "maint.",
        night: "nuit", saving24: "\u00e9conomie pr\u00e9vue", month: "ce mois-ci", yesterday: "hier", vs: "vs constant", accuracy: "erreur du plan 6 h", ready: "pr\u00eat \u00e0 piloter", min: "min", steer: "Laisser Roost piloter", sure: "S\u00fbr ? Cliquez encore", importing: "Import des statistiques", months: "mois", done_at: "fini", eta: { import: "apr\u00e8s l'import", heating: "apr\u00e8s plus d'heures de chauffe", heating_season: "pendant la saison de chauffe", check: "peut-\u00eatre au prochain contr\u00f4le", lever: "pas encore (la consigne n'a pas d'effet)", following: "pas encore (la pompe ne suit pas)" },
        active: "ACTIF", shadow: "OBSERVATION", off: "ARR\u00caT", paused: "EN PAUSE", scrub: "glissez sur le graphique",
        stored: "stock\u00e9", unavailable: "Indisponible", pick: "Choisissez le capteur 'Consigne pr\u00e9vue' de l'int\u00e9gration Roost.",
        noplan: "pas encore de plan", heating: "la pompe chauffe", e_entity: "Capteur", e_title: "Titre", e_language: "Langue",
        e_time_format: "Format de l'heure", e_auto: "Comme Home Assistant", e_show_tiles: "Tuiles", e_show_chart: "Plan sur 24 heures",
        e_show_footer: "\u00c9conomie", e_show_curve: "Conseil de courbe de chauffe", e_compact: "Compact (p. ex. une tablette murale)", e_history: "R\u00e9trospective (bouton)", e_view: "S'ouvre sur",
        v_plan: "Aper\u00e7u", v_history: "R\u00e9trospective", tab_curve: "Courbe", v_curve: "Conseil de courbe", go_integration: "Ouvrir Roost dans les param\u00e8tres", tab_table: "Tableau", t_time: "Heure", t_why: "Pourquoi", t_back7: "7 derniers jours", t_today: "Aujourd'hui", t_exp: "pr\u00e9vu", t_set: "Consigne", t_room: "Pi\u00e8ce", mo_off: "Arr\u00eat", mo_shadow: "Observation", mo_active: "Actif", mh_off: "Roost ne fait rien", mh_shadow: "Roost planifie, le thermostat n'est pas touch\u00e9", mh_active: "Roost r\u00e8gle le thermostat", mo_resume: "Reprendre maintenant", mo_sure: "S\u00fbr ? Touchez encore", v_table: "Tableau", set_btn: "R\u00e9glages", s_comfort: "Confort (jour)", s_day_min: "Minimum le jour", s_night_min: "Minimum la nuit", s_hours: "Heures de confort", s_lowest: "Consigne la plus basse", s_store: "Stocker la chaleur jusqu'\u00e0", mo_away: "Absent", away_1: "1 jour", away_3: "3 jours", away_7: "1 semaine", mh_away: "seulement le minimum ({min} \u00b0C), de nouveau chaud \u00e0 temps", mo_home: "De retour", mh_home: "les heures de confort comptent de nouveau", st_away: "ABSENT", comfort_lbl: "Confort", src_title: "\u00c9lectricit\u00e9 de chauffage", src_sun: "solaire", src_bat: "batterie", src_grid: "r\u00e9seau", t_loss_store: "{h} heures marqu\u00e9es comme stockage ; maximum mesur\u00e9 {max} \u00b0C. Cela ne prouve pas quelles heures \u00e9taient inutiles.", t_loss_other: "L'estimation du mod\u00e8le est n\u00e9gative ; la cause n'est pas \u00e9tablie.", next_at: "\u00e0 {t} \u2192 {sp}", mo_pause: "Pause 2 h", mh_pause: "Roost laisse le thermostat tranquille 2 heures", warn_notready: "Roost pilote avec le mod\u00e8le qu'il avait : la v\u00e9rification du mod\u00e8le de la maison n'est pas (encore) r\u00e9ussie.",
        ahead: "Aper\u00e7u", back: "R\u00e9trospective", h_cost: "Co\u00fbt", h_saving: "\u00c9conomie estim\u00e9e", h_pred: "Pr\u00e9vision 6 h", h_largest: "max.",
        h_below: "Sous le confort", h_lowest: "minimum", h_changes: "Changements", h_byhand: "\u00e0 la main", h_byroost: "Roost",
        h_log: "Journal", h_report: "Rapport", h_loading: "Chargement des derniers jours\u2026",
        h_nodata: "Pas encore d'historique : Roost garde chaque heure \u00e0 partir de maintenant.", h_sp_t: "consigne thermostat", h_sp_p: "pr\u00e9vue",
        h_room: "pi\u00e8ce mesur\u00e9e", h_pred6: "pi\u00e8ce pr\u00e9vue 6 h avant", h_heat: "chaleur kWh", h_pause: "pause",
        h_expected: "pr\u00e9vu", h_dev: "\u00e9cart", h_room_after: "pi\u00e8ce", h_set_hand: "\u00e0 la main, Roost en pause {h} h",
        h_pause_ev: "en pause {h} h", h_resume: "reprise", h_mode: "mode", h_learned: "maison r\u00e9apprise",
        h_window: "fen\u00eatre ouverte", h_window_end: "fen\u00eatre ferm\u00e9e, pi\u00e8ce revenue", h_win_mark: "F", h_period: "P\u00e9riode", h_day: "Jour", h_kwh: "kWh", h_cop: "COP", h_deficit: "\u00b0C\u00b7h en dessous",
        p_title: "L'\u00e9conomie en parts", p_less: "Moins d'\u00e9lectricit\u00e9 (attendre le soleil, pas de surchauffe, heures plus douces)", p_sun: "dont dans les heures de soleil", p_cheap: "Chauffer aux heures moins ch\u00e8res", p_end: "Chaleur restante \u00e0 la fin", r_sav: "Comparaison horaire du mod\u00e8le avec une r\u00e9f\u00e9rence de confort selon la m\u00e9t\u00e9o", r_yday: "Hier", r_next: "Prochaines 24 heures (plan)", r_hour: "Heure", r_out: "Ext\u00e9rieur", r_roost: "Roost", r_steady: "R\u00e9f\u00e9rence de confort", r_diff: "\u00c9conomis\u00e9", r_sp: "consigne", r_room: "pi\u00e8ce", r_cost: "co\u00fbt", r_sum: "Total", r_end: "Ce que l'\u00e9tat final co\u00fbte encore (chaleur sous le confort rachet\u00e9e plus tard, ou chaleur en trop)", r_total: "\u00c9conomie", r_note: "Les deux co\u00fbts sont simul\u00e9s avec les m\u00eames mod\u00e8le, m\u00e9t\u00e9o et prix. La r\u00e9f\u00e9rence adapte sa consigne \u00e0 la m\u00e9t\u00e9o. D\u00e9ficit de confort principal : Roost {a}, r\u00e9f\u00e9rence {b} degr\u00e9s-heures. Voir la qualit\u00e9 ci-dessus.", r_uses_note: "\u00ab\u00a0Le plan compte\u00a0\u00bb est ce que Roost compte par kWh du r\u00e9seau ou de la batterie domestique dans cette heure\u00a0: le tarif ou, tant que la batterie alimente la maison, le prix pour racheter ce kWh plus tard, pertes de la batterie comprises (plus la pr\u00e9f\u00e9rence pour l'\u00e9nergie propre, si r\u00e9gl\u00e9e).", r_none: "Pas encore disponible : une journ\u00e9e est rejou\u00e9e apr\u00e8s minuit.", r_changes: "Changements du plan", r_ch_sp: "Consigne cette heure", r_ch_sav: "\u00c9conomie pr\u00e9vue 24 h", r_nochg: "Aucun changement sur cette p\u00e9riode.", c_prices_published: "nouveaux prix publi\u00e9s ({n} h)", c_prices_changed: "prix modifi\u00e9s ({n} h)", c_forecast: "pr\u00e9visions m\u00e9t\u00e9o modifi\u00e9es", c_room: "pi\u00e8ce {r} \u00b0C, attendu {e} \u00b0C", c_correction: "correction des derni\u00e8res heures modifi\u00e9e", c_settings: "r\u00e9glages modifi\u00e9s", c_estimated: "prix estim\u00e9s (pas encore publi\u00e9s) laiss\u00e9s de c\u00f4t\u00e9", c_new_hour: "nouvelle heure : les 24 heures avancent", c_other: "recalcul\u00e9 avec les derni\u00e8res mesures" },
};

for (const [lang, words] of Object.entries({"en": {"s_weekly": "Weekly schedule active", "s_weekly_edit": "Edit weekly comfort periods"}, "nl": {"s_weekly": "Weekplanning actief", "s_weekly_edit": "Comforttijden per weekdag instellen"}, "de": {"s_weekly": "Wochenplan aktiv", "s_weekly_edit": "Komfortzeiten je Wochentag bearbeiten"}, "fr": {"s_weekly": "Planning hebdomadaire actif", "s_weekly_edit": "Modifier les heures par jour"}})) Object.assign(T[lang], words);

for (const [lang, words] of Object.entries({"en": {"e_show_status": "Status line", "e_show_pumps": "Heat pump runs", "cal_hint": "Since v0.8.0 a day only counts once it is checked against the measurements; the first complete day counts after midnight.", "st_held": "Plan held since {t}", "st_next": "next change {t} \u2192 {sp}", "st_nochange": "no change in the coming hours", "st_prices": "prices until {t}", "fb_no_price": "fallback: no price", "fb_schedule": "fallback: comfort schedule", "pump_on": "heat pump heating", "pr_starts": "Heat pump starts today", "pr_yday": "yesterday {n}", "pr_run": "Mean run today", "pr_was": "yesterday {m}", "pr_month": "Saving this month", "pr_days": "{n} of {m} days", "pr_sun": "own solar", "w_title": "Comfort per weekday", "w_on": "Per weekday", "w_off": "Same every day", "w_add": "+ period", "w_del": "Remove", "w_copy_wd": "Copy to weekdays", "w_copy_we": "Copy to weekend", "w_copy_all": "Copy to all days", "w_save": "Save", "w_saved": "Saved", "w_err": "Not saved: {e}", "w_empty": "no comfort hours", "w_tap": "Tap a day to change its periods", "w_days": "Mo,Tu,We,Th,Fr,Sa,Su", "cal_title": "Saving per day this month", "cal_ok": "counted", "cal_bad": "not counted", "cal_none": "no data", "why_first": "first plan", "why_forced": "planned again", "why_prices": "new prices", "why_room": "room off the plan", "why_weather": "weather changed", "why_sun": "sun changed", "why_solar": "solar changed", "why_age": "plan refreshed", "why_horizon": "plan ran out", "why_window": "window closed", "why_fallback": "fallback"}, "nl": {"e_show_status": "Statusbalk", "e_show_pumps": "Pompruns", "cal_hint": "Sinds v0.8.0 telt een dag pas als hij tegen de metingen is gecontroleerd; de eerste volledige dag telt na middernacht.", "st_held": "Vast plan sinds {t}", "st_next": "volgende wijziging {t} \u2192 {sp}", "st_nochange": "geen wijziging de komende uren", "st_prices": "prijzen tot {t}", "fb_no_price": "terugval: geen prijs", "fb_schedule": "terugval: comfortschema", "pump_on": "warmtepomp stookt", "pr_starts": "Pompstarts vandaag", "pr_yday": "gisteren {n}", "pr_run": "Gem. looptijd vandaag", "pr_was": "gisteren {m}", "pr_month": "Besparing deze maand", "pr_days": "{n} van {m} dagen", "pr_sun": "eigen zon", "w_title": "Comfort per weekdag", "w_on": "Per weekdag", "w_off": "Elke dag gelijk", "w_add": "+ periode", "w_del": "Verwijderen", "w_copy_wd": "Kopieer naar werkdagen", "w_copy_we": "Kopieer naar weekend", "w_copy_all": "Kopieer naar alle dagen", "w_save": "Opslaan", "w_saved": "Opgeslagen", "w_err": "Niet opgeslagen: {e}", "w_empty": "geen comforturen", "w_tap": "Tik op een dag om de perioden te wijzigen", "w_days": "ma,di,wo,do,vr,za,zo", "cal_title": "Besparing per dag deze maand", "cal_ok": "geteld", "cal_bad": "niet geteld", "cal_none": "geen gegevens", "why_first": "eerste plan", "why_forced": "opnieuw gepland", "why_prices": "nieuwe prijzen", "why_room": "kamer week af", "why_weather": "weer veranderd", "why_sun": "zon veranderd", "why_solar": "zonnestroom veranderd", "why_age": "plan ververst", "why_horizon": "plan liep af", "why_window": "raam dicht", "why_fallback": "terugval"}, "de": {"e_show_status": "Statuszeile", "e_show_pumps": "Pumpenl\u00e4ufe", "cal_hint": "Seit v0.8.0 z\u00e4hlt ein Tag erst, wenn er mit den Messungen gepr\u00fcft ist; der erste vollst\u00e4ndige Tag z\u00e4hlt nach Mitternacht.", "st_held": "Plan fest seit {t}", "st_next": "n\u00e4chste \u00c4nderung {t} \u2192 {sp}", "st_nochange": "keine \u00c4nderung in den n\u00e4chsten Stunden", "st_prices": "Preise bis {t}", "fb_no_price": "Ersatz: kein Preis", "fb_schedule": "Ersatz: Komfortplan", "pump_on": "W\u00e4rmepumpe heizt", "pr_starts": "Pumpenstarts heute", "pr_yday": "gestern {n}", "pr_run": "Mittlere Laufzeit heute", "pr_was": "gestern {m}", "pr_month": "Ersparnis diesen Monat", "pr_days": "{n} von {m} Tagen", "pr_sun": "eigene Sonne", "w_title": "Komfort je Wochentag", "w_on": "Je Wochentag", "w_off": "Jeden Tag gleich", "w_add": "+ Zeitraum", "w_del": "Entfernen", "w_copy_wd": "Auf Werktage kopieren", "w_copy_we": "Aufs Wochenende kopieren", "w_copy_all": "Auf alle Tage kopieren", "w_save": "Speichern", "w_saved": "Gespeichert", "w_err": "Nicht gespeichert: {e}", "w_empty": "keine Komfortzeiten", "w_tap": "Tippe auf einen Tag, um seine Zeitr\u00e4ume zu \u00e4ndern", "w_days": "Mo,Di,Mi,Do,Fr,Sa,So", "cal_title": "Ersparnis je Tag diesen Monat", "cal_ok": "gez\u00e4hlt", "cal_bad": "nicht gez\u00e4hlt", "cal_none": "keine Daten", "why_first": "erster Plan", "why_forced": "neu geplant", "why_prices": "neue Preise", "why_room": "Raum wich ab", "why_weather": "Wetter ge\u00e4ndert", "why_sun": "Sonne ge\u00e4ndert", "why_solar": "Solarstrom ge\u00e4ndert", "why_age": "Plan erneuert", "why_horizon": "Plan lief aus", "why_window": "Fenster zu", "why_fallback": "Ersatz"}, "fr": {"e_show_status": "Ligne d'\u00e9tat", "e_show_pumps": "Cycles de la pompe", "cal_hint": "Depuis la v0.8.0 un jour ne compte qu'une fois v\u00e9rifi\u00e9 avec les mesures ; le premier jour complet compte apr\u00e8s minuit.", "st_held": "Plan fixe depuis {t}", "st_next": "prochain changement {t} \u2192 {sp}", "st_nochange": "aucun changement dans les prochaines heures", "st_prices": "prix jusqu'\u00e0 {t}", "fb_no_price": "secours : pas de prix", "fb_schedule": "secours : programme de confort", "pump_on": "la pompe \u00e0 chaleur chauffe", "pr_starts": "D\u00e9marrages aujourd'hui", "pr_yday": "hier {n}", "pr_run": "Dur\u00e9e moyenne aujourd'hui", "pr_was": "hier {m}", "pr_month": "\u00c9conomie ce mois", "pr_days": "{n} sur {m} jours", "pr_sun": "solaire", "w_title": "Confort par jour", "w_on": "Par jour", "w_off": "Chaque jour pareil", "w_add": "+ p\u00e9riode", "w_del": "Supprimer", "w_copy_wd": "Copier vers la semaine", "w_copy_we": "Copier vers le week-end", "w_copy_all": "Copier vers tous les jours", "w_save": "Enregistrer", "w_saved": "Enregistr\u00e9", "w_err": "Non enregistr\u00e9 : {e}", "w_empty": "pas d'heures de confort", "w_tap": "Touchez un jour pour modifier ses p\u00e9riodes", "w_days": "lu,ma,me,je,ve,sa,di", "cal_title": "\u00c9conomie par jour ce mois", "cal_ok": "compt\u00e9", "cal_bad": "non compt\u00e9", "cal_none": "pas de donn\u00e9es", "why_first": "premier plan", "why_forced": "replanifi\u00e9", "why_prices": "nouveaux prix", "why_room": "pi\u00e8ce \u00e9cart\u00e9e", "why_weather": "m\u00e9t\u00e9o chang\u00e9e", "why_sun": "soleil chang\u00e9", "why_solar": "solaire chang\u00e9", "why_age": "plan renouvel\u00e9", "why_horizon": "plan \u00e9puis\u00e9", "why_window": "fen\u00eatre ferm\u00e9e", "why_fallback": "secours"}})) Object.assign(T[lang], words);

// Why Roost plans or does something: the integration sends a code with values (reason_code/_args,
// decision_code/_args); the card words it. Unknown codes fall back to the English text of the integration.
const WHY = {
  en: { starting: "starting", window_open: "window open: Roost waits until the room is back", no_price: "no price", no_room: "no room temperature",
        no_weather: "no weather forecast and no outdoor temperature", no_plan: "no plan", off: "Roost is off",
        store_solar: "charging the floor on own solar (up to {sp} \u00b0C)",
        store_cheap: "charging the floor now ({ct} ct) before more expensive hours",
        expensive: "expensive hour ({ct} ct): living off the heat in the floor",
        store_solar_house: "storing heat in the house on own solar (up to {sp} \u00b0C)",
        store_cheap_house: "storing heat in the house now ({ct} ct) before more expensive hours",
        expensive_house: "expensive hour ({ct} ct): living off the heat in the house",
        store_ahead: "warming the floor ahead of dearer hours ({ct} ct from {at}:00)",
        store_ahead_house: "warming the house ahead of dearer hours ({ct} ct from {at}:00)",
        warm_enough: "warm enough ({room} \u00b0C): no heat needed", holding: "keeping the room at temperature",
        paused: "changed by hand: leaving the thermostat alone for {min} more min",
        already_right: "thermostat already right", wait: "next change allowed in {min} min",
        urgent: "room below the minimum: correcting now", hold_ahead: "room above the setpoint: keeping {sp} \u00b0C ahead of dearer hours ({ct} ct from {at}:00); the heat pump waits", following: "following the plan",
        airing: "window open: thermostat at its lowest until it closes", fallback_no_price: "no price: planned on one flat price", fallback_schedule: "no full plan: comfort schedule", min_run: "the heat pump just started: lowering in {min} min", set_failed: "could not set the thermostat: trying again in {min} min" },
  nl: { starting: "opstarten", window_open: "raam open: Roost wacht tot de kamer terug is", no_price: "geen prijs", no_room: "geen kamertemperatuur",
        no_weather: "geen weersverwachting en geen buitentemperatuur", no_plan: "geen plan", off: "Roost staat uit",
        store_solar: "vloer opladen met eigen zonnestroom (tot {sp} \u00b0C)",
        store_cheap: "vloer opladen ({ct} ct), straks wordt het duurder",
        expensive: "duur uur ({ct} ct): teert op de vloerbuffer",
        store_solar_house: "warmte opslaan in het huis met eigen zonnestroom (tot {sp} \u00b0C)",
        store_cheap_house: "warmte opslaan in het huis ({ct} ct), straks wordt het duurder",
        expensive_house: "duur uur ({ct} ct): teert op de warmte in het huis",
        store_ahead: "vloer alvast opwarmen voor duurdere uren ({ct} ct vanaf {at}:00)",
        store_ahead_house: "huis alvast opwarmen voor duurdere uren ({ct} ct vanaf {at}:00)",
        warm_enough: "warm genoeg ({room} \u00b0C): geen warmte nodig", holding: "kamer op temperatuur houden",
        paused: "met de hand gewijzigd: thermostaat nog {min} min met rust gelaten",
        already_right: "thermostaat staat al goed", wait: "volgende wijziging over {min} min",
        urgent: "kamer onder het minimum: nu bijsturen", hold_ahead: "kamer boven het setpoint: houdt {sp} \u00b0C aan v\u00f3\u00f3r duurdere uren ({ct} ct vanaf {at}:00); de warmtepomp wacht", following: "volgt het plan",
        airing: "raam open: thermostaat op de laagste stand tot het dicht is", fallback_no_price: "geen prijs: gepland op \u00e9\u00e9n vlakke prijs", fallback_schedule: "geen volledig plan: comfortschema", min_run: "warmtepomp is net gestart: verlagen over {min} min", set_failed: "thermostaat niet gelukt: opnieuw over {min} min" },
  de: { starting: "startet", window_open: "Fenster offen: Roost wartet, bis der Raum zur\u00fcck ist", no_price: "kein Preis", no_room: "keine Raumtemperatur",
        no_weather: "keine Wettervorhersage und keine Au\u00dfentemperatur", no_plan: "kein Plan", off: "Roost ist aus",
        store_solar: "l\u00e4dt den Boden mit eigenem Solarstrom (bis {sp} \u00b0C)",
        store_cheap: "l\u00e4dt den Boden jetzt ({ct} ct) vor teureren Stunden",
        expensive: "teure Stunde ({ct} ct): lebt von der W\u00e4rme im Boden",
        store_solar_house: "speichert W\u00e4rme im Haus mit eigenem Solarstrom (bis {sp} \u00b0C)",
        store_cheap_house: "speichert W\u00e4rme im Haus jetzt ({ct} ct) vor teureren Stunden",
        expensive_house: "teure Stunde ({ct} ct): lebt von der W\u00e4rme im Haus",
        store_ahead: "w\u00e4rmt den Boden vor teureren Stunden vor ({ct} ct ab {at}:00)",
        store_ahead_house: "w\u00e4rmt das Haus vor teureren Stunden vor ({ct} ct ab {at}:00)",
        warm_enough: "warm genug ({room} \u00b0C): keine W\u00e4rme n\u00f6tig", holding: "h\u00e4lt den Raum auf Temperatur",
        paused: "von Hand ge\u00e4ndert: l\u00e4sst das Thermostat noch {min} min in Ruhe",
        already_right: "Thermostat steht schon richtig", wait: "n\u00e4chste \u00c4nderung in {min} min erlaubt",
        urgent: "Raum unter dem Minimum: korrigiert jetzt", hold_ahead: "Raum \u00fcber dem Sollwert: h\u00e4lt {sp} \u00b0C vor teureren Stunden ({ct} ct ab {at}:00); die W\u00e4rmepumpe wartet", following: "folgt dem Plan",
        airing: "Fenster offen: Thermostat auf niedrigster Stufe bis es zu ist", fallback_no_price: "kein Preis: mit einem festen Preis geplant", fallback_schedule: "kein vollst\u00e4ndiger Plan: Komfortplan", min_run: "W\u00e4rmepumpe gerade gestartet: senken in {min} min", set_failed: "Thermostat nicht gesetzt: neuer Versuch in {min} min" },
  fr: { starting: "d\u00e9marrage", window_open: "fen\u00eatre ouverte : Roost attend que la pi\u00e8ce revienne", no_price: "pas de prix", no_room: "pas de temp\u00e9rature de pi\u00e8ce",
        no_weather: "pas de pr\u00e9visions m\u00e9t\u00e9o ni de temp\u00e9rature ext\u00e9rieure", no_plan: "pas de plan", off: "Roost est arr\u00eat\u00e9",
        store_solar: "charge le sol avec le solaire (jusqu'\u00e0 {sp} \u00b0C)",
        store_cheap: "charge le sol maintenant ({ct} ct) avant des heures plus ch\u00e8res",
        expensive: "heure ch\u00e8re ({ct} ct) : vit de la chaleur du sol",
        store_solar_house: "stocke de la chaleur dans la maison avec le solaire (jusqu'\u00e0 {sp} \u00b0C)",
        store_cheap_house: "stocke de la chaleur dans la maison maintenant ({ct} ct) avant des heures plus ch\u00e8res",
        expensive_house: "heure ch\u00e8re ({ct} ct) : vit de la chaleur de la maison",
        store_ahead: "pr\u00e9chauffe le sol avant des heures plus ch\u00e8res ({ct} ct d\u00e8s {at} h)",
        store_ahead_house: "pr\u00e9chauffe la maison avant des heures plus ch\u00e8res ({ct} ct d\u00e8s {at} h)",
        warm_enough: "assez chaud ({room} \u00b0C) : pas besoin de chaleur", holding: "maintient la pi\u00e8ce \u00e0 temp\u00e9rature",
        paused: "chang\u00e9 \u00e0 la main : laisse le thermostat encore {min} min",
        already_right: "thermostat d\u00e9j\u00e0 bien r\u00e9gl\u00e9", wait: "prochain changement possible dans {min} min",
        urgent: "pi\u00e8ce sous le minimum : correction maintenant", hold_ahead: "pi\u00e8ce au-dessus de la consigne : garde {sp} \u00b0C avant des heures plus ch\u00e8res ({ct} ct d\u00e8s {at}:00) ; la pompe \u00e0 chaleur attend", following: "suit le plan",
        airing: "fen\u00eatre ouverte : thermostat au plus bas jusqu'\u00e0 fermeture", fallback_no_price: "pas de prix : planifi\u00e9 sur un prix fixe", fallback_schedule: "pas de plan complet : programme de confort", min_run: "la pompe \u00e0 chaleur vient de d\u00e9marrer : baisse dans {min} min", set_failed: "thermostat non r\u00e9gl\u00e9 : nouvel essai dans {min} min" },
};
const WHY_DECIMALS = { sp: 1, room: 1, ct: 0, min: 0, at: 0 };
// The heating curve advice (sensor heating_curve): a folded table under the plan.
const CURVE_T = {
  en: { none_needed: "none", n_none: "None: at this outdoor temperature your house needs no heat.", wi_label: "Indoor temperature", wi_note: "what if: changes neither Roost nor the thermostat", lg_cloud_ot: "Measured under OpenTherm: each dot is an hour the heat pump ran the whole hour", lg_cloud_curve: "Measured on its heating curve: each dot is an hour the heat pump ran the whole hour", lg_cloud: "Measured: each dot is an hour the heat pump ran the whole hour", lg_dash: "Dashed: calculated (colder than measured) or in the cycling zone", need: "Needed", meas_ot: "Measured (OT)", meas_curve: "Measured (curve)", n_need: "Needed: the least your house asks for at that outdoor temperature, without margin.", n_meas_ot: "Measured (OT): the flow by the heat pump's own sensor, in hours it ran the whole hour while the OpenTherm thermostat set the water temperature.", n_meas_curve: "Measured (curve): the flow by the heat pump's own sensor, in hours it ran the whole hour on its own heating curve.", title: "Heating curve advice", out: "Outdoor", now: "Now", adv: "Advice", meas: "Measured", cz: "cycling zone", at0: "At 0 \u00b0C outside", loss: "Heat loss", cyc: "Cycles above", flow: "flow temperature", outside: "outdoor", x_axis: "outdoor temperature", y_axis: "flow \u00b0C", lg_adv: "Advice: the flow temperature your house needs", lg_now: "Now: the curve your heat pump has", lg_need: "Needed: the least your house asks for (without margin)", lg_meas: "Measured: what your heat pump really made", lg_cyc: "Cycling zone: here the heat pump switches on and off anyway", n_for: "For {room} \u00b0C indoors, from {days} heating days and {hours} hours of steady heating.", n_rough: "Still rough: little data yet.", n_cycles: "Above about {t} \u00b0C outside the heat pump switches on and off anyway; the points there (grey) matter little.", n_extra: "{x} \u00b0C is calculated: colder than any day measured (coldest {min} \u00b0C).", n_meas: "Measured: the flow temperature in hours the heat pump ran the whole hour, near that outdoor temperature.", n_thermostat: "Your heat pump follows the thermostat now; the advice applies when it runs on its heating curve.", n_oncurve: "Your heat pump runs on its heating curve.", n_set: "Use it for the maximum water temperature of the thermostat.", none: "No advice yet: Roost needs about 20 heating days and 30 hours of steady heating with the flow temperature from the Quatt statistics." },
  nl: { none_needed: "geen", n_none: "Geen: bij deze buitentemperatuur vraagt je huis geen warmte.", wi_label: "Binnentemperatuur", wi_note: "wat als: verandert Roost en de thermostaat niet", lg_cloud_ot: "Gemeten onder OpenTherm: elke stip is een uur waarin de warmtepomp het hele uur draaide", lg_cloud_curve: "Gemeten op de stooklijn: elke stip is een uur waarin de warmtepomp het hele uur draaide", lg_cloud: "Gemeten: elke stip is een uur waarin de warmtepomp het hele uur draaide", lg_dash: "Gestippeld: doorgerekend (kouder dan gemeten) of in de pendelzone", need: "Nodig", meas_ot: "Gemeten (OT)", meas_curve: "Gemeten (stooklijn)", n_need: "Nodig: wat je huis minimaal vraagt bij die buitentemperatuur, zonder marge.", n_meas_ot: "Gemeten (OT): de aanvoer volgens de sensor van de warmtepomp zelf, in uren dat hij het hele uur draaide terwijl de OpenTherm-thermostaat de watertemperatuur bepaalde.", n_meas_curve: "Gemeten (stooklijn): de aanvoer volgens de sensor van de warmtepomp zelf, in uren dat hij het hele uur op zijn eigen stooklijn draaide.", title: "Stooklijnadvies", out: "Buiten", now: "Nu", adv: "Advies", meas: "Gemeten", cz: "pendelzone", at0: "Bij 0 \u00b0C buiten", loss: "Warmteverlies", cyc: "Pendelt boven", flow: "aanvoertemperatuur", outside: "buiten", x_axis: "buitentemperatuur", y_axis: "aanvoer \u00b0C", lg_adv: "Advies: de aanvoertemperatuur die je huis nodig heeft", lg_now: "Nu: de stooklijn van je warmtepomp", lg_need: "Nodig: wat je huis minimaal vraagt (zonder marge)", lg_meas: "Gemeten: wat je warmtepomp echt maakte", lg_cyc: "Pendelzone: hier slaat de warmtepomp toch af en aan", n_for: "Voor {room} \u00b0C binnen, uit {days} stookdagen en {hours} uur rustig stoken.", n_rough: "Nog grof: nog weinig data.", n_cycles: "Boven ongeveer {t} \u00b0C buiten slaat de warmtepomp toch af en aan; de punten daar (grijs) maken weinig uit.", n_extra: "{x} \u00b0C is doorgerekend: kouder dan elke gemeten dag (koudste {min} \u00b0C).", n_meas: "Gemeten: de aanvoertemperatuur in uren dat de warmtepomp het hele uur draaide, rond die buitentemperatuur.", n_thermostat: "Je warmtepomp volgt nu de thermostaat; het advies geldt zodra hij op zijn stooklijn draait.", n_oncurve: "Je warmtepomp draait op zijn stooklijn.", n_set: "Gebruik het voor de maximale watertemperatuur van de thermostaat.", none: "Nog geen advies: Roost heeft ongeveer 20 stookdagen en 30 uur rustig stoken nodig, met de aanvoertemperatuur uit de Quatt-statistieken." },
  de: { none_needed: "keine", n_none: "Keine: bei dieser Au\u00dfentemperatur braucht dein Haus keine W\u00e4rme.", wi_label: "Innentemperatur", wi_note: "Was w\u00e4re wenn: \u00e4ndert weder Roost noch das Thermostat", lg_cloud_ot: "Gemessen unter OpenTherm: jeder Punkt ist eine Stunde, in der die W\u00e4rmepumpe durchlief", lg_cloud_curve: "Gemessen nach der Heizkurve: jeder Punkt ist eine Stunde, in der die W\u00e4rmepumpe durchlief", lg_cloud: "Gemessen: jeder Punkt ist eine Stunde, in der die W\u00e4rmepumpe durchlief", lg_dash: "Gestrichelt: berechnet (k\u00e4lter als gemessen) oder in der Taktzone", need: "N\u00f6tig", meas_ot: "Gemessen (OT)", meas_curve: "Gemessen (Kurve)", n_need: "N\u00f6tig: was dein Haus bei dieser Au\u00dfentemperatur mindestens braucht, ohne Reserve.", n_meas_ot: "Gemessen (OT): der Vorlauf laut dem eigenen F\u00fchler der W\u00e4rmepumpe, in Stunden, in denen sie die ganze Stunde lief, w\u00e4hrend das OpenTherm-Thermostat die Wassertemperatur vorgab.", n_meas_curve: "Gemessen (Kurve): der Vorlauf laut dem eigenen F\u00fchler der W\u00e4rmepumpe, in Stunden, in denen sie die ganze Stunde nach ihrer Heizkurve lief.", title: "Heizkurven-Empfehlung", out: "Au\u00dfen", now: "Jetzt", adv: "Empfehlung", meas: "Gemessen", cz: "Taktzone", at0: "Bei 0 \u00b0C au\u00dfen", loss: "W\u00e4rmeverlust", cyc: "Taktet \u00fcber", flow: "Vorlauftemperatur", outside: "au\u00dfen", x_axis: "Au\u00dfentemperatur", y_axis: "Vorlauf \u00b0C", lg_adv: "Empfehlung: die Vorlauftemperatur, die dein Haus braucht", lg_now: "Jetzt: die Kurve deiner W\u00e4rmepumpe", lg_need: "N\u00f6tig: was dein Haus mindestens braucht (ohne Reserve)", lg_meas: "Gemessen: was deine W\u00e4rmepumpe wirklich lieferte", lg_cyc: "Taktzone: hier taktet die W\u00e4rmepumpe ohnehin", n_for: "F\u00fcr {room} \u00b0C innen, aus {days} Heiztagen und {hours} Stunden ruhigem Heizen.", n_rough: "Noch grob: noch wenige Daten.", n_cycles: "Oberhalb von etwa {t} \u00b0C au\u00dfen taktet die W\u00e4rmepumpe ohnehin; die Punkte dort (grau) sind kaum wichtig.", n_extra: "{x} \u00b0C ist berechnet: k\u00e4lter als jeder gemessene Tag (k\u00e4ltester {min} \u00b0C).", n_meas: "Gemessen: die Vorlauftemperatur in Stunden, in denen die W\u00e4rmepumpe die ganze Stunde lief, bei dieser Au\u00dfentemperatur.", n_thermostat: "Deine W\u00e4rmepumpe folgt jetzt dem Thermostat; die Empfehlung gilt, sobald sie nach ihrer Heizkurve l\u00e4uft.", n_oncurve: "Deine W\u00e4rmepumpe l\u00e4uft nach ihrer Heizkurve.", n_set: "Nutze sie f\u00fcr die maximale Wassertemperatur am Thermostat.", none: "Noch keine Empfehlung: Roost braucht etwa 20 Heiztage und 30 Stunden ruhiges Heizen mit der Vorlauftemperatur aus den Quatt-Statistiken." },
  fr: { none_needed: "aucune", n_none: "Aucune : \u00e0 cette temp\u00e9rature ext\u00e9rieure, votre maison n'a pas besoin de chaleur.", wi_label: "Temp\u00e9rature int\u00e9rieure", wi_note: "et si : ne change ni Roost ni le thermostat", lg_cloud_ot: "Mesur\u00e9 sous OpenTherm : chaque point est une heure o\u00f9 la pompe a tourn\u00e9 toute l'heure", lg_cloud_curve: "Mesur\u00e9 sur sa courbe : chaque point est une heure o\u00f9 la pompe a tourn\u00e9 toute l'heure", lg_cloud: "Mesur\u00e9 : chaque point est une heure o\u00f9 la pompe a tourn\u00e9 toute l'heure", lg_dash: "Pointill\u00e9 : calcul\u00e9 (plus froid que mesur\u00e9) ou dans la zone de cycles", need: "N\u00e9cessaire", meas_ot: "Mesur\u00e9 (OT)", meas_curve: "Mesur\u00e9 (courbe)", n_need: "N\u00e9cessaire : le minimum que demande la maison \u00e0 cette temp\u00e9rature ext\u00e9rieure, sans marge.", n_meas_ot: "Mesur\u00e9 (OT) : le d\u00e9part selon la sonde de la pompe elle-m\u00eame, pendant les heures o\u00f9 elle a tourn\u00e9 toute l'heure pendant que le thermostat OpenTherm fixait la temp\u00e9rature de l'eau.", n_meas_curve: "Mesur\u00e9 (courbe) : le d\u00e9part selon la sonde de la pompe elle-m\u00eame, pendant les heures o\u00f9 elle a tourn\u00e9 toute l'heure sur sa propre courbe de chauffe.", title: "Conseil de courbe de chauffe", out: "Ext\u00e9rieur", now: "Actuel", adv: "Conseil", meas: "Mesur\u00e9", cz: "zone de cycles", at0: "\u00c0 0 \u00b0C dehors", loss: "D\u00e9perditions", cyc: "Cycle au-dessus de", flow: "temp\u00e9rature de d\u00e9part", outside: "ext\u00e9rieur", x_axis: "temp\u00e9rature ext\u00e9rieure", y_axis: "d\u00e9part \u00b0C", lg_adv: "Conseil : la temp\u00e9rature de d\u00e9part dont votre maison a besoin", lg_now: "Actuel : la courbe de votre pompe \u00e0 chaleur", lg_need: "N\u00e9cessaire : le minimum que demande la maison (sans marge)", lg_meas: "Mesur\u00e9 : ce que la pompe a r\u00e9ellement fourni", lg_cyc: "Zone de cycles : ici la pompe s'allume et s'\u00e9teint de toute fa\u00e7on", n_for: "Pour {room} \u00b0C \u00e0 l'int\u00e9rieur, d'apr\u00e8s {days} jours de chauffe et {hours} heures de chauffe stable.", n_rough: "Encore approximatif : peu de donn\u00e9es.", n_cycles: "Au-dessus d'environ {t} \u00b0C dehors la pompe s'allume et s'\u00e9teint de toute fa\u00e7on ; les points y (en gris) comptent peu.", n_extra: "{x} \u00b0C est calcul\u00e9 : plus froid que tout jour mesur\u00e9 (le plus froid {min} \u00b0C).", n_meas: "Mesur\u00e9 : la temp\u00e9rature de d\u00e9part pendant les heures o\u00f9 la pompe a tourn\u00e9 toute l'heure, autour de cette temp\u00e9rature ext\u00e9rieure.", n_thermostat: "Votre pompe \u00e0 chaleur suit le thermostat ; le conseil vaut quand elle fonctionne sur sa courbe de chauffe.", n_oncurve: "Votre pompe \u00e0 chaleur fonctionne sur sa courbe de chauffe.", n_set: "Utilisez-la pour la temp\u00e9rature d'eau maximale du thermostat.", none: "Pas encore de conseil : Roost a besoin d'environ 20 jours de chauffe et 30 heures de chauffe stable avec la temp\u00e9rature de d\u00e9part des statistiques Quatt." },
};

// Parts of the card that can be hidden with show_<part>: false. "compact: true" hides the chart and the saving and
// keeps the header and the tiles; a show_<part> set explicitly always wins (e.g. compact with show_chart: true).
const PARTS = ["status", "tiles", "chart", "pumps", "curve", "footer"];
const COMPACT_HIDES = ["chart", "pumps", "curve", "footer"];
const showDefault = (config, part) => !(config && config.compact && COMPACT_HIDES.indexOf(part) >= 0);
const shows = (config, part) => {
  const v = config ? config["show_" + part] : undefined;
  return v === undefined || v === null ? showDefault(config, part) : !!v;
};
const lang2 = (hass) => ((hass && ((hass.locale && hass.locale.language) || hass.language)) || "en").slice(0, 2);
const WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const fmt = (v, d) => (v === null || v === undefined || isNaN(v)) ? "\u2014" : Number(v).toFixed(d === undefined ? 0 : d);

const SAVING_QUALITY = {
  "en": {
    "partial_hours": "Home Assistant was restarted during an hour, so part of that hour was not measured.",
    "checked": "Model estimate checked against measured heating electricity and room temperatures; not a measured bill saving.",
    "forecast": "Expected model estimate; not a measured saving.",
    "unreliable": "No accepted saving estimate.",
    "extra_rooms": "The reference does not yet account for the extra rooms.",
    "comfort_mismatch": "The reference and Roost do not meet the same comfort.",
    "missing_context": "The original daily model and settings are missing.",
    "incomplete_day": "This local day is incomplete.",
    "incomplete_forecast": "A complete 24-hour plan is not available yet.",
    "missing_measurements": "Too few complete measurements.",
    "energy_mismatch": "Modelled heating electricity differs too much from the meter.",
    "temperature_mismatch": "The replayed room temperature differs too much from measurements.",
    "settings_changed": "Comfort settings changed during this day."
  },
  "nl": {
    "partial_hours": "Home Assistant is tijdens een uur herstart, waardoor een deel van dat uur niet is gemeten.",
    "checked": "Modelraming getoetst aan gemeten verwarmingsstroom en kamertemperaturen; geen gemeten besparing op de rekening.",
    "forecast": "Verwachte modelraming; geen gemeten besparing.",
    "unreliable": "Geen voldoende betrouwbare besparingsschatting.",
    "extra_rooms": "De referentie houdt nog geen rekening met de extra kamers.",
    "comfort_mismatch": "De referentie en Roost leveren niet hetzelfde comfort.",
    "missing_context": "Het oorspronkelijke dagmodel en de instellingen ontbreken.",
    "incomplete_day": "Deze lokale dag is onvolledig.",
    "incomplete_forecast": "Er is nog geen volledige planning voor 24 uur.",
    "missing_measurements": "Er zijn te weinig volledige metingen.",
    "energy_mismatch": "Het gesimuleerde verwarmingsverbruik wijkt te veel af van de meter.",
    "temperature_mismatch": "De gesimuleerde kamertemperatuur wijkt te veel af van de metingen.",
    "settings_changed": "De comfortinstellingen zijn tijdens deze dag veranderd."
  },
  "de": {
    "partial_hours": "Home Assistant wurde w\u00e4hrend einer Stunde neu gestartet; ein Teil dieser Stunde wurde nicht gemessen.",
    "incomplete_forecast": "Ein vollst\u00e4ndiger 24-Stunden-Plan ist noch nicht verf\u00fcgbar.",
    "checked": "Modellsch\u00e4tzung mit gemessenem Heizstrom und Raumtemperaturen gepr\u00fcft; keine gemessene Rechnungsersparnis.",
    "forecast": "Erwartete Modellsch\u00e4tzung; keine gemessene Ersparnis.",
    "unreliable": "Keine ausreichend zuverl\u00e4ssige Sparsch\u00e4tzung.",
    "extra_rooms": "Die Referenz ber\u00fccksichtigt die zus\u00e4tzlichen R\u00e4ume noch nicht.",
    "comfort_mismatch": "Die Referenz und Roost bieten nicht denselben Komfort.",
    "missing_context": "Das urspr\u00fcngliche Tagesmodell und die Einstellungen fehlen.",
    "incomplete_day": "Dieser lokale Tag ist unvollst\u00e4ndig.",
    "missing_measurements": "Zu wenige vollst\u00e4ndige Messungen.",
    "energy_mismatch": "Der simulierte Heizstrom weicht zu stark vom Z\u00e4hler ab.",
    "temperature_mismatch": "Die simulierte Raumtemperatur weicht zu stark von Messungen ab.",
    "settings_changed": "Die Komforteinstellungen wurden im Tagesverlauf ge\u00e4ndert."
  },
  "fr": {
    "partial_hours": "Home Assistant a red\u00e9marr\u00e9 pendant une heure ; une partie de cette heure n'a pas \u00e9t\u00e9 mesur\u00e9e.",
    "incomplete_forecast": "Le plan complet sur 24 heures n'est pas encore disponible.",
    "checked": "Estimation v\u00e9rifi\u00e9e avec la consommation de chauffage et les temp\u00e9ratures mesur\u00e9es ; pas une \u00e9conomie mesur\u00e9e sur la facture.",
    "forecast": "Estimation pr\u00e9vue par le mod\u00e8le ; pas une \u00e9conomie mesur\u00e9e.",
    "unreliable": "Pas d'estimation suffisamment fiable.",
    "extra_rooms": "La r\u00e9f\u00e9rence ne tient pas encore compte des pi\u00e8ces suppl\u00e9mentaires.",
    "comfort_mismatch": "La r\u00e9f\u00e9rence et Roost n'offrent pas le m\u00eame confort.",
    "missing_context": "Le mod\u00e8le initial du jour et ses r\u00e9glages manquent.",
    "incomplete_day": "Cette journ\u00e9e locale est incompl\u00e8te.",
    "missing_measurements": "Trop peu de mesures compl\u00e8tes.",
    "energy_mismatch": "La consommation simul\u00e9e diff\u00e8re trop du compteur.",
    "temperature_mismatch": "La temp\u00e9rature simul\u00e9e diff\u00e8re trop des mesures.",
    "settings_changed": "Les r\u00e9glages de confort ont chang\u00e9 pendant cette journ\u00e9e."
  }
};

const PRICE_HORIZON = {
  en: "Tariff planning until {time}; later tariffs are not available yet.",
  nl: "Tariefplanning tot {time}; latere tarieven zijn nog niet beschikbaar.",
  de: "Tarifplanung bis {time}; sp\u00e4tere Tarife sind noch nicht verf\u00fcgbar.",
  fr: "Planification tarifaire jusqu'\u00e0 {time} ; les tarifs suivants ne sont pas encore disponibles."
};

class RoostCard extends HTMLElement {
  static getConfigElement() { return document.createElement("roost-quatt-card-editor"); }

  static getStubConfig(hass) {
    const ent = Object.keys(hass.states).find((e) => e.startsWith("sensor.") && hass.states[e].attributes &&
      hass.states[e].attributes.plan !== undefined && hass.states[e].attributes.store_max !== undefined);
    return { entity: ent || "" };
  }

  setConfig(config) {
    if (!config.entity) throw new Error("entity is required (the 'Planned setpoint' sensor)");
    this._config = Object.assign({}, config);
    if (this._view === undefined) this._view = ["history", "table", "curve"].indexOf(config.view) >= 0 ? config.view : "plan";
    if (this._range === undefined) this._range = 24;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const st = this._config && hass.states[this._config.entity];
    const sib = this._siblings();
    const parts = [st ? st.last_updated : "none", hass.locale && hass.locale.language];
    Object.keys(sib).forEach((k) => { const s = hass.states[sib[k]]; parts.push(s ? s.state : ""); });
    const key = parts.join("|");
    if (key !== this._key) { this._key = key; this._render(); }
  }

  getCardSize() { return 2 + (this._show("tiles") ? 1 : 0) + (this._show("chart") ? 3 : 0); }
  getGridOptions() { return { columns: 12, min_columns: 6 }; }

  _show(part) { return shows(this._config, part); }
  _lang() { const own = this._config && this._config.language; return own && T[own] ? own : lang2(this._hass); }
  _t(k) { return (T[this._lang()] || T.en)[k]; }
  _why(code, args, text) {
    const tpl = code && ((WHY[this._lang()] || WHY.en)[code] || WHY.en[code]);
    if (!tpl) return text || "";
    return tpl.replace(/\{(\w+)\}/g, (m, k) => (args && args[k] !== undefined ? this._num(args[k], nn(WHY_DECIMALS[k], 1)) : m));
  }
  _locale() {
    const user = (this._hass && ((this._hass.locale && this._hass.locale.language) || this._hass.language)) || undefined;
    const own = this._config && this._config.language;
    if (own && T[own]) return user && user.slice(0, 2) === own ? user : own;
    return user;
  }
  _hour(date) {
    const opts = { hour: "2-digit", minute: "2-digit" };
    const own = this._config && this._config.time_format;
    const profile = this._hass && this._hass.locale && this._hass.locale.time_format;
    const choice = own === "24" || own === "12" ? own : profile;
    if (choice === "24") opts.hour12 = false;
    if (choice === "12") opts.hour12 = true;
    return date.toLocaleTimeString(choice === "system" ? undefined : this._locale(), opts);
  }
  _num(v, d) { return v === null || v === undefined || isNaN(v) ? "\u2014" : Number(v).toLocaleString(this._locale(), { minimumFractionDigits: d, maximumFractionDigits: d }); }
  _money(v) {
    if (v === null || v === undefined || isNaN(v)) return "\u2014";
    const cur = (this._hass && this._hass.config && this._hass.config.currency) || "EUR";
    try { return Number(v).toLocaleString(this._locale(), { style: "currency", currency: cur }); } catch (e) { return fmt(v, 2); }
  }

  // The other Roost entities of the same entry, found through the entity registry by their translation key.
  _siblings() {
    const hass = this._hass, out = {};
    if (!hass || !hass.entities || !this._config) return out;
    const me = hass.entities[this._config.entity];
    if (!me || !me.device_id) return out;
    Object.keys(hass.entities).forEach((eid) => {
      const e = hass.entities[eid];
      if (e.device_id === me.device_id && e.platform === "roost_quatt" && e.translation_key) out[e.translation_key] = eid;
    });
    return out;
  }
  _hm(d) {   // a time, with the weekday when it is not today
    return (d.toDateString() === new Date().toDateString() ? "" : d.toLocaleDateString(this._lang(), { weekday: "short" }) + " ") +
      d.toLocaleTimeString(this._lang(), { hour: "2-digit", minute: "2-digit" });
  }
  _sib(key) { const s = this._siblings(); const st = s[key] && this._hass.states[s[key]]; return st ? st : null; }

  _shell() {
    if (this._card && this._card.parentNode === this.shadowRoot) return this._card;
    this.shadowRoot.innerHTML = `${this._style()}<ha-card></ha-card>`;
    this._card = this.shadowRoot.querySelector("ha-card");
    // the plan graph is drawn in the card's own pixels (text stays its size on a wide dashboard): draw again when the
    // width changes clearly
    if (typeof ResizeObserver !== "undefined") {
      new ResizeObserver((es) => {
        const w = Math.round(es[0].contentRect.width);
        if (w && Math.abs(w - (this._chartW || 0)) > 24) { this._chartW = w; if (this._clickable) this._render(); }
      }).observe(this._card);
    }
    this._card.addEventListener("click", (ev) => {
      if (!this._clickable || (ev.target && ev.target.closest && ev.target.closest(".chart, .seg, .hlog, .rep, .curve, .cview, .ico, .pill, .mmenu, .ptable, .tile.plan, .tile.therm, button, .status, .cal, .week"))) return;
      const e = new Event("hass-more-info", { bubbles: true, composed: true });
      e.detail = { entityId: this._config.entity };
      this.dispatchEvent(e);
    });
    return this._card;
  }

  _render() {
    if (!this.shadowRoot || !this._config || !this._hass) return;
    const st = this._hass.states[this._config.entity];
    if (!st || st.state === "unavailable" || st.state === "unknown") {
      this._clickable = false;
      this._shell().innerHTML = `<div class="na">${st ? this._t("unavailable") : this._t("pick")}</div>`;
      return;
    }
    const a = st.attributes;
    const mode = a.mode || "shadow";
    const paused = a.paused_until && new Date(a.paused_until) > new Date();
    const canMode = !!this._siblings().mode;
    const away = a.away_until && new Date(a.away_until) > new Date();
    const pill = `<span class="pill ${paused ? "warn" : (away ? "warn" : mode)}${canMode ? " modebtn" : ""}">${this._t(paused ? "paused" : (away ? "st_away" : mode))}` +
      `${canMode ? ' <ha-icon icon="mdi:menu-down"></ha-icon>' : ""}</span>`;
    const title = this._config.title || this._t("title");
    const reason = this._why(a.reason_code, a.reason_args, a.reason) || this._t("noplan");
    const decision = this._why(a.decision_code, a.decision_args, a.decision);
    // the planned setpoint is a thermostat setting (a lever: a slow unit may be set well below the room), so show
    // where the room is expected to go with it
    const p0 = a.plan && a.plan.length ? a.plan[0] : null;
    let expect = p0 ? `${this._t("expected")} ${this._num(p0[1], 1)} ${DEG}` : reason;
    if (p0) {        // the next change the plan makes, when there is one in the coming 24 hours
      const i = a.plan.findIndex((p, j) => j > 0 && Math.abs(p[0] - p0[0]) >= 0.25);
      if (i > 0) {
        const t0 = a.start ? new Date(a.start).getTime() : Date.now();
        expect = this._t("next_at").replace("{t}", this._hour(new Date(t0 + i * 3600000))).replace("{sp}", `${this._num(a.plan[i][0], 1)}${DEG}`);
      }
    }
    const hist = this._histOn();
    const segv = (v, l) => `<span data-v="${v}" class="${this._view === v ? "on" : ""}">${this._t(l)}</span>`;
    const hasCurve = !!this._siblings().heating_curve && this._show("curve");
    const seg = hist ? `<div class="seg">${segv("plan", "ahead")}${segv("table", "tab_table")}` +
      `${hasCurve ? segv("curve", "tab_curve") : ""}${segv("history", "back")}</div>` : "";
    let html = `<div class="head"><div class="ico" title="${this._t("go_integration")}"><ha-icon icon="mdi:bird"></ha-icon></div>
      <div class="ht"><div class="tt">${title}</div><div class="sub">${reason}</div></div>${seg}${pill}</div>`;
    const ready = this._sib("ready");
    if (mode === "active" && ready && ready.state === "off") html += `<div class="warnline"><ha-icon icon="mdi:alert-outline"></ha-icon>${this._t("warn_notready")}</div>`;
    html += this._status(a);
    if (this._calOpen) html += this._calendar();
    if (this._modeOpen && canMode) html += this._modeMenu(mode, paused, away, a);
    if (hist && this._view === "curve") {
      html += this._curveView();
      this._clickable = true;
      this._shell().innerHTML = html;
      this._wire();
      return;
    }
    if (hist && this._view === "table") {
      html += this._tableBody(a);
      if (this._show("footer")) html += this._footer(a);
      this._clickable = true;
      this._shell().innerHTML = html;
      this._wire();
      return;
    }
    if (hist && this._view === "history") {
      html += this._histBody();
      if (this._show("footer")) html += this._footer(a);
      this._clickable = true;
      this._shell().innerHTML = html;
      this._wire();
      return;
    }
    if (this._show("tiles")) html += this._tiles(st, a, decision, expect);
    if (a.rooms && a.rooms.length) html += this._rooms(a.rooms);
    // ready (nightly self-check) and still in shadow: one button to let Roost steer, clicked twice
    if (ready && ready.state === "on" && mode === "shadow" && this._siblings().mode) {
      html += `<button class="steer">${this._t("steer")}</button>`;
    }
    if (this._show("chart") && a.plan && a.plan.length) html += this._chart(a);
    if (this._show("footer")) html += this._pumpRow(a) + this._footer(a);
    this._clickable = true;
    this._shell().innerHTML = html;
    this._wire();
  }

  _ct(k, args) {
    const tpl = (CURVE_T[this._lang()] || CURVE_T.en)[k] || CURVE_T.en[k];
    return tpl.replace(/\{(\w+)\}/g, (m, x) => (args && args[x] !== undefined ? args[x] : m));
  }

  // The heating curve the house needs: the five points, and the flow the unit made at that outdoor temperature; folded, remembered while the card lives
  _curve() {
    const s = this._sib("heating_curve"), a = s && s.attributes;
    if (!a || !a.points || !a.points.length) return "";
    return `<details class="curve"${this._curveOpen ? " open" : ""}><summary>${this._ct("title")}` +
      `${s.state && !isNaN(parseFloat(s.state)) ? ` <span>0\u00b0 \u2192 ${this._num(parseFloat(s.state), 1)}${DEG}</span>` : ""}</summary>` +
      `${this._curveTable(a)}</details>`;
  }

  // The curve view: three numbers, the curve in a graph (advice, the curve now, what the house needs, what the unit
  // made, the zone where it cycles), the five points and the notes
  // The advice for another indoor temperature ("what if"): the same steps as Roost's curve.py, on its learned numbers
  _curveFor(a, room) {
    const ua = nn(a.ua_kw, (a.heat_loss_w_per_k || 0) / 1000), k = nn(a.k_kw, (a.emitter_w_per_k || 0) / 1000), n = a.n || 1.1;
    const base = nn(a.base_kw, 0), margin = nn(a.margin_kw, 0);
    if (!(ua > 0 && k > 0)) return a;
    const up = (v) => Math.ceil(v * 2 - 1e-9) / 2;
    const flow = (t) => { const q = ua * (room - t) + base + margin; return q > 0 ? room + Math.pow(q / k, 1 / n) : null; };
    const top = room + (base + margin) / ua;
    let prev = null;
    const points = a.points.map((p) => {
      const x = p[0];
      let y;
      if (!prev) { const f0 = flow(x); y = f0 !== null && x < top ? up(f0) : up(room); }
      else if (prev[0] >= top) y = up(room);
      else {
        const x0 = prev[0], y0 = prev[1], end = Math.min(x, top), steps = Math.max(2, Math.floor((end - x0) * 4));
        let yy = null;
        for (let i = 1; i <= steps; i++) {
          const t = x0 + (end - x0) * i / steps, f = flow(t);
          if (f === null) continue;
          const ny = y0 + (f - y0) * (x - x0) / (t - x0);
          yy = yy === null ? ny : Math.max(yy, ny);
        }
        y = yy !== null ? up(Math.max(room, Math.min(yy, y0))) : up(room);
      }
      prev = [x, y];
      return [x, y, p[2]];
    });
    return Object.assign({}, a, { room, points });
  }

  _curveView() {
    const s = this._sib("heating_curve"), a0 = s && s.attributes;
    if (!a0 || !a0.points || !a0.points.length) return `<div class="cview"><div class="na">${this._ct("none")}</div></div>`;
    const room = this._curveRoom !== undefined ? this._curveRoom : nn(a0.room, 20);
    const a = Math.abs(room - nn(a0.room, 20)) < 0.01 ? a0 : this._curveFor(a0, room);
    const tile = (label, v, unit, sub) => `<div class="tile htile"><div class="tl">${label}</div><div class="tv">${v}<span>${unit}</span></div><div class="ts">${sub}</div></div>`;
    const pts = a.points.filter((p) => p[1] !== null && p[1] !== undefined);
    let at0 = parseFloat(s.state);
    if (a !== a0 && pts.length > 1) {        // 0 degrees on the line between the points around it
      const i = pts.findIndex((p) => p[0] >= 0);
      at0 = i > 0 ? pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * (0 - pts[i - 1][0]) / (pts[i][0] - pts[i - 1][0]) : pts[0][1];
    }
    const cyc = a.cycling_from;
    return `<div class="cview"><div class="tiles">` +
      tile(this._ct("at0"), isNaN(at0) ? "\u2014" : this._num(at0, 1), DEG, this._ct("flow")) +
      tile(this._ct("loss"), a.heat_loss_w_per_k !== undefined ? this._num(a.heat_loss_w_per_k, 0) : "\u2014", "W/K", `${a.days} d \u00b7 ${a.hours} h`) +
      tile(this._ct("cyc"), cyc !== null && cyc !== undefined ? this._num(cyc, 0) : "\u2014", DEG, this._ct("outside")) +
      `</div><div class="mrow wirow"><b>${this._ct("wi_label")}</b><span><button class="mini" data-room="-0.5">\u2212</button>` +
      `<b class="sv">${this._num(room, 1)}${DEG}</b><button class="mini" data-room="0.5">+</button></span><small>${this._ct("wi_note")}</small></div>` +
      `${this._curveChart(a)}${this._curveTable(a)}</div>`;
  }

  // Flow temperature against outdoor temperature: the advice (orange, its five points with their values), the curve
  // the heat pump has now (grey, when known), what the house needs without margin (blue, dashed), what the
  // heat pump really made (white dots with their values), the cycling zone (shaded)
  _curveChart(a) {
    const VW = 440, VH = 230, L = 34, R = 14, TOP = 22, B = 34;
    const xs = a.points.map((p) => p[0]).sort((p, q) => p - q), X0 = xs[0], X1 = xs[xs.length - 1];
    const pts = a.points.filter((p) => p[1] !== null && p[1] !== undefined);
    const cloud = (a.cloud || []).filter((c) => c[0] >= X0 && c[0] <= X1);
    const room = nn(a.room, 20), ua = nn(a.ua_kw, (a.heat_loss_w_per_k || 0) / 1000), k = nn(a.k_kw, (a.emitter_w_per_k || 0) / 1000), n = a.n || 1.1;
    const base = nn(a.base_kw, 0), cyc = a.cycling_from !== null && a.cycling_from !== undefined ? a.cycling_from : X1;
    const cold = a.cold_hour !== null && a.cold_hour !== undefined ? Math.max(X0, a.cold_hour) : X0;
    const need = (t) => { const q = ua * (room - t) + base; return q > 0 && k > 0 ? room + Math.pow(q / k, 1 / n) : null; };
    const adv = (t) => {        // the advice line: the five points, straight between them
      if (t <= pts[0][0]) return pts[0][1];
      for (let i = 1; i < pts.length; i++) if (t <= pts[i][0]) return pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * (t - pts[i - 1][0]) / (pts[i][0] - pts[i - 1][0]);
      return pts[pts.length - 1][1];
    };
    const needPts = [];        // what the house needs, up to where it needs no heat at all
    for (let t = X0; t <= X1 + 1e-9; t += 0.25) { const v = need(t); if (v === null) break; needPts.push([t, v]); }
    const ys = [room].concat(pts.map((p) => p[1]), cloud.map((c) => c[1]), needPts.map((p) => p[1]));
    const lo = Math.floor((Math.min.apply(null, ys) - 2) / 5) * 5, hi = Math.ceil((Math.max.apply(null, ys) + 3) / 5) * 5;
    // the five points of the app evenly over the width; straight between them (each stretch on its own scale)
    const x = (t) => {
      if (t <= X0) return L;
      let i = 0;
      while (i < xs.length - 2 && t > xs[i + 1]) i++;
      const f = Math.min(1, (t - xs[i]) / (xs[i + 1] - xs[i]));
      return L + (i + f) / (xs.length - 1) * (VW - L - R);
    };
    const y = (v) => TOP + (hi - v) / (hi - lo) * (VH - TOP - B);
    const path = (list) => list.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)} ${y(p[1]).toFixed(1)}`).join(" ");
    let g = "";
    if (cyc < X1) {
      g += `<rect x="${x(Math.max(X0, cyc)).toFixed(1)}" y="${TOP}" width="${(x(X1) - x(Math.max(X0, cyc))).toFixed(1)}" height="${VH - TOP - B}" class="czone"/>` +
        `<text x="${(x(X1) - 4).toFixed(1)}" y="${TOP + 11}" text-anchor="end" class="axis">${this._ct("cz")}</text>`;
    }
    for (let v = lo; v <= hi; v += 5) g += `<line x1="${L}" x2="${VW - R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" class="grid"/><text x="${L - 5}" y="${(y(v) + 3.5).toFixed(1)}" text-anchor="end" class="axis">${v}\u00b0</text>`;
    a.points.forEach((p) => {       // the x axis on the five points of the app
      g += `<line x1="${x(p[0]).toFixed(1)}" x2="${x(p[0]).toFixed(1)}" y1="${TOP}" y2="${VH - B}" class="grid vgrid"/>` +
        `<text x="${x(p[0]).toFixed(1)}" y="${VH - 18}" text-anchor="${p[0] <= X0 ? "start" : (p[0] >= X1 ? "end" : "middle")}" class="axis">${this._num(p[0], 0)}\u00b0</text>`;
    });
    g += `<text x="${((L + VW - R) / 2).toFixed(1)}" y="${VH - 3}" text-anchor="middle" class="axis">${this._ct("x_axis")} \u2192</text>` +
      `<text x="${L}" y="${TOP - 10}" class="axis">${this._ct("y_axis")}</text>`;
    cloud.forEach((c) => { g += `<circle cx="${x(c[0]).toFixed(1)}" cy="${y(c[1]).toFixed(1)}" r="1.7" class="ccloud"/>`; });
    const needIn = needPts.filter((p) => p[0] <= cyc + 1e-9), needOut = needPts.filter((p) => p[0] >= cyc - 0.25);
    if (needIn.length > 1) g += `<path d="${path(needIn)}" class="cneed"/>`;
    if (needOut.length > 1 && cyc < X1) g += `<path d="${path(needOut)}" class="cneed soft"/>`;
    if (pts.length > 1) {           // solid where it rests on measurements, dashed where calculated or in the cycling zone
      const seg = (t0, t1) => { const xs = [t0].concat(pts.map((p) => p[0]).filter((t) => t > t0 && t < t1), [t1]); return path(xs.map((t) => [t, adv(t)])); };
      const end = Math.min(X1, Math.max(cold, cyc));
      if (cold > X0) g += `<path d="${seg(X0, cold)}" class="cadv dash"/>`;
      if (end > cold) g += `<path d="${seg(cold, end)}" class="cadv"/>`;
      if (end < X1) g += `<path d="${seg(end, X1)}" class="cadv dash"/>`;
    }
    pts.forEach((p) => {
      const soft = p[0] > cyc;
      g += `<circle cx="${x(p[0]).toFixed(1)}" cy="${y(p[1]).toFixed(1)}" r="4" class="cdot${soft ? " soft" : ""}"/>` +
        `<text x="${x(p[0]).toFixed(1)}" y="${(p[0] <= X0 ? y(p[1]) - 8 : y(p[1]) + 16).toFixed(1)}" text-anchor="${p[0] <= X0 ? "start" : (p[0] >= X1 ? "end" : "middle")}" class="cval${soft ? " soft" : ""}">${this._num(p[1], 1)}</text>`;
    });
    const leg = (cls, txt) => `<div><b class="l ${cls}"></b>${txt}</div>`;
    const cl = a.measured_by === "opentherm" ? "lg_cloud_ot" : (a.measured_by === "heating_curve" ? "lg_cloud_curve" : "lg_cloud");
    return `<div class="chart"><svg viewBox="0 0 ${VW} ${VH}">${g}</svg><div class="cleg">` +
      leg("sp", this._ct("lg_adv")) + leg("cneedl", this._ct("lg_need")) + (cloud.length ? leg("ccl", this._ct(cl)) : "") +
      leg("cdashl", this._ct("lg_dash")) + (cyc < X1 ? leg("czl", this._ct("lg_cyc")) : "") + `</div></div>`;
  }

  _curveTable(a) {
    const cur = {};
    (a.current || []).forEach((p) => { cur[p[0]] = p[1]; });
    const hasCur = Object.keys(cur).length > 0, hasMeas = a.points.some((p) => p[2] !== null && p[2] !== undefined);
    const cyc = a.cycling_from;
    const c = (v) => (v === null || v === undefined ? "\u2014" : this._num(v, 1));
    const room = nn(a.room, 20), ua = nn(a.ua_kw, (a.heat_loss_w_per_k || 0) / 1000), k = nn(a.k_kw, (a.emitter_w_per_k || 0) / 1000), n = a.n || 1.1;
    const need = (t) => { const q = ua * (room - t) + nn(a.base_kw, 0); return q > 0 && k > 0 ? room + Math.pow(q / k, 1 / n) : null; };
    const hasNeed = k > 0 && ua > 0;
    const mk = a.measured_by === "opentherm" ? "meas_ot" : (a.measured_by === "heating_curve" ? "meas_curve" : "meas");
    let rows = "";
    a.points.forEach((p) => {
      const inCz = cyc !== null && cyc !== undefined && p[0] > cyc;
      rows += `<tr${inCz ? ' class="cz"' : ""}><td>${this._num(p[0], 0)}\u00b0</td>${hasCur ? `<td>${c(cur[p[0]])}</td>` : ""}` +
        `<td><b>${c(p[1])}</b></td>${hasNeed ? `<td>${need(p[0]) === null ? `<i>${this._ct("none_needed")}</i>` : c(need(p[0]))}</td>` : ""}` +
        `${hasMeas ? `<td>${c(p[2])}</td>` : ""}</tr>`;
    });
    const notes = [this._ct("n_for", { room: this._num(a.room, 1), days: a.days, hours: a.hours })];
    if (a.control === "heating_curve") notes.push(this._ct("n_oncurve"));
    else if (a.control) notes.push(this._ct("n_thermostat"));
    if (!a.reliable) notes.push(this._ct("n_rough"));
    if (cyc !== null && cyc !== undefined) notes.push(this._ct("n_cycles", { t: this._num(cyc, 0) }));
    (a.extrapolated || []).forEach((x) => notes.push(this._ct("n_extra", { x: this._num(x, 0), min: this._num(a.out_min, 1) })));
    if (hasNeed) notes.push(this._ct("n_need"));
    if (hasNeed && a.points.some((p) => need(p[0]) === null)) notes.push(this._ct("n_none"));
    if (hasMeas) notes.push(this._ct(mk === "meas" ? "n_meas" : "n_" + mk));
    notes.push(this._ct("n_set"));
    return `<div class="curve"><table><tr><th>${this._ct("out")}</th>${hasCur ? `<th>${this._ct("now")}</th>` : ""}<th>${this._ct("adv")}</th>` +
      `${hasNeed ? `<th>${this._ct("need")}</th>` : ""}${hasMeas ? `<th>${this._ct(mk)}</th>` : ""}</tr>${rows}</table>` +
      `<ul class="cnote">${notes.map((t) => `<li>${t}</li>`).join("")}</ul></div>`;
  }

  // Extra rooms (radiators upstairs, a bedroom): temperature, minimum and its hours; orange when below it in its hours
  _rooms(list) {
    const chips = list.map((r) => {
      const cold = r.active_now && r.temperature < r.minimum;
      return `<span class="room${cold ? " cold" : ""}" title="${r.from}:00\u2013${r.to}:00"><b>${r.name}</b> ${this._num(r.temperature, 1)}${DEG}` +
        ` \u00b7 ${this._t("min")} ${this._num(r.minimum, 1)} <i>(${r.from}\u2013${r.to})</i></span>`;
    });
    return `<div class="rooms">${chips.join("")}</div>`;
  }

  // ---------------------------------------------------------------- v0.8.0: status line, tiles, pump runs, calendar
  _fill(k, args) {
    let t = this._t(k) || "";
    Object.keys(args || {}).forEach((a) => { t = t.replace("{" + a + "}", args[a]); });
    return t;
  }
  _clock(min) { return `${String(Math.floor(min / 60) % 24).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`; }
  _nextChange(a) {
    const p = a.plan;
    if (!p || !p.length) return null;
    const i = p.findIndex((x, j) => j > 0 && Math.abs(x[0] - p[0][0]) >= 0.25);
    if (i <= 0) return null;
    const t0 = a.start ? new Date(a.start).getTime() : Date.now();
    return { t: new Date(t0 + i * 3600000), sp: p[i][0], up: p[i][0] > p[0][0] };
  }
  // One line under the header: the plan held and its next change, then chips only for what is going on now
  _status(a) {
    if (!this._show("status")) return "";
    const bits = [], chips = [];
    if (a.plan_made) {
      const t = new Date(a.plan_made);
      if (!isNaN(t)) bits.push(this._fill("st_held", { t: this._hm(t) }));
    }
    const nx = this._nextChange(a);
    if (nx) bits.push(this._fill("st_next", { t: this._hm(nx.t), sp: `<b>${this._num(nx.sp, 1)}${DEG}</b>` }));
    else if (a.plan && a.plan.length) bits.push(this._t("st_nochange"));
    if (a.price_limited_until) {
      const u = new Date(a.price_limited_until);
      if (!isNaN(u)) chips.push(`<span class="chip info">${this._fill("st_prices", { t: this._hm(u) })}</span>`);
    }
    if (a.fallback) chips.push(`<span class="chip warn">${this._t(a.fallback === "no_price" ? "fb_no_price" : "fb_schedule")}</span>`);
    const dc = a.decision_code;
    if (["min_run", "airing", "window_open", "set_failed", "paused"].indexOf(dc) >= 0) {
      chips.push(`<span class="chip warn">${this._why(dc, a.decision_args, a.decision)}</span>`);
    }
    if (a.pump_runs && a.pump_runs.heating && dc !== "min_run") chips.push(`<span class="chip heat"><ha-icon icon="mdi:fire"></ha-icon>${this._t("pump_on")}</span>`);
    const sm = this._sib("saving_month");
    if (sm) {        // the month's saving and how many days count: tap for the calendar
      const at = sm.attributes || {}, v = parseFloat(sm.state), inc = (at.included_days || []).length;
      chips.push(`<span class="chip calpill${this._calOpen ? " on" : ""}"><ha-icon icon="mdi:calendar-check"></ha-icon>` +
        `${isNaN(v) ? "\u2014" : this._money(v)} \u00b7 ${inc}/${nn(at.days_expected, inc)}</span>`);
    }
    if (!bits.length && !chips.length) return "";
    return `<div class="status"><ha-icon icon="mdi:lock-clock"></ha-icon><span class="stx">${bits.join(" \u00b7 ")}</span>${chips.join("")}</div>`;
  }
  // The room the last hours (measured) and the next six (expected), a small line in the room tile
  _spark(a) {
    const past = (a.room_recent || []).map((r) => r[1]);
    const ahead = (a.plan || []).slice(0, 6).map((p) => p[1]);
    const now = nn(a.room, past.length ? past[past.length - 1] : null);
    if (now === null || (!past.length && !ahead.length)) return "";
    const pts = past.concat([now]), fut = [now].concat(ahead), all = pts.concat(fut);
    const lo = Math.min.apply(null, all) - 0.1, hi = Math.max.apply(null, all) + 0.1, W = 120, H = 24, n = pts.length + fut.length - 2;
    const X = (i) => (i / Math.max(1, n) * W).toFixed(1), Y = (v) => (H - 2 - (v - lo) / Math.max(0.2, hi - lo) * (H - 4)).toFixed(1);
    const p1 = pts.map((v, i) => `${i ? "L" : "M"}${X(i)} ${Y(v)}`).join(" ");
    const o = pts.length - 1, p2 = fut.map((v, i) => `${i ? "L" : "M"}${X(o + i)} ${Y(v)}`).join(" ");
    return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><path d="${p1}" class="sp1"/><path d="${p2}" class="sp2"/>` +
      `<line x1="${X(o)}" x2="${X(o)}" y1="0" y2="${H}" class="spn"/></svg>`;
  }
  _tiles(st, a, decision, expect) {
    const nx = this._nextChange(a), heat = a.pump_runs && a.pump_runs.heating;
    const arrow = nx ? `<span class="nx ${nx.up ? "up" : "dn"}"><ha-icon icon="mdi:arrow-${nx.up ? "top-right" : "bottom-right"}"></ha-icon>` +
      `${this._num(nx.sp, 1)}${DEG} ${this._hour(nx.t)}</span>` : "";
    const why = a.plan_made_why ? `<span class="badge">${this._t("why_" + a.plan_made_why) || a.plan_made_why}</span>` : "";
    const warm = a.room !== null && a.room !== undefined && a.comfort !== undefined ? (a.room >= a.comfort ? "warm" : "cool") : "";
    return `<div class="tiles">
      <div class="tile rtile ${warm}"><div class="tl"><ha-icon icon="mdi:home-thermometer-outline"></ha-icon>${this._t("room")}</div>
        <div class="tv big">${this._num(a.room, 1)}<span>${DEG}</span></div>${this._spark(a) || `<div class="ts">${this._t("stored")} ${fmt(a.storage_kwh, 1)} kWh</div>`}
        <div class="ts">${this._t("stored")} ${fmt(a.storage_kwh, 1)} kWh</div></div>
      <div class="tile therm${a.thermostat_entity ? "" : " nolink"}"><div class="tl"><ha-icon icon="mdi:thermostat"></ha-icon>${this._t("thermostat")}${heat ? '<i class="hot" title="' + this._t("pump_on") + '"></i>' : ""}</div>
        <div class="tv">${this._num(a.thermostat, 1)}<span>${DEG}</span></div>${arrow}<div class="ts">${decision}</div></div>
      <div class="tile plan"><div class="tl"><ha-icon icon="mdi:bird"></ha-icon>${this._t("planned")}</div>
        <div class="tv">${this._num(parseFloat(st.state), 1)}<span>${DEG}</span></div>${why}<div class="ts">${expect}</div></div>
    </div>`;
  }
  // Starts and run length of the heat pump today against yesterday (the month's saving is the pill in the status line)
  _pumpRow(a) {
    const r = a.pump_runs;
    if (!r || !this._show("pumps")) return "";
    const t = r.today || {}, y = r.yesterday || {};
    if (!t.starts && !y.starts && !r.heating) return "";          // nothing to show before the first run
    const dur = (m) => (m === null || m === undefined ? "\u2014" : (m >= 60 ? `${Math.floor(m / 60)} u ${String(m % 60).padStart(2, "0")}` : `${m} min`));
    const better = (a1, b1, low) => (a1 === null || b1 === null || a1 === undefined || b1 === undefined ? "" : ((low ? a1 < b1 : a1 > b1) ? "good" : ""));
    return `<div class="mtiles"><div class="mt"><div class="tl">${this._t("pr_starts")}</div><div class="mv ${better(t.starts, y.starts, true)}">${nn(t.starts, 0)}</div>` +
      `<div class="ts">${this._fill("pr_yday", { n: nn(y.starts, "\u2014") })}</div></div>` +
      `<div class="mt"><div class="tl">${this._t("pr_run")}</div><div class="mv ${better(t.minutes, y.minutes, false)}">${dur(t.minutes)}</div>` +
      `<div class="ts">${this._fill("pr_was", { m: dur(y.minutes) })}</div></div></div>`;
  }
  // One dot per day of the month: counted, not counted (tap for why), no data
  _calendar() {
    const sm = this._sib("saving_month");
    if (!sm) return "";
    const at = sm.attributes || {}, inc = at.included_days || [], exc = at.excluded_days || [], reasons = at.day_reasons || {};
    const today = new Date(), y = today.getFullYear(), m = today.getMonth(), days = new Date(y, m + 1, 0).getDate();
    const lang = String(this._locale()).split("-")[0], q = SAVING_QUALITY[lang] || SAVING_QUALITY.en;
    const names = this._t("w_days").split(",");
    let cells = names.map((d) => `<span class="cwd">${d}</span>`).join("");
    for (let i = 0, lead = (new Date(y, m, 1).getDay() + 6) % 7; i < lead; i++) cells += "<span></span>";
    for (let d = 1; d <= days; d++) {
      const key = `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const cls = inc.indexOf(key) >= 0 ? "ok" : (exc.indexOf(key) >= 0 ? "bad" : (d >= today.getDate() ? "future" : "none"));
      const why = cls === "bad" ? (reasons[key] || []).map((r) => q[r] || r).join(" ") : "";
      const sel = this._calDay && this._calDay.day === key ? " sel" : "";
      cells += `<span class="cd ${cls}${sel}" data-day="${key}" data-why="${why.replace(/"/g, "&quot;")}">${d}</span>`;
    }
    const pick = this._calDay ? `<div class="cwhy"><b>${this._calDay.day.slice(8)}</b> \u00b7 ${this._calDay.why || this._t("cal_bad")}</div>` : "";
    const hint = inc.length ? "" : `<div class="cwhy">${this._t("cal_hint")}</div>`;
    return `<div class="cal"><div class="ch"><span>${this._t("cal_title")}</span></div><div class="cgrid">${cells}</div>` +
      `<div class="calleg"><span><i class="ok"></i>${this._t("cal_ok")}</span><span><i class="bad"></i>${this._t("cal_bad")}</span>` +
      `<span><i class="none"></i>${this._t("cal_none")}</span></div>${pick}${hint}</div>`;
  }
  // ---------------------------------------------------------------- the weekly comfort periods, edited in the card
  _weekDraft(a) {
    if (!this._wk) {
      const src = a.comfort_week || {}, from = nn(a.day_from, 7) * 60, to = nn(a.day_to, 22) * 60;
      this._wk = {};
      WEEKDAYS.forEach((d) => {
        const v = src[d];
        this._wk[d] = Array.isArray(v) ? v.map((p) => [p[0], p[1]]) : (a.comfort_week ? [] : [[from, to]]);
      });
      this._wkDay = nn(this._wkDay, (new Date().getDay() + 6) % 7);
    }
    return this._wk;
  }
  _weekEditor(a) {
    const on = !!a.weekly_comfort, wk = this._weekDraft(a), names = this._t("w_days").split(",");
    const seg = (s, e, cls) => `<i class="${cls}" style="left:${(s / 14.4).toFixed(2)}%;width:${((e - s) / 14.4).toFixed(2)}%"></i>`;
    let rows = "";
    WEEKDAYS.forEach((d, i) => {
      let bars = "";
      wk[d].forEach((p) => { bars += p[1] > p[0] ? seg(p[0], p[1], "blk") : seg(p[0], 1440, "blk"); });
      wk[WEEKDAYS[(i + 6) % 7]].forEach((p) => { if (p[1] < p[0] && p[1] > 0) bars += seg(0, p[1], "blk over"); });
      rows += `<div class="wrow${i === this._wkDay ? " sel" : ""}" data-wd="${i}"><span>${names[i]}</span><div class="wbar">${bars}</div></div>`;
    });
    const day = WEEKDAYS[this._wkDay], list = wk[day];
    let edit = list.map((p, j) => `<div class="wper"><button class="mini" data-wp="${j}:0:-15">\u2212</button><b>${this._clock(p[0])}</b>` +
      `<button class="mini" data-wp="${j}:0:15">+</button> \u2013 <button class="mini" data-wp="${j}:1:-15">\u2212</button><b>${this._clock(p[1] === 1440 ? 1440 : p[1])}</b>` +
      `<button class="mini" data-wp="${j}:1:15">+</button><button class="mini del" data-wdel="${j}" title="${this._t("w_del")}">\u00d7</button></div>`).join("");
    if (!list.length) edit = `<div class="ts">${this._t("w_empty")}</div>`;
    const msg = this._wkMsg ? `<div class="wmsg ${this._wkMsg.ok ? "ok" : "err"}">${this._wkMsg.text}</div>` : "";
    return `<div class="week"><div class="srow"><span>${this._t("w_title")}</span><span class="wtog">` +
      `<button class="mini${on ? "" : " on"}" data-wmode="0">${this._t("w_off")}</button><button class="mini${on ? " on" : ""}" data-wmode="1">${this._t("w_on")}</button></span></div>` +
      (on || this._wkOpen ? `<div class="wgrid">${rows}<div class="waxis"><span>0</span><span>6</span><span>12</span><span>18</span><span>24</span></div></div>` +
        `<div class="wedit"><div class="ts">${this._t("w_tap")}</div><div class="wday">${names[this._wkDay]}</div>${edit}` +
        `<div class="wbtns"><button class="mini" data-wadd="1">${this._t("w_add")}</button><button class="mini" data-wcopy="wd">${this._t("w_copy_wd")}</button>` +
        `<button class="mini" data-wcopy="we">${this._t("w_copy_we")}</button><button class="mini" data-wcopy="all">${this._t("w_copy_all")}</button>` +
        `<button class="mini save" data-wsave="1">${this._t("w_save")}</button></div>${msg}</div>` : "") + `</div>`;
  }
  _wireWeek() {
    const root = this.shadowRoot, st = this._hass.states[this._config.entity], a = st ? st.attributes : {};
    const redraw = (ev) => { ev.stopPropagation(); this._render(); };
    root.querySelectorAll(".wrow[data-wd]").forEach((r) => r.addEventListener("click", (ev) => { this._wkDay = parseInt(r.dataset.wd, 10); redraw(ev); }));
    root.querySelectorAll("[data-wp]").forEach((b) => b.addEventListener("click", (ev) => {
      const [j, k, d] = b.dataset.wp.split(":").map((x) => parseInt(x, 10)), p = this._weekDraft(a)[WEEKDAYS[this._wkDay]][j];
      let v = p[k] + d;
      if (k === 0) v = (v + 1440) % 1440; else v = v <= 0 ? 1440 : (v > 1440 ? 15 : v);
      if (v !== p[1 - k] && !(k === 0 && v === p[1] % 1440)) p[k] = v;
      this._wkMsg = null; redraw(ev);
    }));
    root.querySelectorAll("[data-wdel]").forEach((b) => b.addEventListener("click", (ev) => {
      this._weekDraft(a)[WEEKDAYS[this._wkDay]].splice(parseInt(b.dataset.wdel, 10), 1); this._wkMsg = null; redraw(ev);
    }));
    root.querySelectorAll("[data-wadd]").forEach((b) => b.addEventListener("click", (ev) => {
      const list = this._weekDraft(a)[WEEKDAYS[this._wkDay]], last = list.length ? Math.max.apply(null, list.map((p) => (p[1] > p[0] ? p[1] : 1440))) : 7 * 60;
      const s = Math.min(1380, last + 60);
      list.push([s, Math.min(1440, s + 120)]); list.sort((x, y) => x[0] - y[0]); this._wkMsg = null; redraw(ev);
    }));
    root.querySelectorAll("[data-wcopy]").forEach((b) => b.addEventListener("click", (ev) => {
      const wk = this._weekDraft(a), src = wk[WEEKDAYS[this._wkDay]], to = { wd: [0, 1, 2, 3, 4], we: [5, 6], all: [0, 1, 2, 3, 4, 5, 6] }[b.dataset.wcopy];
      to.forEach((i) => { if (i !== this._wkDay) wk[WEEKDAYS[i]] = src.map((p) => [p[0], p[1]]); });
      this._wkMsg = null; redraw(ev);
    }));
    root.querySelectorAll("[data-wmode]").forEach((b) => b.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const on = b.dataset.wmode === "1";
      if (on && !a.weekly_comfort) { this._wkOpen = true; this._render(); return; }     // first set the periods, then save
      if (!on && a.weekly_comfort) this._saveWeek({ weekly_comfort: false });
      if (!on) { this._wkOpen = false; this._render(); }
    }));
    root.querySelectorAll("[data-wsave]").forEach((b) => b.addEventListener("click", (ev) => {
      ev.stopPropagation();
      this._saveWeek({ weekly_comfort: true, comfort_schedule: this._weekDraft(a) });
    }));
  }
  _saveWeek(data) {
    const done = (ok, e) => { this._wkMsg = { ok, text: ok ? this._t("w_saved") : this._fill("w_err", { e: (e && e.message) || e || "" }) }; this._render(); };
    Promise.resolve(this._hass.callService("roost_quatt", "set_settings", data)).then(() => { this._wk = null; this._wkOpen = false; done(true); }, (e) => done(false, e));
  }

  _tile(icon, label, v, big, sub, cls) {
    return `<div class="tile ${cls || ""}"><div class="tl"><ha-icon icon="${icon}"></ha-icon>${label}</div>
      <div class="tv${big ? " big" : ""}">${this._num(v, 1)}<span>${DEG}</span></div><div class="ts">${sub}</div></div>`;
  }

  _chart(a) {
    const plan = a.plan, n = plan.length;
    // bars: the import tariff (p[4]; older versions only had the planner's price p[3]); p[5] = 1: not known yet, guessed
    const sp = plan.map((p) => p[0]), kt = plan.map((p) => p[1]), pr = plan.map((p) => nn(p[4], p[3]));
    const guess = plan.map((p) => !!p[5]);
    const day = a.day_hours || plan.map(() => 1);
    const start = a.start ? new Date(a.start) : new Date();
    // one unit is one pixel of the card (fixed text size, a height that does not grow with a wide dashboard)
    const VW = Math.max(300, Math.min(1600, (this._chartW || 472) - 32)), VH = 172, L = 28, R = 6, TOP = 8, B = 46, PB = 26, w = (VW - L - R) / n;
    const vals = sp.concat(kt).filter((v) => !isNaN(v));
    const lo = Math.min(nn(a.night_min, 19) - 0.5, Math.floor(Math.min.apply(null, vals) - 0.3));
    const hi = Math.max(nn(a.store_max, 22.5) + 0.3, Math.ceil(Math.max.apply(null, vals) + 0.3));
    const y = (v) => TOP + (hi - v) / (hi - lo) * (VH - TOP - B), x = (i) => L + i * w;
    const pmin = Math.min.apply(null, pr), pmax = Math.max.apply(null, pr), pb = VH - 18;
    const tone = (p) => { const r = (p - pmin) / Math.max(0.01, pmax - pmin); return r < 0.33 ? "var(--rc-cheap)" : (r < 0.66 ? "var(--rc-mid)" : "var(--rc-dear)"); };
    let g = "";
    const cl = nn(a.day_min, 20), ch = nn(a.comfort, 20.5);
    for (let i = 0; i < n; i++) {
      const mask = a.comfort_masks && a.comfort_masks[i];
      if (mask) {
        for (let q = 0; q < 4; q++) if (mask[q]) g += `<rect x="${(x(i) + q * w / 4).toFixed(1)}" y="${y(ch).toFixed(1)}" width="${(w / 4 + 0.2).toFixed(1)}" height="${Math.max(1, y(cl) - y(ch)).toFixed(1)}" class="band"/>`;
      } else if (day[i]) g += `<rect x="${x(i).toFixed(1)}" y="${y(ch).toFixed(1)}" width="${(w + 0.2).toFixed(1)}" height="${Math.max(1, y(cl) - y(ch)).toFixed(1)}" class="band"/>`;
    }
    for (let v = Math.ceil(lo); v <= hi; v++) {
      g += `<line x1="${L}" x2="${VW - R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" class="grid"/>` +
        `<text x="${L - 5}" y="${(y(v) + 3.5).toFixed(1)}" text-anchor="end" class="axis">${v}\u00b0</text>`;
    }
    const own = a.own_kw || [], omax = Math.max(1, Math.max.apply(null, own.concat([0])));
    own.forEach((o, i) => {          // own solar to use: a yellow wash behind the price bars
      if (o > 0.05 && i < n) g += `<rect x="${x(i).toFixed(1)}" y="${(pb - o / omax * PB).toFixed(1)}" width="${(w + 0.2).toFixed(1)}" height="${(o / omax * PB).toFixed(1)}" class="sun"/>`;
    });
    pr.forEach((p, i) => {
      const r = (p - pmin) / Math.max(0.01, pmax - pmin), hgt = 4 + r * (PB - 8);
      g += `<rect x="${(x(i) + 1).toFixed(1)}" y="${(pb - hgt).toFixed(1)}" width="${(w - 2).toFixed(1)}" height="${hgt.toFixed(1)}" rx="1.5" style="fill:${tone(p)}" class="price${guess[i] ? " guess" : ""}"/>`;
    });
    let d = `M${x(0).toFixed(1)} ${y(sp[0]).toFixed(1)}`;
    sp.forEach((v, i) => { d += ` L${x(i).toFixed(1)} ${y(v).toFixed(1)} L${x(i + 1).toFixed(1)} ${y(v).toFixed(1)}`; });
    let k = "";
    kt.forEach((v, i) => { k += `${i ? " L" : "M"}${(x(i) + w / 2).toFixed(1)} ${y(v).toFixed(1)}`; });
    const area = `${k} L${(x(n - 1) + w / 2).toFixed(1)} ${VH - B} L${(x(0) + w / 2).toFixed(1)} ${VH - B} Z`;
    g = `<path d="${area}" class="area"/>` + g + `<path d="${d}" class="sp"/><path d="${k}" class="room"/>` +
      `<line x1="${x(0).toFixed(1)}" x2="${x(0).toFixed(1)}" y1="${TOP}" y2="${pb}" class="nowl"/>`;
    for (let i = 0; i <= n; i += 6) {
      const t = new Date(start.getTime() + i * 3600000);
      g += `<text x="${x(i).toFixed(1)}" y="${VH - 4}" text-anchor="${i === 0 ? "start" : (i === n ? "end" : "middle")}" class="axis${i === 0 ? " nowt" : ""}">${i === 0 ? this._t("now") : this._hour(t)}</text>`;
    }
    g += `<line class="cur" x1="0" x2="0" y1="${TOP}" y2="${pb}"/><circle class="dot2" r="3.5"/><circle class="dot" r="4"/>` +
      `<rect class="hit" x="${L}" y="${TOP}" width="${VW - L - R}" height="${pb - TOP}"/>`;
    this._geo = { n, L, w, sp: sp.map((v) => y(v)), kt: kt.map((v) => y(v)), start: start.getTime(), plan, day, why: a.plan_why || [] };
    return `<div class="chart"><div class="ch"><span>${this._t("next24")}</span><span class="info">${this._info(0)} \u00b7 <i>${this._t("scrub")}</i></span></div>
      <svg viewBox="0 0 ${VW} ${VH}">${g}</svg>${this._pumpStrip(plan, L / VW, R / VW)}${a.plan_why ? `<div class="pwhy">${this._pwhy(0)}</div>` : ""}
      <div class="leg"><span><b class="l sp"></b>${this._t("setpoint")}</span><span><b class="l room"></b>${this._t("expected")}</span>
      <span><b class="l price"></b>${this._t("price")}</span>${guess.some((g) => g) ? `<span><b class="l price guess"></b>${this._t("guessed")}</span>` : ""}
      <span><b class="l band"></b>${this._t("comfort")}</span>${own.some((o) => o > 0.05) ? `<span><b class="l sun"></b>${this._t("pr_sun")}</span>` : ""}` +
      (plan.some((p) => (p[2] || 0) > 0.05) ? `<span><b class="l pump"></b>${this._t("pump_on")}</span>` : "") + `</div></div>`;
  }

  // the hours the heat pump is expected to heat (planned electricity), as a strip under the graph
  _pumpStrip(plan, l, r) {
    const cells = plan.map((p) => `<i class="${(p[2] || 0) > 0.05 ? "on" : ""}"></i>`).join("");
    return `<div class="pstrip" style="margin-left:${(l * 100).toFixed(2)}%;margin-right:${(r * 100).toFixed(2)}%">${cells}</div>`;
  }

  _info(i) {
    const p = this._geo && this._geo.plan[i];
    if (!p) return "";
    const t = i === 0 ? this._t("now") : this._hour(new Date(this._geo.start + i * 3600000));
    const tariff = nn(p[4], p[3]);
    // the planner may count another price: the battery's refill cost, or own solar
    const uses = Math.abs(p[3] - tariff) >= 0.5 ? ` (${this._t("uses")} ${this._num(p[3], 0)} ct)` : "";
    return `<b>${t}</b> \u00b7 ${this._t("setpoint")} <b class="o">${this._num(p[0], 1)}${DEG}</b> \u00b7 ${this._t("room")} <b>${this._num(p[1], 1)}${DEG}</b>` +
      ` \u00b7 <b>${this._num(tariff, 0)} ct</b>${p[5] ? " " + this._t("guessed") : ""}${uses}${this._geo.day[i] ? "" : " \u00b7 " + this._t("night")}`;
  }

  // why the hour under the finger is what it is (issue #1): the planner's reason for that hour
  _pwhy(i) {
    const r = this._geo && this._geo.why[i];
    if (!r) return "";
    const t = i === 0 ? this._t("now") : this._hour(new Date(this._geo.start + i * 3600000));
    return `<b>${t}</b> \u00b7 ${this._why(r[0], r[1], "")}`;
  }

  _wire() {
    const root = this.shadowRoot, hit = root.querySelector(".hit");
    root.querySelectorAll(".seg span[data-v]").forEach((s) => s.addEventListener("click", (ev) => {
      ev.stopPropagation();
      this._view = s.dataset.v;
      this._render();
    }));
    root.querySelectorAll(".pill.modebtn").forEach((pl) => pl.addEventListener("click", (ev) => {
      ev.stopPropagation(); this._modeOpen = !this._modeOpen; this._armed = null; this._render();
    }));
    root.querySelectorAll(".mopt[data-m]").forEach((b) => b.addEventListener("click", (ev) => {     // not the Settings button
      ev.stopPropagation();
      const m = b.dataset.m;
      if (m === "active" && this._armed !== "active") { this._armed = "active"; b.querySelector("small").textContent = this._t("mo_sure"); return; }
      if (m === "resume") this._hass.callService("roost_quatt", "resume", {});
      else if (m === "pause") this._hass.callService("roost_quatt", "pause", { hours: 2 });
      else if (m === "home") this._hass.callService("roost_quatt", "home", {});
      else this._hass.callService("select", "select_option", { entity_id: this._siblings().mode, option: m });
      this._modeOpen = false; this._armed = null; this._render();
    }));
    root.querySelectorAll(".head .ico, .week-settings").forEach((ico) => ico.addEventListener("click", (ev) => {
      ev.stopPropagation();
      window.history.pushState(null, "", "/config/integrations/integration/roost");
      window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
    }));
    const th = root.querySelector(".tile.therm");
    if (th) th.addEventListener("click", (ev) => {      // the thermostat's own controls (Home Assistant's dialog)
      ev.stopPropagation();
      const st = this._hass.states[this._config.entity];
      const e = new Event("hass-more-info", { bubbles: true, composed: true });
      e.detail = { entityId: st && st.attributes.thermostat_entity };
      this.dispatchEvent(e);
    });
    root.querySelectorAll(".mini[data-away]").forEach((b) => b.addEventListener("click", (ev) => {
      ev.stopPropagation();
      this._hass.callService("roost_quatt", "away", { days: parseFloat(b.dataset.away) });
      this._modeOpen = false; this._render();
    }));
    this._wireWeek();
    root.querySelectorAll(".calpill").forEach((c) => c.addEventListener("click", (ev) => {
      ev.stopPropagation(); this._calOpen = !this._calOpen; this._calDay = null; this._render();
    }));
    root.querySelectorAll(".cd[data-day]").forEach((c) => c.addEventListener("click", (ev) => {
      ev.stopPropagation();
      if (!c.classList.contains("bad")) return;
      this._calDay = !(this._calDay && this._calDay.day === c.dataset.day) ? { day: c.dataset.day, why: c.dataset.why } : null;
      this._render();
    }));
    const sb = root.querySelector(".setbtn");
    if (sb) sb.addEventListener("click", (ev) => { ev.stopPropagation(); this._setOpen = !this._setOpen; this._render(); });
    root.querySelectorAll(".mini[data-set]").forEach((b) => b.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const st = this._hass.states[this._config.entity], key = b.dataset.set, cur = st && parseFloat(st.attributes[key]);
      if (isNaN(cur)) return;
      const lim = { comfort: [15, 25], day_min: [10, 25], night_min: [5, 25], store_max: [15, 28], lowest_setpoint: [5, 25], day_from: [0, 23], day_to: [1, 24] }[key];
      const v = Math.min(lim[1], Math.max(lim[0], cur + parseFloat(b.dataset.d)));
      if (key === "day_from" && v >= parseInt(st.attributes.day_to, 10)) return;
      if (key === "day_to" && v <= parseInt(st.attributes.day_from, 10)) return;
      this._hass.callService("roost_quatt", "set_settings", { [key]: v });
    }));
    const tp = root.querySelector(".tile.plan");
    if (tp && this._histOn()) tp.addEventListener("click", (ev) => { ev.stopPropagation(); this._view = "table"; this._render(); });
    root.querySelectorAll(".mini[data-room]").forEach((b) => b.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const st = this._sib("heating_curve"), base = st && parseFloat(st.attributes.room);
      const cur = this._curveRoom !== undefined ? this._curveRoom : base;
      if (isNaN(cur)) return;
      this._curveRoom = Math.min(24, Math.max(16, cur + parseFloat(b.dataset.room)));
      this._render();
    }));
    if (this._view === "curve" && this._histOn()) return;
    if (this._view === "table" && this._histOn()) {
      root.querySelectorAll("details.tday").forEach((d) => d.addEventListener("toggle", () => {
        this._tblOpen = Object.assign({}, this._tblOpen, { [d.dataset.day]: d.open });
      }));
      return;
    }
    if (this._view === "history" && this._histOn()) { this._wireHist(); return; }
    const steer = root.querySelector(".steer");
    if (steer) {
      steer.addEventListener("click", (ev) => {
        ev.stopPropagation();
        if (!steer.dataset.armed) {
          steer.dataset.armed = "1";
          steer.textContent = this._t("sure");
          setTimeout(() => { if (steer.isConnected) { delete steer.dataset.armed; steer.textContent = this._t("steer"); } }, 5000);
          return;
        }
        this._hass.callService("select", "select_option", { entity_id: this._siblings().mode, option: "active" });
      });
    }
    const cv = root.querySelector("details.curve");
    if (cv) cv.addEventListener("toggle", () => { this._curveOpen = cv.open; });
    if (!hit || !this._geo) return;
    const move = (ev) => {
      const r = hit.getBoundingClientRect();
      const cx = ev.touches && ev.touches.length ? ev.touches[0].clientX : ev.clientX;
      const i = Math.max(0, Math.min(this._geo.n - 1, Math.floor((cx - r.left) / r.width * this._geo.n)));
      const xx = this._geo.L + (i + 0.5) * this._geo.w;
      const cur = root.querySelector(".cur"), dot = root.querySelector(".dot"), dot2 = root.querySelector(".dot2");
      cur.setAttribute("x1", xx); cur.setAttribute("x2", xx);
      dot.setAttribute("cx", xx); dot.setAttribute("cy", this._geo.kt[i]);
      dot2.setAttribute("cx", xx); dot2.setAttribute("cy", this._geo.sp[i]);
      root.querySelector(".chart").classList.add("on");
      root.querySelector(".info").innerHTML = this._info(i);
      const pw = root.querySelector(".pwhy");
      if (pw) pw.innerHTML = this._pwhy(i);
    };
    hit.addEventListener("pointermove", move);
    hit.addEventListener("pointerdown", move);
    hit.addEventListener("touchmove", move, { passive: true });
  }

  _footer(a) {
    const s24 = this._sib("saving_next_24h"), sm = this._sib("saving_month"), sy = this._sib("saving_yesterday");
    const bits = [];
    if (s24 && !isNaN(parseFloat(s24.state))) bits.push(`${this._t("saving24")} <b>${this._money(parseFloat(s24.state))}</b>`);
    if (sy && !isNaN(parseFloat(sy.state))) bits.push(`${this._t("yesterday")} <b>${this._money(parseFloat(sy.state))}</b>`);
    if (sm && !isNaN(parseFloat(sm.state))) bits.push(`${this._t("month")} <b>${this._money(parseFloat(sm.state))}</b>`);
    if (a.cost_24h !== undefined && a.cost_24h !== null) bits.push(`24 h ${this._money(a.cost_24h)} (${this._t("vs")} ${this._money(a.steady_cost_24h)})`);
    const acc = this._sib("plan_accuracy");          // nightly self-check: the room 6 hours ahead
    if (acc && !isNaN(parseFloat(acc.state))) {
      bits.push(`${this._t("accuracy")} <b>\u00b1${this._num(parseFloat(acc.state), 2)} ${DEG}</b>` +
        (acc.attributes.ready_to_steer && a.mode === "shadow" ? ` \u00b7 <b class="ok">${this._t("ready")}</b>` : ""));
    }
    // the import from the statistics while it runs: months in and the expected end
    const imp = this._sib("history_import"), prog = this._sib("import_progress");
    if (imp && imp.state === "importing" && prog) {
      const pa = prog.attributes, end = pa.expected_done ? new Date(pa.expected_done) : null;
      bits.push(`${this._t("importing")} <b>${pa.months_done}/${pa.months}</b> ${this._t("months")}` +
        (end && !isNaN(end) ? `, ${this._t("done_at")} ~${this._hm(end)}` : ""));
    }
    // not ready yet, still in shadow: when Roost expects to be (ready sensor, nightly self-check)
    const ready = this._sib("ready");
    const code = ready && ready.state !== "on" && a.mode === "shadow" ? ready.attributes.waiting_for : null;
    const eta = code ? this._t("eta")[code] : null;
    if (eta) {
      const when = ready.attributes.expected ? new Date(ready.attributes.expected) : null;
      const hm = when && !isNaN(when) ? ` ~${this._hm(when)}` : "";
      bits.push(`${this._t("ready")}: ${eta}${hm}`);
    }
    return bits.length ? `<div class="foot">${bits.join(" \u00b7 ")}</div>` : "";
  }

  // ---------------------------------------------------------------- mode menu (tap the mode label)
  _modeMenu(mode, paused, away, a) {
    const opt = (m) => `<button class="mopt${m === mode ? " on" : ""}" data-m="${m}"><b>${this._t("mo_" + m)}</b>` +
      `<small>${this._armed === m ? this._t("mo_sure") : this._t("mh_" + m)}</small></button>`;
    return `<div class="mmenu">${paused ? `<button class="mopt" data-m="resume"><b>${this._t("mo_resume")}</b><small>&nbsp;</small></button>` : ""}` +
      `${opt("off")}${opt("shadow")}${opt("active")}${mode === "active" && !paused ? opt("pause") : ""}` +
      (mode === "active" ? (away ? `<button class="mopt" data-m="home"><b>${this._t("mo_home")}</b><small>${this._t("mh_home")}</small></button>`
        : `<div class="mrow"><b>${this._t("mo_away")}</b><span>${[1, 3, 7].map((d) => `<button class="mini" data-away="${d}">${this._t("away_" + d)}</button>`).join("")}</span>` +
          `<small>${this._t("mh_away").replace("{min}", this._num(16, 0))}</small></div>`) : "") +
      `<button class="mopt setbtn${this._setOpen ? " on" : ""}"><b><ha-icon icon="mdi:cog-outline"></ha-icon> ${this._t("set_btn")}</b></button>` +
      (this._setOpen && a ? this._settingsPanel(a) : "") + `</div>`;
  }

  // All temperatures and the comfort hours, each with - / +: Roost's own settings (the same as Configure -> Comfort)
  _settingsPanel(a) {
    const row = (key, label, v, step, unit) => `<div class="srow"><span>${this._t(label)}</span><span>` +
      `<button class="mini" data-set="${key}" data-d="${-step}">\u2212</button><b class="sv">${unit === "h" ? `${v}:00` : `${this._num(v, 1)}${DEG}`}</b>` +
      `<button class="mini" data-set="${key}" data-d="${step}">+</button></span></div>`;
    return `<div class="spanel">` +
      row("comfort", "s_comfort", a.comfort, 0.5) + row("day_min", "s_day_min", a.day_min, 0.5) + row("night_min", "s_night_min", a.night_min, 0.5) +
      (a.weekly_comfort ? "" :
       (`<div class="srow"><span>${this._t("s_hours")}</span><span><button class="mini" data-set="day_from" data-d="-1">\u2212</button>` +
      `<b class="sv">${a.day_from}:00</b><button class="mini" data-set="day_from" data-d="1">+</button> \u2013 ` +
      `<button class="mini" data-set="day_to" data-d="-1">\u2212</button><b class="sv">${a.day_to}:00</b>` +
      `<button class="mini" data-set="day_to" data-d="1">+</button></span></div>`)) +
      this._weekEditor(a) +
      row("lowest_setpoint", "s_lowest", a.lowest_setpoint, 0.5) + row("store_max", "s_store", a.store_max, 0.5) + `</div>`;
  }

  // ---------------------------------------------------------------- table: the plan ahead and the last 7 days per hour
  _priceHorizon(a) {
    if (!a.price_limited_until) return "";
    const until = new Date(a.price_limited_until);
    if (isNaN(until.getTime())) return "";
    const time = until.toLocaleString(this._locale(), { weekday: "short", hour: "2-digit", minute: "2-digit" });
    return (PRICE_HORIZON[this._lang()] || PRICE_HORIZON.en).replace("{time}", time);
  }

  _savingQuality(q) {
    if (!q) return "";
    const lang = String(this._locale()).split("-")[0];
    const text = SAVING_QUALITY[lang] || SAVING_QUALITY.en;
    if (q.valid) return q.status === "validated_estimate" ? text.checked : text.forecast;
    return text.unreliable + " " + (q.reasons || []).map((r) => text[r] || text.unreliable).join(" ");
  }

  // Hours in a row with the same setting and the same reason are one line, so the table stays short.
  _runs(list, same) {
    const out = [];
    list.forEach((x) => { const r = out[out.length - 1]; if (r && same(r.items[r.items.length - 1], x)) r.items.push(x); else out.push({ items: [x] }); });
    return out;
  }
  _span(t0, n) {
    const a = this._hour(new Date(t0 * 1000));
    return n > 1 ? `${a}\u2013${this._hour(new Date((t0 + n * 3600) * 1000))}` : a;
  }
  _range2(a, b, d) {    // "20,7" or "20,7\u2192 20,3"
    return a === null || a === undefined ? "\u2014" : (b === null || b === undefined || Math.abs(a - b) < 0.05 ? this._num(a, d) : `${this._num(a, d)}\u2192${this._num(b, d)}`);
  }
  // Where the heat pump's electricity came from (own solar, battery, grid), over the given hours of the log
  _srcLine(hours) {
    const sum = (k) => hours.reduce((t, h) => t + (h[k] || 0), 0);
    const sun = sum("e_sun"), bat = sum("e_bat"), grid = sum("e_grid"), tot = sun + bat + grid;
    if (tot < 0.05) return "";
    const pc = (v) => `${this._num(100 * v / tot, 0)}%`;
    return `<div class="srcl"><span class="sbar"><i class="ss" style="width:${100 * sun / tot}%"></i><i class="sb" style="width:${100 * bat / tot}%"></i>` +
      `<i class="sg" style="width:${100 * grid / tot}%"></i></span>${this._t("src_title")} ${this._num(tot, 1)} kWh: ` +
      `<b class="ss">${this._t("src_sun")} ${pc(sun)}</b> \u00b7 <b class="sb">${this._t("src_bat")} ${pc(bat)}</b> \u00b7 <b class="sg">${this._t("src_grid")} ${pc(grid)}</b></div>`;
  }

  _tableBody(a) {
    return `<div class="ptable">${this._tableAhead(a)}${this._tableBack()}</div>`;
  }
  _tableAhead(a) {
    const plan = a.plan || [], why = a.plan_why || [];
    if (!plan.length) return `<div class="na">${this._t("noplan")}</div>`;
    const start = Math.floor((a.start ? new Date(a.start).getTime() : Date.now()) / 1000);
    const hrs = plan.map((p, i) => ({ ts: start + i * 3600, sp: p[0], room: p[1], kwh: p[2], tariff: nn(p[4], p[3]), guess: !!p[5], why: why[i] || null }));
    const tar = hrs.map((h) => h.tariff).sort((x, y) => x - y), lo = tar[Math.floor(tar.length / 3)], hi = tar[Math.floor(2 * tar.length / 3)];
    const tone = (v) => (v <= lo ? "cheap" : (v >= hi ? "dear" : "mid"));
    const runs = this._runs(hrs, (x, y) => x.sp === y.sp && (x.why && x.why[0]) === (y.why && y.why[0]));
    let prev = null, rows = "";
    runs.forEach((r, k) => {
      const f = r.items[0], l = r.items[r.items.length - 1], n = r.items.length;
      const avg = r.items.reduce((t, h) => t + h.tariff, 0) / n, kwh = r.items.reduce((t, h) => t + (h.kwh || 0), 0);
      const arrow = prev === null || f.sp === prev ? "" : (f.sp > prev ? " \u2191" : " \u2193");
      const t = k === 0 ? `${this._t("now")} ${this._span(f.ts, n)}` : this._span(f.ts, n);
      rows += `<div class="tr${k === 0 ? " now" : ""}"><span>${t}</span><b class="o">${this._num(f.sp, 1)}${arrow}</b>` +
        `<span>${this._range2(f.room, l.room, 1)}</span><span class="pr ${tone(avg)}${f.guess ? " guess" : ""}">${this._num(avg, 0)} ct</span>` +
        `<span>${kwh >= 0.05 ? this._num(kwh, 1) : "\u2013"}</span>` +
        `<div class="tw">${f.why ? this._why(f.why[0], f.why[1], "") : ""}</div></div>`;
      prev = f.sp;
    });
    return `<div class="tsec">${this._t("next24")}</div><div class="tr th"><span>${this._t("t_time")}</span><span>${this._t("t_set")}</span>` +
      `<span>${this._t("t_room")} ${this._t("t_exp")}</span><span>${this._t("price")}</span><span>kWh</span></div>${rows}`;
  }
  _tableBack() {
    if (!this._hist || Date.now() - (this._histAt || 0) > 300000) this._fetchHist();
    if (!this._hist) return `<div class="tsec">${this._t("t_back7")}</div><div class="na">${this._histErr || this._t("h_loading")}</div>`;
    const d = this._hist, hours = (d.hours || []).slice().sort((x, y) => y.ts - x.ts);
    if (!hours.length) return "";
    const key = (ts) => { const t = new Date(ts * 1000); return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`; };
    const hand = new Set((d.events || []).filter((e) => e.kind === "by_hand").map((e) => Math.floor(new Date(e.t).getTime() / 3600000) * 3600));
    const byDay = {};
    hours.forEach((h) => { (byDay[key(h.ts)] = byDay[key(h.ts)] || []).push(h); });
    const today = key(Date.now() / 1000);
    let html = `<div class="tsec">${this._t("t_back7")}</div>`;
    Object.keys(byDay).sort().reverse().forEach((day) => {
      const hs = byDay[day].slice().sort((x, y) => x.ts - y.ts);
      const ds = (d.days || {})[day];
      const open = this._tblOpen && this._tblOpen[day] !== undefined ? this._tblOpen[day] : day === today;
      const label = day === today ? this._t("t_today") : new Date(day + "T12:00:00").toLocaleDateString(this._locale(), { weekday: "short", day: "numeric", month: "short" });
      const sum = ds ? ` <span>${this._money(ds.cost)}${ds.saving !== undefined && ds.saving !== null ? ` \u00b7 ${this._t("h_saving")} ${this._money(ds.saving)}` : ""}` +
        `${ds.pred_mae !== null && ds.pred_mae !== undefined ? ` \u00b7 ${this._t("h_pred")} \u00b1${this._num(ds.pred_mae, 1)}` : ""}</span>` : "";
      let loss = "";
      if (ds && ds.quality && !ds.quality.valid) {
        loss = `<div class="tloss">${this._savingQuality(ds.quality)}</div>`;
      } else if (ds && ds.saving !== undefined && ds.saving !== null && ds.saving < -0.05) {      // why a day cost more than a steady thermostat
        const stored = hs.filter((h) => String(h.reason || "").startsWith("store_")).length;
        const top = Math.max.apply(null, hs.map((h) => h.T));
        loss = `<div class="tloss">${stored ? this._t("t_loss_store").replace("{h}", stored).replace("{max}", this._num(top, 1)) : this._t("t_loss_other")}</div>`;
      }
      const runs = this._runs(hs, (x, y) => x.sp_t === y.sp_t && x.sp_plan === y.sp_plan && x.reason === y.reason && !hand.has(y.ts) && !!x.window === !!y.window);
      let rows = "";
      runs.forEach((r) => {
        const f = r.items[0], l = r.items[r.items.length - 1], n = r.items.length;
        // electricity, as in the plan above (not the heat delivered: three to four times as much, not comparable)
        const price = r.items.reduce((t, h) => t + (h.p_grid || 0), 0) / n * 100, elec = r.items.reduce((t, h) => t + (h.e || 0), 0);
        const set = f.sp_plan !== null && f.sp_plan !== undefined && Math.abs(f.sp_plan - f.sp_t) >= 0.25
          ? `${this._num(f.sp_plan, 1)}\u2192${this._num(f.sp_t, 1)}` : this._num(f.sp_t, 1);
        const marks = (hand.has(f.ts) ? ` <i class="mk">${this._t("h_byhand")}</i>` : "") + (f.window ? ` <i class="mk">${this._t("h_window")}</i>` : "");
        const pred = f.p6 !== null && f.p6 !== undefined ? ` <small>(${this._t("t_exp")} ${this._num(f.p6, 1)})</small>` : "";
        rows += `<div class="tr"><span>${this._span(f.ts, n)}</span><b class="o">${set}</b><span>${this._range2(f.T, l.T, 1)}${pred}</span>` +
          `<span class="pr">${this._num(price, 0)} ct</span><span>${elec >= 0.05 ? this._num(elec, 1) : "\u2013"}</span>` +
          `<div class="tw">${f.reason ? this._why(f.reason, f.args || {}, "") : ""}${marks}</div></div>`;
      });
      html += `<details class="tday" data-day="${day}"${open ? " open" : ""}><summary><b>${label}</b>${sum}</summary>${loss}${this._srcLine(hs)}` +
        `<div class="tr th"><span>${this._t("t_time")}</span><span>${this._t("t_set")}</span><span>${this._t("t_room")}</span>` +
        `<span>${this._t("price")}</span><span>kWh</span></div>${rows}</details>`;
    });
    return html;
  }

  // ---------------------------------------------------------------- look back (websocket roost_quatt/history)
  _histOn() { return this._config.history !== false && !this._config.compact; }

  _fetchHist() {
    if (this._loading || !this._hass) return;
    this._loading = true;
    this._hass.callWS({ type: "roost_quatt/history", entity_id: this._config.entity, days: 7 }).then((d) => {
      this._hist = d; this._histAt = Date.now(); this._histErr = null; this._loading = false; this._render();
    }).catch((e) => { this._histErr = String((e && e.message) || e); this._loading = false; this._render(); });
  }

  _histSlice() {
    const d = this._hist || { hours: [], events: [], days: {} };
    const t1 = Math.floor(Date.now() / 3600000) * 3600 + 3600, t0 = t1 - this._range * 3600;
    const hours = d.hours.filter((h) => h.ts >= t0 && h.ts < t1);
    const evTs = (e) => new Date(e.t).getTime() / 1000;
    const events = d.events.filter((e) => evTs(e) >= t0 && evTs(e) < t1).map((e) => Object.assign({ ts: evTs(e) }, e));
    return { d, t0, t1, hours, events };
  }

  _histBody() {
    if (!this._hist || Date.now() - (this._histAt || 0) > 300000) this._fetchHist();
    if (!this._hist) return `<div class="na">${this._histErr || this._t("h_loading")}</div>`;
    const s = this._histSlice();
    if (!s.hours.length) return this._rangeBar() + `<div class="na">${this._t("h_nodata")}</div>`;
    return this._rangeBar() + this._histTiles(s) + this._srcLine(s.hours) + this._histChart(s) + this._histLog(s);
  }

  _rangeBar() {
    const r = (v, l) => `<span data-r="${v}" class="${this._range === v ? "on" : ""}">${l}</span>`;
    return `<div class="hbar"><div class="seg rng">${r(24, "24 h")}${r(48, "48 h")}${r(168, "7 d")}</div>` +
      `<button class="rep"><ha-icon icon="mdi:file-download-outline"></ha-icon>${this._t("h_report")}</button></div>`;
  }

  _histStats(s) {
    const comfort = nn(s.d.comfort, 20.5);
    const costed = s.hours.filter((h) => h.cost !== undefined && h.cost !== null);
    const cost = costed.length ? costed.reduce((t, h) => t + h.cost, 0) : null;
    const days = Object.keys(s.d.days || {}).filter((k) => new Date(k + "T12:00:00").getTime() / 1000 >= s.t0);
    const sav = days.map((k) => s.d.days[k].saving).filter((v) => v !== undefined && v !== null);
    const errs = s.hours.filter((h) => h.p6 !== null && h.p6 !== undefined).map((h) => ({ ts: h.ts, e: h.T - h.p6 }));
    const mae = errs.length ? errs.reduce((t, x) => t + Math.abs(x.e), 0) / errs.length : null;
    const worst = errs.reduce((m, x) => (!m || Math.abs(x.e) > Math.abs(m.e) ? x : m), null);
    const dayH = s.hours.filter((h) => h.day);
    const below = dayH.filter((h) => !h.away && h.T < comfort - 0.3)
      .reduce((n, h) => n + (h.comfort_mask ? 15 * h.comfort_mask.filter(Boolean).length : 60), 0);
    const low = s.hours.length ? Math.min.apply(null, s.hours.map((h) => h.T)) : null;
    let roost = 0;
    for (let i = 1; i < s.hours.length; i++) {
      const a = s.hours[i - 1].sp_t, b = s.hours[i].sp_t;
      if (a !== null && b !== null && a !== undefined && b !== undefined && Math.abs(a - b) >= 0.25) roost++;
    }
    const hand = s.events.filter((e) => e.kind === "by_hand").length;
    return { cost, sav: sav.length ? sav.reduce((t, v) => t + v, 0) : null, mae, worst, below, low, roost: Math.max(0, roost - hand), hand };
  }

  _histTiles(s) {
    const st = this._histStats(s);
    const tile = (label, value, sub) => `<div class="tile htile"><div class="tl">${label}</div><div class="tv">${value}</div><div class="ts">${sub}</div></div>`;
    return `<div class="tiles four">` +
      tile(this._t("h_cost"), st.cost !== null ? this._money(st.cost) : "\u2014", st.sav !== null ? `${this._t("h_saving")} ${this._money(st.sav)}` : "&nbsp;") +
      tile(this._t("h_pred"), st.mae !== null ? `\u00b1 ${this._num(st.mae, 1)}<span>${DEG}</span>` : "\u2014",
        st.worst ? `${this._t("h_largest")} ${this._num(Math.abs(st.worst.e), 1)} (${this._hour(new Date(st.worst.ts * 1000))})` : "&nbsp;") +
      tile(this._t("h_below"), `${st.below}<span>min</span>`, st.low !== null ? `${this._t("h_lowest")} ${this._num(st.low, 1)} ${DEG}` : "&nbsp;") +
      tile(this._t("h_changes"), `${st.roost} + ${st.hand}`, `${this._t("h_byroost")} \u00b7 ${this._t("h_byhand")}`) + `</div>`;
  }

  _histChart(s) {
    const VW = 440, VH = 190, L = 28, R = 6, TOP = 14, B = 58, n = this._range;
    const w = (VW - L - R) / n, x = (ts) => L + (ts - s.t0) / 3600 * w;
    const by = {}; s.hours.forEach((h) => { by[h.ts] = h; });
    const vals = [];
    s.hours.forEach((h) => { [h.T, h.p6, h.sp_t, h.sp_plan].forEach((v) => { if (v !== null && v !== undefined && !isNaN(v)) vals.push(v); }); });
    const lo = Math.floor(Math.min.apply(null, vals) - 0.3), hi = Math.ceil(Math.max.apply(null, vals) + 0.3);
    const y = (v) => TOP + (hi - v) / Math.max(0.5, hi - lo) * (VH - TOP - B);
    const pb = VH - 18, ph = 30;
    const pmax = Math.max(0.01, Math.max.apply(null, s.hours.map((h) => h.p_grid || 0)));
    const qmax = Math.max(0.5, Math.max.apply(null, s.hours.map((h) => h.q || 0)));
    const pmin = Math.min.apply(null, s.hours.map((h) => h.p_grid || 0));
    const tone = (p) => { const r = (p - pmin) / Math.max(0.01, pmax - pmin); return r < 0.33 ? "var(--rc-cheap)" : (r < 0.66 ? "var(--rc-mid)" : "var(--rc-dear)"); };
    let g = "";
    for (let v = Math.ceil(lo); v <= hi; v++) {
      g += `<line x1="${L}" x2="${VW - R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" class="grid"/>` +
        `<text x="${L - 5}" y="${(y(v) + 3.5).toFixed(1)}" text-anchor="end" class="axis">${v}\u00b0</text>`;
    }
    s.hours.forEach((h) => {
      const x0 = x(h.ts);
      if (h.paused) g += `<rect x="${x0.toFixed(1)}" y="${TOP}" width="${(w + 0.2).toFixed(1)}" height="${(pb - TOP).toFixed(1)}" class="hpause"/>`;
      const p = h.p_grid || 0, q = h.q || 0, bw = Math.max(0.6, w / 2 - 0.6);
      const hp = 3 + p / pmax * (ph - 3), hq = q / qmax * (ph - 3);
      g += `<rect x="${(x0 + 0.3).toFixed(1)}" y="${(pb - hp).toFixed(1)}" width="${bw.toFixed(1)}" height="${hp.toFixed(1)}" style="fill:${tone(p)}" class="price"/>`;
      if (hq > 0.2) g += `<rect x="${(x0 + w / 2).toFixed(1)}" y="${(pb - hq).toFixed(1)}" width="${bw.toFixed(1)}" height="${hq.toFixed(1)}" class="hheat"/>`;
    });
    const step = (key) => {
      let d = "", pen = false;
      s.hours.forEach((h) => {
        const v = h[key];
        if (v === null || v === undefined) { pen = false; return; }
        d += `${pen ? " L" : " M"}${x(h.ts).toFixed(1)} ${y(v).toFixed(1)} L${(x(h.ts) + w).toFixed(1)} ${y(v).toFixed(1)}`;
        pen = !!by[h.ts + 3600];
      });
      return d;
    };
    const line = (key) => {
      let d = "", pen = false;
      s.hours.forEach((h) => {
        const v = h[key];
        if (v === null || v === undefined) { pen = false; return; }
        d += `${pen ? " L" : " M"}${(x(h.ts) + w / 2).toFixed(1)} ${y(v).toFixed(1)}`;
        pen = !!by[h.ts + 3600];
      });
      return d;
    };
    g += `<path d="${step("sp_plan")}" class="hplan"/><path d="${step("sp_t")}" class="sp"/>` +
      `<path d="${line("p6")}" class="hpred"/><path d="${line("T")}" class="hroom"/>`;
    s.events.forEach((e) => {
      const tag = e.kind === "by_hand" ? "H" : (e.kind === "mode" ? "M" : (e.kind === "window" && e.phase === "open" ? this._t("h_win_mark") : ""));
      if (!tag) return;
      const xx = Math.max(L + 6, Math.min(VW - R - 6, x(e.ts)));
      g += `<circle cx="${xx.toFixed(1)}" cy="${TOP - 5}" r="5.5" class="hmark"/><text x="${xx.toFixed(1)}" y="${TOP - 2}" text-anchor="middle" class="hmt">${tag}</text>`;
    });
    s.hours.forEach((h) => {
      if (h.p6 !== null && h.p6 !== undefined && Math.abs(h.T - h.p6) >= 0.5) {
        g += `<circle cx="${(x(h.ts) + w / 2).toFixed(1)}" cy="${y(h.T).toFixed(1)}" r="3" class="hdev"/>`;
      }
    });
    const every = n <= 24 ? 6 : (n <= 48 ? 12 : 24);
    for (let i = 0; i <= n; i += every) {
      const t = new Date((s.t0 + i * 3600) * 1000);
      const lab = n > 48 ? t.toLocaleDateString(this._lang(), { weekday: "short" }) : this._hour(t);
      g += `<text x="${(L + i * w).toFixed(1)}" y="${VH - 4}" text-anchor="${i === 0 ? "start" : (i === n ? "end" : "middle")}" class="axis">${lab}</text>`;
    }
    g += `<line class="cur" x1="0" x2="0" y1="${TOP}" y2="${pb}"/><rect class="hit" x="${L}" y="${TOP}" width="${VW - L - R}" height="${pb - TOP}"/>`;
    this._hgeo = { L, w, n, t0: s.t0, by };
    const last = s.hours[s.hours.length - 1];
    return `<div class="chart hchart"><div class="ch"><span>${this._t("back")}</span><span class="info">${this._hinfo(last)} \u00b7 <i>${this._t("scrub")}</i></span></div>
      <svg viewBox="0 0 ${VW} ${VH}">${g}</svg>
      <div class="leg"><span><b class="l sp"></b>${this._t("h_sp_t")}</span><span><b class="l hplan"></b>${this._t("h_sp_p")}</span>
      <span><b class="l hroom"></b>${this._t("h_room")}</span><span><b class="l hpred"></b>${this._t("h_pred6")}</span>
      <span><b class="l price"></b>${this._t("price")}</span><span><b class="l hheat"></b>${this._t("h_heat")}</span></div></div>`;
  }

  _hinfo(h) {
    if (!h) return "";
    const t = this._hour(new Date(h.ts * 1000));
    const why = h.reason ? this._why(h.reason, h.args || {}, "") : "";
    const pred = h.p6 !== null && h.p6 !== undefined ? ` (${this._t("h_expected")} ${this._num(h.p6, 1)})` : "";
    return `<b>${t}</b> \u00b7 ${this._t("h_sp_p")} <b class="o">${this._num(h.sp_plan, 1)}${DEG}</b> / ${this._num(h.sp_t, 1)}${DEG}` +
      ` \u00b7 ${this._t("room")} <b>${this._num(h.T, 1)}${DEG}</b>${pred} \u00b7 <b>${this._num((h.p_grid || 0) * 100, 0)} ct</b>` +
      ` \u00b7 ${this._num(h.q || 0, 1)} kWh${why ? " \u00b7 " + why : ""}`;
  }

  _histItems(s) {
    const items = [];
    const by = {}; s.hours.forEach((h) => { by[h.ts] = h; });
    // what happened next: the room an hour later against what the plan expected for it
    const outcome = (ts) => {
      const nx = by[Math.floor(ts / 3600) * 3600 + 3600];
      if (!nx || nx.p1 === null || nx.p1 === undefined) return { out: "", cls: "" };
      const ok = Math.abs(nx.T - nx.p1) <= 0.3;
      return { out: `${this._t("h_room_after")} ${this._num(nx.T, 1)} (${this._t("h_expected")} ${this._num(nx.p1, 1)}) ${ok ? "\u2713" : "\u00b7 " + this._t("h_dev")}`,
               cls: ok ? "ok" : "warn" };
    };
    // shadow mode: what Roost would have set (the plan changed); active mode: what it did set (below)
    for (let i = 1; i < s.hours.length; i++) {
      const a = s.hours[i - 1], h = s.hours[i];
      if (h.mode !== "shadow" || a.sp_plan === null || h.sp_plan === null || a.sp_plan === undefined || h.sp_plan === undefined ||
          Math.abs(a.sp_plan - h.sp_plan) < 0.25) continue;
      items.push(Object.assign({ ts: h.ts, what: `\u2192 ${this._num(h.sp_plan, 1)}${DEG}`, why: this._why(h.reason, h.args || {}, "") }, outcome(h.ts)));
    }
    s.events.forEach((e) => {
      if (e.kind === "set") {
        // older events have no values for the reason: leave the parts that need them out
        const why = e.args ? this._why(e.reason, e.args, "") : this._why(e.reason, {}, "").replace(/\s*\([^()]*\{\w+\}[^()]*\)|\s*\{\w+\}\S*/g, "");
        items.push(Object.assign({ ts: e.ts, what: `\u2192 ${this._num(e.new, 1)}${DEG}`, why }, outcome(e.ts)));
      }
      else if (e.kind === "by_hand") items.push({ ts: e.ts, what: `\u2192 ${this._num(e.new, 1)}${DEG}`, why: this._t("h_set_hand").replace("{h}", this._num(e.pause_h || 2, 0)), out: "", cls: "", hand: true });
      else if (e.kind === "pause") items.push({ ts: e.ts, what: "", why: this._t("h_pause_ev").replace("{h}", this._num(e.hours, 1)), out: "", cls: "", hand: true });
      else if (e.kind === "window") items.push({ ts: e.ts, what: "", why: this._t(e.phase === "open" ? "h_window" : "h_window_end") +
        (e.phase === "open" && e.before !== undefined && e.before !== null && e.room !== null && e.room !== undefined ?
          ` (${this._num(e.before, 1)} \u2192 ${this._num(e.room, 1)}${DEG})` : ""), out: "", cls: "", hand: e.phase === "open" });
      else if (e.kind === "resume") items.push({ ts: e.ts, what: "", why: this._t("h_resume"), out: "", cls: "" });
      else if (e.kind === "mode") items.push({ ts: e.ts, what: "", why: `${this._t("h_mode")}: ${this._t(e.new) || e.new}`, out: "", cls: "" });
      else if (e.kind === "learned" && String(e.house || "").indexOf("adopted") >= 0) items.push({ ts: e.ts, what: "", why: this._t("h_learned"), out: "", cls: "" });
    });
    return items.sort((a, b) => b.ts - a.ts);
  }

  _histLog(s) {
    const items = this._histItems(s);
    const when = (ts) => {
      const d = new Date(ts * 1000);
      return (this._range > 24 && d.toDateString() !== new Date().toDateString() ? d.toLocaleDateString(this._lang(), { weekday: "short" }) + " " : "") + this._hour(d);
    };
    const rows = this._logOpen ? items.slice(0, 60).map((it) => `<div class="lrow"><span>${when(it.ts)}</span><span>${it.what}</span>` +
      `<span class="${it.hand ? "warn" : "mut"}">${it.why}</span><span class="${it.cls}">${it.out}</span></div>`).join("") : "";
    return `<div class="hlog"><div class="lhead">${this._t("h_log")} (${items.length}) ${this._logOpen ? "\u25be" : "\u25b8"}</div>${rows}</div>`;
  }

  _wireHist() {
    const root = this.shadowRoot;
    root.querySelectorAll(".rng span").forEach((sp) => sp.addEventListener("click", (ev) => {
      ev.stopPropagation(); this._range = parseInt(sp.dataset.r, 10); this._render();
    }));
    const lh = root.querySelector(".lhead");
    if (lh) lh.addEventListener("click", (ev) => { ev.stopPropagation(); this._logOpen = !this._logOpen; this._render(); });
    const rep = root.querySelector(".rep");
    if (rep) rep.addEventListener("click", (ev) => { ev.stopPropagation(); this._report(); });
    const hit = root.querySelector(".hchart .hit");
    if (!hit || !this._hgeo) return;
    const move = (ev) => {
      const r = hit.getBoundingClientRect();
      const cx = ev.touches && ev.touches.length ? ev.touches[0].clientX : ev.clientX;
      const i = Math.max(0, Math.min(this._hgeo.n - 1, Math.floor((cx - r.left) / r.width * this._hgeo.n)));
      const h = this._hgeo.by[this._hgeo.t0 + i * 3600];
      const xx = this._hgeo.L + (i + 0.5) * this._hgeo.w;
      const cur = root.querySelector(".hchart .cur");
      cur.setAttribute("x1", xx); cur.setAttribute("x2", xx);
      root.querySelector(".hchart").classList.add("on");
      if (h) root.querySelector(".hchart .info").innerHTML = this._hinfo(h);
    };
    hit.addEventListener("pointermove", move);
    hit.addEventListener("pointerdown", move);
    hit.addEventListener("touchmove", move, { passive: true });
  }

  // A page to keep or share: the period's numbers, the graph, the log and the days (built here, nothing is sent)
  _report() {
    const html = this._reportHtml();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([html], { type: "text/html" }));
    a.download = `roost-${new Date().toISOString().slice(0, 10)}.html`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
  }

  _reportHtml() {
    const s = this._histSlice(), st = this._histStats(s);
    const svg = this.shadowRoot.querySelector(".hchart svg");
    const esc = (v) => String(v === undefined || v === null ? "" : v).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    const strip = (h) => String(h).replace(/<[^>]+>/g, "");
    const fromTo = `${new Date(s.t0 * 1000).toLocaleString(this._locale())} \u2013 ${new Date(s.t1 * 1000).toLocaleString(this._locale())}`;
    const days = Object.keys(s.d.days || {}).sort().reverse().slice(0, 62);
    const dayRows = days.map((k) => {
      const v = s.d.days[k];
      return `<tr><td>${k}</td><td>${this._num(v.kwh, 1)}</td><td>${this._num(v.heat_kwh, 1)}</td><td>${v.cop ? this._num(v.cop, 1) : "\u2014"}</td>` +
        `<td>${this._money(v.cost)}</td><td>${v.saving !== undefined ? this._money(v.saving) : "\u2014"}</td><td>${this._num(v.deficit_ch, 1)}</td>` +
        `<td>${v.changes} + ${v.by_hand}</td><td>${v.pred_mae !== null && v.pred_mae !== undefined ? "\u00b1" + this._num(v.pred_mae, 2) : "\u2014"}</td></tr>`;
    }).join("");
    const logRows = this._histItems(s).map((it) => `<tr><td>${new Date(it.ts * 1000).toLocaleString(this._locale())}</td><td>${esc(strip(it.what))}</td>` +
      `<td>${esc(strip(it.why))}</td><td>${esc(strip(it.out))}</td></tr>`).join("");
    // where the saving comes from, hour by hour (planner.breakdown), and why the plan changed (replan.py)
    const m3 = (v) => {
      if (v === null || v === undefined || isNaN(v)) return "\u2014";
      const cur = (this._hass && this._hass.config && this._hass.config.currency) || "EUR";
      try { return Number(v).toLocaleString(this._locale(), { style: "currency", currency: cur, minimumFractionDigits: 3, maximumFractionDigits: 3 }); } catch (e) { return this._num(v, 3); }
    };
    const sd = s.d.saving_detail || {};
    const lastDay = Object.keys(sd).sort().pop();
    const savTable = (bd, title) => {
      if (!bd || !bd.hours || !bd.hours.length) return `<h3>${esc(title)}</h3><p>${esc(this._t("r_none"))}</p>`;
      const th = (k) => `<th>${esc(this._t(k))}</th>`;
      // the tariff (price sensor, formula or contract) and what the plan counts: they differ while a home battery
      // supplies the house (the price of buying that kWh back later); hours logged by older versions have no tariff
      const tar = (r) => (r.tariff === null || r.tariff === undefined ? "\u2014" : m3(r.tariff)) + (r.guess ? " (" + esc(this._t("guessed")) + ")" : "");
      const differs = bd.hours.some((r) => r.tariff === null || r.tariff === undefined || Math.abs(r.tariff - r.price) >= 0.0005);
      const rows = bd.hours.map((r) => `<tr><td>${r.ts ? esc(this._hour(new Date(r.ts * 1000))) : esc(r.hour)}${r.sun ? " \u2600" : ""}</td><td>${this._num(r.t_out, 1)}</td><td>${tar(r)}</td><td>${m3(r.price)}</td>` +
        `<td>${this._num(r.sp, 1)}</td><td>${this._num(r.t, 1)}</td><td>${this._num(r.kwh, 2)}</td><td>${m3(r.cost)}</td>` +
        `<td>${this._num(r.b_sp, 1)}</td><td>${this._num(r.b_t, 1)}</td><td>${this._num(r.b_kwh, 2)}</td><td>${m3(r.b_cost)}</td><td><b>${m3(r.save)}</b></td></tr>`).join("");
      const note = this._t("r_note").replace("{a}", this._num(bd.short, 1)).replace("{b}", this._num(bd.b_short, 1));
      return `<h3>${esc(title)}</h3><p>${esc(this._savingQuality(bd.quality))}</p><table><tr><th></th><th></th><th></th><th></th><th colspan="4">${esc(this._t("r_roost"))}</th><th colspan="4">${esc(this._t("r_steady"))}</th><th></th></tr>` +
        `<tr>${th("r_hour")}${th("r_out")}${th("price")}${th("uses")}${th("r_sp")}${th("r_room")}${th("h_kwh")}${th("r_cost")}${th("r_sp")}${th("r_room")}${th("h_kwh")}${th("r_cost")}${th("r_diff")}</tr>${rows}` +
        `<tr><td><b>${esc(this._t("r_sum"))}</b></td><td></td><td></td><td></td><td></td><td></td><td>${this._num(bd.kwh, 1)}</td><td>${m3(bd.cost)}</td><td></td><td></td><td>${this._num(bd.b_kwh, 1)}</td><td>${m3(bd.b_cost)}</td><td>${m3(bd.b_cost - bd.cost)}</td></tr>` +
        `<tr><td colspan="7">${esc(this._t("r_end"))}</td><td>${m3(bd.end)}</td><td colspan="3"></td><td>${m3(bd.b_end)}</td><td>${m3(bd.b_end - bd.end)}</td></tr>` +
        `<tr><td colspan="12"><b>${esc(this._t("r_total"))}</b></td><td><b>${this._money(bd.saving)}</b></td></tr></table>` +
        (bd.parts ? `<table><tr><th colspan="2">${esc(this._t("p_title"))}</th></tr>` +
          `<tr><td>${esc(this._t("p_less"))}</td><td>${m3(bd.parts.less_kwh)}</td></tr>` +
          `<tr><td>\u2003\u2600 ${esc(this._t("p_sun"))}</td><td>${m3(bd.parts.sun)}</td></tr>` +
          `<tr><td>${esc(this._t("p_cheap"))}</td><td>${m3(bd.parts.cheaper_hours)}</td></tr>` +
          `<tr><td>${esc(this._t("p_end"))}</td><td>${m3(bd.parts.end)}</td></tr>` +
          `<tr><td><b>${esc(this._t("r_total"))}</b></td><td><b>${this._money(bd.saving)}</b></td></tr></table>` : "") +
        `<p>${esc(note)}</p>` + (differs ? `<p>${esc(this._t("r_uses_note"))}</p>` : "");
    };
    const cause = (c, dt) => {
      const n = dt[c] !== undefined ? dt[c] : 0;
      return (this._t("c_" + c) || c).replace("{n}", n).replace("{r}", this._num(dt.room, 1)).replace("{e}", this._num(dt.room_expected, 1));
    };
    const chg = (s.d.plan_changes || []).filter((c) => c.ts >= s.t0).slice().reverse();
    const chgRows = chg.map((c) => `<tr><td>${new Date(c.ts * 1000).toLocaleString(this._locale())}</td>` +
      `<td>${this._num(c.sp[0], 1)} \u2192 ${this._num(c.sp[1], 1)}${DEG}</td><td>${this._money(c.saving[0])} \u2192 ${this._money(c.saving[1])}</td>` +
      `<td>${esc(c.why.map((w) => cause(w, c.detail || {})).join("; "))}</td></tr>`).join("");
    const savHtml = `<h2>${esc(this._t("r_sav"))}</h2>` + savTable(lastDay ? sd[lastDay] : null, `${this._t("r_yday")}${lastDay ? " (" + lastDay + ")" : ""}`) +
      savTable(s.d.next, this._t("r_next")) +
      `<h2>${esc(this._t("r_changes"))}</h2>` + (chgRows ? `<table><tr><th>${esc(this._t("t_time"))}</th><th>${esc(this._t("r_ch_sp"))}</th><th>${esc(this._t("r_ch_sav"))}</th><th>${esc(this._t("t_why"))}</th></tr>${chgRows}</table>`
        : `<p>${esc(this._t("r_nochg"))}</p>`);
    const css = `body{font-family:system-ui,sans-serif;margin:24px;color:#222}h1{font-size:20px}table{border-collapse:collapse;font-size:13px;margin:8px 0 20px}
      td,th{border-bottom:1px solid #ddd;padding:4px 8px;text-align:left}svg{max-width:760px;width:100%}
      .grid{stroke:#e5e5e5}.axis{fill:#777;font-size:10px}.sp{fill:none;stroke:#fb923c;stroke-width:2.2}.hplan{fill:none;stroke:#fb923c;stroke-width:1.5;stroke-dasharray:4 3}
      .hroom{fill:none;stroke:#222;stroke-width:2}.hpred{fill:none;stroke:#378add;stroke-width:1.5;stroke-dasharray:4 3}.price{opacity:.55}
      .hheat{fill:#f0997b;opacity:.8}.hpause{fill:#f5a524;opacity:.12}.hmark{fill:#fde7c2;stroke:#ba7517}.hmt{fill:#7a4a06;font-size:8px}.hdev{fill:#e5484d}
      .cur,.hit{display:none}:root{--rc-cheap:#30a46c;--rc-mid:#f5a524;--rc-dear:#e5484d}`;
    const html = `<!doctype html><html><head><meta charset="utf-8"><title>Roost \u2013 ${esc(this._t("back"))}</title><style>${css}</style></head><body>
      <h1>Roost \u2013 ${esc(this._t("back"))}</h1><p>${esc(this._t("h_period"))}: ${esc(fromTo)}</p>
      <table><tr><th>${esc(this._t("h_cost"))}</th><th>${esc(this._t("h_saving"))}</th><th>${esc(this._t("h_pred"))}</th><th>${esc(this._t("h_below"))}</th><th>${esc(this._t("h_changes"))}</th></tr>
      <tr><td>${st.cost !== null ? this._money(st.cost) : "\u2014"}</td><td>${st.sav !== null ? this._money(st.sav) : "\u2014"}</td><td>${st.mae !== null ? "\u00b1" + this._num(st.mae, 2) + " \u00b0C" : "\u2014"}</td>
      <td>${st.below} min</td><td>${st.roost} + ${st.hand}</td></tr></table>
      ${svg ? svg.outerHTML : ""}
      <h2>${esc(this._t("h_log"))}</h2><table>${logRows}</table>
      <h2>${esc(this._t("h_day"))}</h2><table><tr><th>${esc(this._t("h_day"))}</th><th>${esc(this._t("h_kwh"))}</th><th>${esc(this._t("h_heat"))}</th><th>${esc(this._t("h_cop"))}</th>
      <th>${esc(this._t("h_cost"))}</th><th>${esc(this._t("h_saving"))}</th><th>${esc(this._t("h_deficit"))}</th><th>${esc(this._t("h_changes"))}</th><th>${esc(this._t("h_pred"))}</th></tr>${dayRows}</table>
      ${savHtml}
      </body></html>`;
    return html;
  }

  _style() {
    return `<style>
      :host { --rc-sp: #fb923c; --rc-cheap: var(--success-color, #30a46c); --rc-mid: var(--warning-color, #f5a524); --rc-dear: var(--error-color, #e5484d);
              --rc-band: var(--success-color, #30a46c); --rc-room: var(--primary-text-color); }
      ha-card { display: block; padding: 16px; cursor: pointer; container-type: inline-size; }
      .na { color: var(--secondary-text-color); padding: 8px 0; }
      .head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
      @container (max-width: 520px) { .head .seg { order: 5; flex: 1 1 100%; } .head .seg span { flex: 1; text-align: center; } }
      .ico { width: 38px; height: 38px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex: none;
             background: color-mix(in srgb, var(--rc-sp) 18%, transparent); color: var(--rc-sp); }
      .ht { flex: 1; min-width: 0; } .tt { font-size: 16px; font-weight: 600; }
      .sub { font-size: 12px; color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .pill { font-size: 11px; font-weight: 600; letter-spacing: .3px; padding: 3px 9px; border-radius: 999px; flex: none; }
      .pill.active { background: color-mix(in srgb, var(--success-color, #30a46c) 20%, transparent); color: var(--success-color, #30a46c); }
      .pill.shadow, .pill.off { background: color-mix(in srgb, var(--secondary-text-color) 18%, transparent); color: var(--secondary-text-color); }
      .pill.warn { background: color-mix(in srgb, var(--warning-color, #f5a524) 20%, transparent); color: var(--warning-color, #f5a524); }
      .tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
      .status { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; font-size: 12px; margin: -4px 0 10px; padding: 7px 10px; border-radius: 10px;
        background: linear-gradient(90deg, color-mix(in srgb, var(--rc-sp) 14%, transparent), transparent); }
      .status ha-icon { --mdc-icon-size: 16px; color: var(--rc-sp); } .status .stx { flex: 1 1 auto; } .status b { font-weight: 600; }
      .chip { font-size: 11px; padding: 2px 8px; border-radius: 999px; display: inline-flex; align-items: center; gap: 3px; }
      .chip ha-icon { --mdc-icon-size: 13px; color: inherit; }
      .chip.info { background: color-mix(in srgb, var(--info-color, #3b82f6) 18%, transparent); color: var(--info-color, #3b82f6); }
      .chip.warn { background: color-mix(in srgb, var(--warning-color, #f5a524) 20%, transparent); color: var(--warning-color, #f5a524); }
      .chip.calpill { cursor: pointer; background: color-mix(in srgb, var(--success-color, #30a46c) 16%, transparent); color: var(--success-color, #30a46c); }
      .chip.calpill.on { outline: 1px solid var(--success-color, #30a46c); }
      .chip.heat { background: color-mix(in srgb, var(--rc-sp) 20%, transparent); color: var(--rc-sp); }
      .tile.rtile.warm { background: linear-gradient(160deg, color-mix(in srgb, var(--rc-sp) 12%, transparent), transparent 70%); }
      .tile.rtile.cool { background: linear-gradient(160deg, color-mix(in srgb, var(--info-color, #3b82f6) 12%, transparent), transparent 70%); }
      .spark { width: 100%; height: 22px; display: block; margin: 2px 0; } .spark path { fill: none; stroke-width: 1.6; stroke: var(--rc-room); }
      .spark .sp2 { stroke-dasharray: 3 3; opacity: .7; } .spark .spn { stroke: var(--divider-color); stroke-width: 1; }
      .nx { display: inline-flex; align-items: center; gap: 2px; font-size: 11px; font-weight: 600; } .nx ha-icon { --mdc-icon-size: 14px; }
      .nx.up { color: var(--rc-sp); } .nx.dn { color: var(--info-color, #3b82f6); }
      .tl i.hot { width: 7px; height: 7px; border-radius: 50%; background: var(--rc-sp); margin-left: auto; }
      .badge { display: inline-block; font-size: 10.5px; padding: 1px 7px; border-radius: 999px; margin-top: 2px;
        background: color-mix(in srgb, var(--rc-sp) 16%, transparent); color: var(--rc-sp); }
      rect.sun { fill: #f5c542; opacity: .28; } .l.sun { background: #f5c542; opacity: .6; } .l.pump { background: var(--rc-sp); }
      .pstrip { display: flex; gap: 1px; height: 5px; margin-top: -2px; } .pstrip i { flex: 1; border-radius: 2px; background: var(--divider-color); }
      .pstrip i.on { background: var(--rc-sp); }
      .mtiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 8px; margin-top: 12px; }
      .mt { border: 1px solid var(--divider-color); border-radius: 12px; padding: 8px 11px; min-width: 0; }
      .mv { font-size: 18px; font-weight: 700; margin-top: 2px; } .mv.good { color: var(--success-color, #30a46c); }
      .cal { margin: -4px 0 10px; padding: 8px 10px; border: 1px solid var(--divider-color); border-radius: 10px; } .cgrid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 3px; max-width: 260px; }
      .cwd { font-size: 10.5px; color: var(--secondary-text-color); text-align: center; }
      .cd { height: 20px; border-radius: 5px; font-size: 10.5px; display: flex; align-items: center; justify-content: center;
        color: var(--secondary-text-color); border: 1px solid var(--divider-color); }
      .cd.ok { background: var(--success-color, #30a46c); border-color: transparent; color: #fff; font-weight: 600; }
      .cd.bad { background: color-mix(in srgb, var(--secondary-text-color) 30%, transparent); border-color: transparent; color: var(--primary-text-color); cursor: pointer; }
      .cd.future { border-style: dashed; opacity: .45; } .cd.sel { outline: 2px solid var(--rc-sp); }
      .calleg { display: flex; flex-wrap: wrap; gap: 4px 14px; margin-top: 6px; font-size: 11px; color: var(--secondary-text-color); }
      .calleg span { display: inline-flex; align-items: center; gap: 5px; }
      .calleg i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; border: 1px solid var(--divider-color); }
      .calleg i.ok { background: var(--success-color, #30a46c); border-color: transparent; }
      .calleg i.bad { background: color-mix(in srgb, var(--secondary-text-color) 30%, transparent); border-color: transparent; }
      .cwhy { font-size: 11.5px; color: var(--secondary-text-color); margin-top: 4px; }
      .week { flex: 1 1 100%; } .wtog { display: inline-flex; gap: 4px; } .mini.on { border-color: var(--rc-sp); color: var(--rc-sp); }
      .wgrid { margin: 6px 0; } .wrow { display: flex; align-items: center; gap: 8px; margin: 3px 0; cursor: pointer; font-size: 12px; }
      .wrow > span { width: 22px; color: var(--secondary-text-color); } .wrow.sel > span { color: var(--rc-sp); font-weight: 700; }
      .wbar { position: relative; flex: 1; height: 16px; border-radius: 4px; background: color-mix(in srgb, var(--secondary-text-color) 12%, transparent); }
      .wrow.sel .wbar { outline: 1px solid var(--rc-sp); }
      .wbar i { position: absolute; top: 2px; bottom: 2px; border-radius: 3px; background: linear-gradient(90deg, var(--rc-band), color-mix(in srgb, var(--rc-band) 70%, transparent)); }
      .wbar i.over { opacity: .55; }
      .waxis { display: flex; justify-content: space-between; margin-left: 30px; font-size: 10.5px; color: var(--secondary-text-color); }
      .wedit { border: 1px solid var(--divider-color); border-radius: 10px; padding: 8px 10px; } .wday { font-weight: 700; margin: 4px 0; }
      .wper { display: flex; align-items: center; gap: 4px; margin: 3px 0; font-size: 13px; } .wper .del { margin-left: auto; }
      .wbtns { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; } .mini.save { border-color: var(--rc-sp); color: var(--rc-sp); font-weight: 700; }
      .wmsg { font-size: 12px; margin-top: 6px; } .wmsg.ok { color: var(--success-color, #30a46c); } .wmsg.err { color: var(--error-color, #e5484d); }
      .tile { border: 1px solid var(--divider-color); border-radius: 12px; padding: 9px 11px; min-width: 0; }
      .rooms { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
      .room { font-size: 11.5px; color: var(--secondary-text-color); border: 1px solid var(--divider-color); border-radius: 999px; padding: 3px 9px; }
      .room b { color: var(--primary-text-color); font-weight: 600; } .room i { font-style: normal; opacity: .75; }
      .room.cold { border-color: var(--warning-color, #f5a524); color: var(--warning-color, #f5a524); }
      .tl { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--secondary-text-color); }
      .tl ha-icon { --mdc-icon-size: 15px; }
      .tv { font-size: 21px; font-weight: 700; margin-top: 3px; white-space: nowrap; } .tv.big { font-size: 25px; }
      .tv span { font-size: .55em; font-weight: 500; color: var(--secondary-text-color); margin-left: 2px; }
      .tile.plan .tv { color: var(--rc-sp); }
      .ts { font-size: 11px; color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .chart { margin-top: 14px; cursor: default; touch-action: pan-y; user-select: none; -webkit-user-select: none; }
      .ch { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; font-weight: 600; margin-bottom: 4px; }
      .ch > span:first-child { flex: none; white-space: nowrap; }
      .badge { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; vertical-align: top; }
      @container (max-width: 520px) { .tile .ts { white-space: normal; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; } }
      .info { font-weight: 400; color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .info b.o { color: var(--rc-sp); } .info i { font-style: normal; opacity: .8; }
      .chart.on .info i { display: none; }
      .pill.modebtn { cursor: pointer; display: inline-flex; align-items: center; gap: 1px; }
      .pill.modebtn ha-icon { --mdc-icon-size: 14px; margin-right: -4px; }
      .mmenu { display: flex; gap: 6px; flex-wrap: wrap; margin: 2px 0 8px; }
      .mopt { flex: 1 1 120px; text-align: left; border: 1px solid var(--divider-color); border-radius: 10px; padding: 6px 9px;
        background: none; color: var(--primary-text-color); font: inherit; cursor: pointer; }
      .mopt.on { border-color: var(--rc-sp); } .mopt b { display: block; font-size: 13px; }
      .mopt small { color: var(--secondary-text-color); font-size: 11px; }
      .tile.plan, .tile.therm { cursor: pointer; }
      .mrow { flex: 1 1 100%; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; border: 1px solid var(--divider-color);
        border-radius: 10px; padding: 6px 9px; font-size: 13px; } .mrow > span { display: inline-flex; gap: 6px; align-items: center; }
      .mrow small { flex: 1 1 100%; color: var(--secondary-text-color); font-size: 11px; }
      .setbtn { flex: 1 1 100%; } .setbtn ha-icon { --mdc-icon-size: 16px; vertical-align: -3px; }
      .spanel { flex: 1 1 100%; border: 1px solid var(--divider-color); border-radius: 10px; padding: 4px 9px; }
      .srow { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 4px 0; font-size: 13px; }
      .srow + .srow { border-top: 1px solid var(--divider-color); } .srow > span:last-child { display: inline-flex; gap: 6px; align-items: center; }
      .sv { min-width: 3.6em; text-align: center; font-weight: 600; }
      .mini { border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color); border-radius: 8px; padding: 3px 9px;
        font: inherit; font-size: 12px; cursor: pointer; } .cfv { min-width: 4em; text-align: center; }
      .srcl { font-size: 12px; color: var(--secondary-text-color); margin: 4px 0 8px; }
      .sbar { display: flex; height: 6px; border-radius: 3px; overflow: hidden; margin-bottom: 4px; background: var(--divider-color); }
      .sbar i { display: block; height: 100%; } i.ss { background: #f5b301; } i.sb { background: #22a06b; } i.sg { background: #8a8f98; }
      .srcl b.ss { color: #d99a00; font-weight: 500; } .srcl b.sb { color: #22a06b; font-weight: 500; } .srcl b.sg { font-weight: 500; }
      .tloss { font-size: 12px; color: var(--warning-color, #f59e0b); margin: 0 0 4px; }
      .warnline { display: flex; gap: 6px; align-items: flex-start; font-size: 12px; margin: -4px 0 10px; padding: 6px 9px; border-radius: 8px;
        color: var(--warning-color, #f59e0b); background: color-mix(in srgb, var(--warning-color, #f59e0b) 12%, transparent); }
      .warnline ha-icon { --mdc-icon-size: 16px; flex: none; } .head .ico { cursor: pointer; }
      .czone { fill: var(--secondary-text-color); opacity: .05; } .vgrid { opacity: .5; }
      .ccloud { fill: var(--primary-text-color); opacity: .22; } .cadv.dash { stroke-dasharray: 6 4; opacity: .7; }
      .l.ccl { background: var(--primary-text-color); opacity: .5; border-radius: 50%; width: 6px !important; height: 6px !important; }
      .l.cdashl { background: none; border-top: 2px dashed var(--rc-sp); height: 0; }
      .cadv { fill: none; stroke: var(--rc-sp); stroke-width: 2.5; } .cdot { fill: var(--rc-sp); }
      .cval { fill: var(--rc-sp); font-size: 11px; font-weight: 600; } .cval.soft, .cdot.soft { opacity: .55; }
      .cmv { fill: var(--primary-text-color); font-size: 10px; opacity: .85; }
      .cleg { display: grid; gap: 3px; margin: 6px 0 2px; font-size: 12px; color: var(--secondary-text-color); }
      .cleg .l { display: inline-block; width: 14px; height: 3px; margin-right: 7px; vertical-align: middle; }
      .l.czl { background: var(--secondary-text-color); opacity: .25; height: 9px; }
      .curve tr.cz td { color: var(--secondary-text-color); } .curve tr.cz td b { color: var(--secondary-text-color); font-weight: 500; }
      .curve small { font-size: 10.5px; color: var(--secondary-text-color); }
      ul.cnote { margin: 6px 0 0; padding-left: 16px; }
      .cnow { fill: none; stroke: var(--secondary-text-color); stroke-width: 1.5; stroke-dasharray: 5 3; }
      .cneed { fill: none; stroke: var(--info-color, #378add); stroke-width: 1.5; stroke-dasharray: 4 3; } .cneed.soft { opacity: .45; }
      .cmade { fill: var(--primary-text-color); opacity: .85; }
      .l.cnowl { background: var(--secondary-text-color); } .l.cneedl { background: none; border-top: 2px dashed var(--info-color, #378add); height: 0; }
      .l.cmadel { background: var(--primary-text-color); border-radius: 50%; width: 7px; height: 7px; }
      .ptable { font-size: 12.5px; font-variant-numeric: tabular-nums; }
      .tsec { font-size: 12px; font-weight: 600; margin: 10px 0 2px; }
      .tr { display: grid; grid-template-columns: minmax(6.5em, 1.3fr) 1fr 1.2fr 0.8fr 0.6fr; gap: 0 8px; padding: 4px 0;
        border-top: 1px solid var(--divider-color); align-items: baseline; }
      .tr > :nth-child(n+2) { text-align: right; } .tr.th { color: var(--secondary-text-color); font-size: 11px; border-top: 0; }
      .tr.now { background: color-mix(in srgb, var(--rc-sp) 7%, transparent); }
      .tr b.o { color: var(--rc-sp); font-weight: 600; } .tr small { color: var(--secondary-text-color); }
      .tw { grid-column: 1 / -1; text-align: left !important; color: var(--secondary-text-color); font-size: 12px; }
      .pr.cheap { color: var(--rc-cheap); } .pr.dear { color: var(--rc-dear); } .pr.guess { opacity: .55; }
      .mk { font-style: normal; font-size: 11px; padding: 0 5px; border-radius: 6px; background: color-mix(in srgb, var(--warning-color, #f59e0b) 22%, transparent); }
      .tday summary { cursor: pointer; padding: 6px 0; font-size: 12.5px; } .tday summary span { color: var(--secondary-text-color); }
      .pwhy { font-size: 12px; color: var(--secondary-text-color); margin: 2px 0 4px; min-height: 1.3em; }
      .pwhy b { color: var(--primary-text-color); font-weight: 600; }
      .curve { margin: 8px 0 2px; font-size: 13px; } .curve summary { cursor: pointer; font-weight: 600; font-size: 12px; }
      .curve summary span { font-weight: 400; color: var(--secondary-text-color); }
      .curve table { border-collapse: collapse; margin: 6px 0; } .curve th, .curve td { padding: 2px 12px 2px 0; text-align: right; }
      .curve th { font-weight: 400; color: var(--secondary-text-color); font-size: 12px; } .curve td b { color: var(--rc-sp); }
      .curve td i { font-style: normal; color: var(--secondary-text-color); }
      .cnote { font-size: 12px; color: var(--secondary-text-color); line-height: 1.4; }
      svg { width: 100%; display: block; touch-action: pan-y; }
      .band { fill: var(--rc-band); opacity: .07; } .grid { stroke: var(--divider-color); stroke-width: 1; }
      .axis { fill: var(--secondary-text-color); font-size: 10px; } .nowt { fill: var(--rc-sp); }
      .price { opacity: .55; } .price.guess { opacity: .2; } .area { fill: var(--rc-room); opacity: .06; }
      .sp { fill: none; stroke: var(--rc-sp); stroke-width: 2.2; stroke-linejoin: round; }
      .room { fill: none; stroke: var(--rc-room); stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
      .nowl { stroke: var(--rc-sp); stroke-width: 1.5; opacity: .6; }
      .cur { stroke: var(--secondary-text-color); stroke-dasharray: 2 2; opacity: 0; } .dot { fill: var(--rc-room); opacity: 0; }
      .dot2 { fill: var(--rc-sp); opacity: 0; } .chart.on .cur, .chart.on .dot, .chart.on .dot2 { opacity: 1; }
      .hit { fill: transparent; cursor: crosshair; }
      .leg { display: flex; flex-wrap: wrap; gap: 12px; font-size: 11px; color: var(--secondary-text-color); margin-top: 4px; }
      .leg span { display: inline-flex; align-items: center; gap: 5px; }
      .l { display: inline-block; width: 14px; height: 3px; border-radius: 2px; } .l.sp { background: var(--rc-sp); }
      .l.room { background: var(--rc-room); } .l.price { height: 8px; background: linear-gradient(90deg, var(--rc-cheap), var(--rc-mid), var(--rc-dear)); opacity: .6; }
      .l.price.guess { opacity: .2; }
      .l.band { height: 8px; background: var(--rc-band); opacity: .25; }
      .foot { font-size: 12px; color: var(--secondary-text-color); margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--divider-color); }
      .seg { display: flex; border: 1px solid var(--divider-color); border-radius: 8px; overflow: hidden; font-size: 11.5px; flex: none; cursor: pointer; }
      .seg span { padding: 3px 8px; color: var(--secondary-text-color); } .seg span.on { background: color-mix(in srgb, var(--rc-sp) 18%, transparent); color: var(--rc-sp); font-weight: 600; }
      .hbar { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
      .rep { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; padding: 3px 9px; border-radius: 8px; border: 1px solid var(--divider-color);
             background: none; color: var(--secondary-text-color); cursor: pointer; } .rep ha-icon { --mdc-icon-size: 15px; }
      .tiles.four { grid-template-columns: repeat(4, minmax(0, 1fr)); } .htile .tv { font-size: 18px; }
      .hplan { fill: none; stroke: var(--rc-sp); stroke-width: 1.5; stroke-dasharray: 4 3; }
      .hroom { fill: none; stroke: var(--rc-room); stroke-width: 2; stroke-linejoin: round; }
      .hpred { fill: none; stroke: var(--info-color, #378add); stroke-width: 1.5; stroke-dasharray: 4 3; }
      .hheat { fill: #f0997b; opacity: .8; } .hpause { fill: var(--warning-color, #f5a524); opacity: .12; }
      .hmark { fill: color-mix(in srgb, var(--warning-color, #f5a524) 25%, var(--card-background-color, #fff)); stroke: var(--warning-color, #f5a524); stroke-width: .7; }
      .hmt { fill: var(--primary-text-color); font-size: 8px; font-weight: 600; } .hdev { fill: var(--error-color, #e5484d); }
      .l.hplan { background: none; border-top: 2px dashed var(--rc-sp); height: 0; } .l.hroom { background: var(--rc-room); }
      .l.hpred { background: none; border-top: 2px dashed var(--info-color, #378add); height: 0; } .l.hheat { height: 8px; background: #f0997b; }
      .hlog { margin-top: 10px; font-size: 12px; } .lhead { cursor: pointer; color: var(--secondary-text-color); font-weight: 600; padding: 4px 0; }
      .lrow { display: grid; grid-template-columns: 70px 62px minmax(0, 1fr) auto; gap: 8px; padding: 5px 0; border-top: 1px solid var(--divider-color); }
      .lrow .mut { color: var(--secondary-text-color); } .lrow .warn { color: var(--warning-color, #f5a524); } .lrow .ok { color: var(--success-color, #30a46c); }
      .foot b { color: var(--primary-text-color); }
      .steer { margin-top: 10px; width: 100%; padding: 9px; border-radius: 10px; border: 1px solid var(--success-color, #30a46c);
               background: color-mix(in srgb, var(--success-color, #30a46c) 15%, transparent); color: var(--success-color, #30a46c);
               font-weight: 600; font-size: 13px; cursor: pointer; } .foot b.ok { color: var(--success-color, #30a46c); }
    </style>`;
  }
}

class RoostCardEditor extends HTMLElement {
  setConfig(config) { this._config = config; this._render(); }
  set hass(hass) { this._hass = hass; this._render(); }

  // The toggles show what the card really shows. Switching "compact" resets the parts to its preset, and a part
  // that matches the preset is left out of the YAML, so the configuration stays short.
  _changed(value) {
    const prev = this._config || {};
    const v = Object.assign({}, value);
    if (!!v.compact !== !!prev.compact) PARTS.forEach((p) => { delete v["show_" + p]; });
    else PARTS.forEach((p) => { if (v["show_" + p] === showDefault(v, p)) delete v["show_" + p]; });
    if (!v.compact) delete v.compact;
    if (!v.title) delete v.title;
    if (!v.language || v.language === "auto") delete v.language;
    if (!v.time_format || v.time_format === "auto") delete v.time_format;
    if (v.history !== false) delete v.history;
    if (!v.view || v.view === "plan") delete v.view;
    this._config = v;
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: v }, bubbles: true, composed: true }));
  }

  _render() {
    if (!this._hass || !this._config) return;
    const t = T[lang2(this._hass)] || T.en;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => t["e_" + s.name] || s.name;
      this._form.addEventListener("value-changed", (ev) => this._changed(ev.detail.value));
      this.appendChild(this._form);
    }
    const data = Object.assign({}, this._config, { compact: !!this._config.compact,
      language: this._config.language || "auto", time_format: this._config.time_format || "auto",
      history: this._config.history !== false, view: this._config.view || "plan" });
    PARTS.forEach((p) => { data["show_" + p] = shows(this._config, p); });
    this._form.hass = this._hass;
    this._form.data = data;
    this._form.schema = [
      { name: "entity", required: true, selector: { entity: { filter: { integration: "roost_quatt", domain: "sensor" } } } },
      { name: "title", selector: { text: {} } },
      { name: "compact", selector: { boolean: {} } },
      { type: "grid", name: "", schema: [
        { name: "view", selector: { select: { mode: "dropdown", options: [
          { value: "plan", label: t.v_plan }, { value: "table", label: t.v_table }, { value: "curve", label: t.v_curve },
          { value: "history", label: t.v_history }] } } },
        { name: "history", selector: { boolean: {} } }] },
      { type: "grid", name: "", schema: [
        { name: "language", selector: { select: { mode: "dropdown", options: [
          { value: "auto", label: t.e_auto }, { value: "en", label: "English" }, { value: "nl", label: "Nederlands" },
          { value: "de", label: "Deutsch" }, { value: "fr", label: "Fran\u00e7ais" }] } } },
        { name: "time_format", selector: { select: { mode: "dropdown", options: [
          { value: "auto", label: t.e_auto }, { value: "24", label: "24h (13:45)" }, { value: "12", label: "12h (1:45 PM)" }] } } }] },
      { type: "grid", name: "", schema: PARTS.map((p) => ({ name: "show_" + p, selector: { boolean: {} } })) },
    ];
  }
}

// Home Assistant 2026.9+ swaps window.customElements for a scoped registry while it starts: define in the registry
// that is there now, and again in the new one as soon as it appears (lesson from the Shower Time card).
const ELEMENTS = [["roost-quatt-card", RoostCard], ["roost-quatt-card-editor", RoostCardEditor]];
const defineIn = (registry) => {
  for (const pair of ELEMENTS) {
    try { if (!registry.get(pair[0])) registry.define(pair[0], pair[1]); } catch (e) { /* defined meanwhile */ }
  }
};
let registry = window.customElements;
defineIn(registry);
const recheck = () => { if (window.customElements !== registry) { registry = window.customElements; defineIn(registry); } };
if (registry.whenDefined) registry.whenDefined("home-assistant").then(recheck);
let checks = 0;
const timer = setInterval(() => { recheck(); if (++checks >= 120) clearInterval(timer); }, 250);
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "roost-quatt-card")) {
  window.customCards.push({ type: "roost-quatt-card", name: "Roost for Quatt", preview: true,
    description: "The 24-hour heating plan of your Quatt heat pump." });
}
console.info(`%c ROOST-QUATT-CARD %c ${CARD_VERSION} `, "background:#fb923c;color:#fff;border-radius:3px 0 0 3px",
  "background:#222;color:#fff;border-radius:0 3px 3px 0");
})();
