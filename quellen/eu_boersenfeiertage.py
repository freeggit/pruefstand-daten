#!/usr/bin/env python3
"""Boersenfeiertage Xetra/Frankfurt (Deutsche Boerse), volle Handelsschliessungen
ab Handelsstart von Xetra (28.11.1997).

Quelle: Deutsche Boerse AG, "Trading Calendar Xetra and Frankfurt"
(https://www.cashmarket.deutsche-boerse.com/cash-en/trading/trading-calendar-and-trading-hours):
Xetra/FWB sind geschlossen an Neujahr, Karfreitag, Ostermontag, Tag der Arbeit
(1. Mai), Heiligabend, 1. und 2. Weihnachtsfeiertag sowie Silvester. Explizit
KEINE Boersenfeiertage sind Christi Himmelfahrt, Pfingstmontag und der Tag der
Deutschen Einheit (an diesen Tagen wird reguleer gehandelt).

Anders als bei US-Feiertagen (NYSE) gibt es fuer diese deutschen Handelsfeiertage
keine Wochenend-Nachholregel: faellt ein Feiertag auf ein Wochenende, entfaellt
er einfach (kein Ersatztag). Start 1997-11-28 (Handelsstart Xetra): das
vorherige Parketthandel-System der Frankfurter Wertpapierboerse hatte
moeglicherweise einen aehnlichen, aber nicht ebenso solide belegten
Feiertagskalender - eine Rueckverlaengerung vor Xetra-Start ist eine
spaetere Etappe, sobald eine ebenso verlaessliche Quelle gefunden ist
(Zusatz 2: nichts schaetzen, Qualitaet vor Menge).
"""
import datetime
import gzip
import io
import json
import os

ID = "eu_boersenfeiertage"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
START = datetime.date(1997, 11, 28)


def easter_sunday(year):
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(year, month, day)


def build_closure_days(end):
    closed = set()
    for year in range(START.year, end.year + 1):
        ostern = easter_sunday(year)
        closed.add(datetime.date(year, 1, 1))
        closed.add(ostern - datetime.timedelta(days=2))  # Karfreitag
        closed.add(ostern + datetime.timedelta(days=1))  # Ostermontag
        closed.add(datetime.date(year, 5, 1))
        closed.add(datetime.date(year, 12, 24))
        closed.add(datetime.date(year, 12, 25))
        closed.add(datetime.date(year, 12, 26))
        closed.add(datetime.date(year, 12, 31))
    # keine Wochenend-Nachholregel: Feiertage an Wochenenden entfallen einfach
    return {d for d in closed if START <= d <= end and d.weekday() < 5}


def gzip_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for d, v in rows:
            t.write("%s,%d\n" % (d.isoformat(), v))
        t.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def daterange(start, end):
    d = start
    one = datetime.timedelta(days=1)
    while d <= end:
        yield d
        d += one


def main():
    end = datetime.datetime.now(datetime.timezone.utc).date()
    closed = build_closure_days(end)
    rows = [(d, 1 if d in closed else 0) for d in daterange(START, end)]
    gzip_write(os.path.join(OUT_DIR, "geschlossen.csv.gz"), rows)

    meta = {
        "geschlossen": {
            "einheit": "Indikator (0/1)",
            "beschreibung": (
                "1 an jedem Kalendertag (Mo-Fr), an dem Xetra/Frankfurter "
                "Wertpapierboerse wegen eines der acht Boersenfeiertage "
                "(Neujahr, Karfreitag, Ostermontag, 1. Mai, Heiligabend, "
                "1./2. Weihnachtsfeiertag, Silvester) geschlossen war, sonst 0 "
                "(auch an Wochenenden 0). Christi Himmelfahrt, Pfingstmontag und "
                "Tag der Deutschen Einheit sind laut Quelle KEINE Boersenfeiertage "
                "und daher nicht enthalten. Keine Wochenend-Nachholregel: faellt "
                "ein Feiertag auf ein Wochenende, entfaellt er ersatzlos."
            ),
            "quelle_url": "https://www.cashmarket.deutsche-boerse.com/cash-en/trading/trading-calendar-and-trading-hours",
            "verdichtung": "keine (deterministische, aus dem amtlichen Deutsche-Boerse-Handelskalender abgeleitete Kalenderreihe, kein externer taeglicher Datenabruf)",
            "publikation": "taeglich (Feiertagsdatum im Voraus oeffentlich bekannt, Reihe wird taeglich fortgeschrieben)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
