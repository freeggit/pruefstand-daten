#!/usr/bin/env python3
"""Turn-of-the-Month-Kalenderreihe: 1 am letzten Handelstag eines Monats sowie
an den ersten drei Handelstagen des Folgemonats (Ariel 1987), sonst 0. Rein
deterministische Berechnung ueber einen Naeherungskalender der NYSE-Feiertage
(keine Marktdaten, kein Blick auf Kurse). Beginn 1971-01-01: ab dem
Uniform Monday Holiday Act (1971) folgen Memorial Day und Washington's
Birthday den bis heute gueltigen Monatsregeln (3. Montag Februar / letzter
Montag Mai); vor 1971 galten feste Kalenderdaten (z.B. 30. Mai), was ohne
zusaetzliche Belege nicht sicher rueckgerechnet werden soll (Zusatz 4/5:
keine Tage erfinden). Nicht modelliert sind ausserordentliche, nicht
kalendarisch fixierte Boersenschliessungen (z.B. 11.-14.9.2001, 29.-30.10.2012,
Trauertage fuer verstorbene Praesidenten); an solchen Terminen kann die
berechnete Handelstag-Zuordnung im Einzelfall abweichen (im meta.json und
katalog.json vermerkt)."""
import datetime
import gzip
import io
import json
import os

ID = "turn_of_month_effekt"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
START = datetime.date(1971, 1, 1)


def easter_sunday(year):
    # Anonymer gregorianischer Algorithmus (Meeus/Jones/Butcher)
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


def nth_weekday(year, month, weekday, n):
    d = datetime.date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    return d + datetime.timedelta(days=offset + 7 * (n - 1))


def last_weekday(year, month, weekday):
    if month == 12:
        d = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        d = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
    offset = (d.weekday() - weekday) % 7
    return d - datetime.timedelta(days=offset)


def observed(d):
    # NYSE-Konvention: Feiertag Samstag -> vorheriger Freitag frei,
    # Feiertag Sonntag -> folgender Montag frei.
    if d.weekday() == 5:
        return d - datetime.timedelta(days=1)
    if d.weekday() == 6:
        return d + datetime.timedelta(days=1)
    return d


def nyse_holidays(year):
    hol = set()
    hol.add(observed(datetime.date(year, 1, 1)))
    if year >= 1998:
        hol.add(nth_weekday(year, 1, 0, 3))  # Martin Luther King Jr. Day
    hol.add(nth_weekday(year, 2, 0, 3))  # Washington's Birthday
    hol.add(easter_sunday(year) - datetime.timedelta(days=2))  # Good Friday
    hol.add(last_weekday(year, 5, 0))  # Memorial Day
    if year >= 2022:
        hol.add(observed(datetime.date(year, 6, 19)))  # Juneteenth
    hol.add(observed(datetime.date(year, 7, 4)))  # Independence Day
    hol.add(nth_weekday(year, 9, 0, 1))  # Labor Day
    hol.add(nth_weekday(year, 11, 3, 4))  # Thanksgiving
    hol.add(observed(datetime.date(year, 12, 25)))  # Christmas
    return hol


def is_trading_day(d, holcache):
    if d.weekday() >= 5:
        return False
    if d.year not in holcache:
        holcache[d.year] = nyse_holidays(d.year)
    return d not in holcache[d.year]


def daterange(start, end):
    d = start
    one = datetime.timedelta(days=1)
    while d <= end:
        yield d
        d += one


def month_end(year, month):
    if month == 12:
        return datetime.date(year, 12, 31)
    return datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)


def build(end):
    holcache = {}
    all_days = list(daterange(START, end))
    trading_days = [d for d in all_days if is_trading_day(d, holcache)]
    event_days = set()
    by_month = {}
    for d in trading_days:
        by_month.setdefault((d.year, d.month), []).append(d)
    months_sorted = sorted(by_month)
    for idx, key in enumerate(months_sorted):
        days = by_month[key]
        year, month = key
        if month_end(year, month) <= end:
            # Monat ist abgeschlossen: letzter Handelstag bekannt.
            event_days.add(days[-1])
        if idx + 1 < len(months_sorted):
            next_days = by_month[months_sorted[idx + 1]]
            for d in next_days[:3]:  # erste 3 Handelstage des Folgemonats
                event_days.add(d)
    return [(d, 1 if d in event_days else 0) for d in all_days]


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
    rows = build(end)
    gzip_write(os.path.join(OUT_DIR, "turn_of_month.csv.gz"), rows)

    meta = {
        "turn_of_month": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am letzten NYSE-Handelstag eines Monats sowie an den ersten drei NYSE-Handelstagen des Folgemonats (Turn-of-the-Month-Effekt, Ariel 1987), sonst 0, fuer jeden Kalendertag ab 1971-01-01. Handelstage ueber einen deterministischen NYSE-Feiertagskalender (Wochenenden plus New Year, MLK-Day ab 1998, Washington's Birthday, Good Friday, Memorial Day, Juneteenth ab 2022, Independence Day, Labor Day, Thanksgiving, Christmas) berechnet. Ausserordentliche, nicht kalendarisch fixierte Boersenschliessungen (z.B. 11.-14.9.2001, 29.-30.10.2012, Trauertage) sind NICHT modelliert; an solchen Terminen kann die Handelstag-Zuordnung im Einzelfall um 1-2 Tage abweichen. Vor 1971 (Uniform Monday Holiday Act) folgten Memorial Day/Washington's Birthday festen statt Montags-Regeln, daher keine Ausweitung ohne weitere Belege.",
            "quelle_url": "kein externer Abruf (deterministische Kalenderberechnung; NYSE-Feiertagsregeln gemaess https://www.nyse.com/markets/hours-calendars)",
            "verdichtung": "keine (deterministische Kalenderreihe, kein externer Datenabruf)",
            "publikation": "taeglich (Ereignisdatum aus oeffentlich bekanntem NYSE-Handelskalender im Voraus ableitbar, Reihe wird taeglich fortgeschrieben)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
