#!/usr/bin/env python3
import datetime
import gzip
import io
import json
import os

ID = "kalender_ereignisse"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
START = datetime.date(2001, 1, 1)
TAX_MONTHS_DAYS = ((1, 15), (4, 15), (6, 15), (9, 15), (12, 15))
QUARTER_MONTHS = (3, 6, 9, 12)


def third_friday(year, month):
    d = datetime.date(year, month, 1)
    first_friday_offset = (4 - d.weekday()) % 7
    return d + datetime.timedelta(days=first_friday_offset + 14)


def daterange(start, end):
    d = start
    one = datetime.timedelta(days=1)
    while d <= end:
        yield d
        d += one


def build_ustax(end):
    event_days = set()
    for year in range(START.year, end.year + 1):
        for month, day in TAX_MONTHS_DAYS:
            event_days.add(datetime.date(year, month, day))
    return [(d, 1 if d in event_days else 0) for d in daterange(START, end)]


def build_opex(end):
    event_days = set()
    for year in range(START.year, end.year + 1):
        for month in QUARTER_MONTHS:
            event_days.add(third_friday(year, month))
    return [(d, 1 if d in event_days else 0) for d in daterange(START, end)]


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


def main():
    end = datetime.datetime.now(datetime.timezone.utc).date()

    rows_ustax = build_ustax(end)
    rows_opex = build_opex(end)

    gzip_write(os.path.join(OUT_DIR, "ustax.csv.gz"), rows_ustax)
    gzip_write(os.path.join(OUT_DIR, "opex_verfall.csv.gz"), rows_opex)

    meta = {
        "ustax": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 an US-Steuerterminen (15.1., 15.4., 15.6., 15.9., 15.12., feste Kalenderdaten ohne Wochenend-/Feiertagsverschiebung), sonst 0, fuer jeden Kalendertag ab 2001-01-01.",
            "quelle_url": "https://www.irs.gov/filing/tax-day-when-are-taxes-due (feste, oeffentlich bekannte Kalendertermine)",
            "verdichtung": "keine (deterministische Kalenderreihe, kein externer Datenabruf)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
        "opex_verfall": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am dritten Freitag der Quartalsmonate Maerz/Juni/September/Dezember (grosser Verfall / Quadruple Witching, zugleich seit ca. 2005 Stichtag der S&P-Quartalsneugewichtung), sonst 0, fuer jeden Kalendertag ab 2001-01-01.",
            "quelle_url": "https://www.cboe.com/optionsexpirationcalendar/ (Marktkonvention: dritter Freitag der Quartalsmonate)",
            "verdichtung": "keine (deterministische Kalenderreihe, kein externer Datenabruf)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
