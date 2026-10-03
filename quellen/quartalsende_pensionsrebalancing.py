#!/usr/bin/env python3
"""Quartalsende-Rebalancing: 1 an den letzten drei NYSE-Handelstagen von Maerz, Juni, September
und Dezember, sonst 0, ab 1971-01-01 (Handelskalender wie turn_of_month_effekt). Fenster vorab
festgelegt (Harvey/Hudson-Stil Rebalancing-Flows; keine Marktdaten verwendet). Die Reihe wird
nur fuer abgeschlossene Quartale mit 1 belegt (letzter Handelstag bekannt)."""
import datetime, importlib.util, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("tom", os.path.join(HERE, "turn_of_month_effekt.py"))
tom = importlib.util.module_from_spec(spec); spec.loader.exec_module(tom)
ID = "quartalsende_pensionsrebalancing"
OUT = os.path.join(HERE, "..", "data", "neu", ID)


def main():
    end = datetime.datetime.now(datetime.timezone.utc).date()
    hc = {}
    all_days = list(tom.daterange(tom.START, end))
    by = {}
    for d in all_days:
        if d.month in (3, 6, 9, 12) and tom.is_trading_day(d, hc):
            by.setdefault((d.year, d.month), []).append(d)
    ev = set()
    for (y, m), days in by.items():
        # Kalender-Monatsende erreicht: letzte drei Handelstage sind dann feststehend
        # (fruehere Tage sind im Voraus bekannt, sobald der Monat laeuft; hier nur ab Monatsende gesetzt)
        if tom.month_end(y, m) <= end:
            ev |= set(days[-3:])
    rows = [(d, 1 if d in ev else 0) for d in all_days]
    tom.gzip_write(os.path.join(OUT, "quartalsende.csv.gz"), rows)
    meta = {"quartalsende": {
        "einheit": "Indikator (0/1)",
        "beschreibung": "1 an den letzten drei NYSE-Handelstagen von Maerz, Juni, September, Dezember (Quartalsende-Rebalancing von Pensionsfonds), sonst 0, jeder Kalendertag ab 1971-01-01. Handelstage ueber deterministischen NYSE-Feiertagskalender (siehe turn_of_month_effekt); Sonderschliessungen ab 1971 enthalten.",
        "quelle_url": "kein externer Abruf (deterministische Kalenderberechnung; NYSE-Regeln https://www.nyse.com/markets/hours-calendars)",
        "verdichtung": "keine (Kalenderreihe)",
        "publikation": "taeglich (Quartalsende und NYSE-Handelstage sind im Voraus bekannt; Belegquelle NYSE-Kalender)",
        "verfuegbar_nach_tagen": 0,
        "revidiert": False}}
    os.makedirs(OUT, exist_ok=True)
    json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), ensure_ascii=False, indent=2, sort_keys=True)


main()
