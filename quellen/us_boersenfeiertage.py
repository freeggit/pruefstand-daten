#!/usr/bin/env python3
"""US-Boersenfeiertage: volle Handelsschliessungen der NYSE, 1953-heute.

Quelle: NYSE / New York Stock Exchange, "History of New York Stock Exchange
Holidays" (revised through January 2011, offizielles Dokument, gespiegelt
u.a. unter https://s3.amazonaws.com/armstrongeconomics-wp/2013/07/NYSE-Closings.pdf
und https://www.ltadvisors.net/Info/research/closings.pdf) sowie
"NEW YORK STOCK EXCHANGE SPECIAL CLOSINGS, 1885-date" (selbes Dokument, Teil 2).

Start 1953-01-01: das Dokument listet fuer Lincoln's Birthday, Columbus Day
und Armistice/Veterans Day 1953 als letztes Jahr einer vollen Schliessung;
zugleich endet damit die Aera unregelmaessiger saisonaler Samstags-Handelstage
("Closed Saturdays" zuletzt 31.5.-27.9.1952) - danach ist Montag-Freitag
durchgehend die Handelswoche, was die Vor-/Nachfeiertags-Definition
(Kalendertag vor/nach einer Schliessung) sauber macht. Vor 1953 muessten
Samstags-Handelstage jahrweise rekonstruiert werden; das ist nicht belegt
genug, um "nichts zu erfinden" sicherzustellen (Zusatz 4/5).

Nur GANZE Handelstags-Schliessungen zaehlen (wert=1); reine Verkuerzungen
("Closed at 1:00 pm", Handelsunterbrechungen) sind laut Dokument die
Mehrzahl der spaeteren Eintraege und werden NICHT gezaehlt, da sie keine
volle Schliessung sind.
"""
import datetime
import gzip
import io
import json
import os

ID = "us_boersenfeiertage"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
START = datetime.date(1953, 1, 1)
SAT_RULE_START = datetime.date(1959, 7, 3)  # NYSE-Boardbeschluss: Samstags-Feiertag -> vorangehender Freitag


def easter_sunday(year):
    # Anonymous-Gregorian-/Meeus-Jones-Butcher-Algorithmus (Gregorianischer Kalender)
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


def observed_fixed(raw_date):
    """Wendet die im Dokument genannten Wochenend-Regeln auf ein festes Datum an.
    Sonntag -> folgender Montag (immer, 'traditionally'). Samstag -> vorangehender
    Freitag, aber erst ab dem Boardbeschluss vom 3.7.1959; davor keine automatische
    Verschiebung (siehe Docstring/Sonderfaelle in SPECIAL_CLOSURES)."""
    wd = raw_date.weekday()
    if wd == 6:  # Sonntag
        return raw_date + datetime.timedelta(days=1)
    if wd == 5:  # Samstag
        if raw_date >= SAT_RULE_START:
            return raw_date - datetime.timedelta(days=1)
        return None
    return raw_date


def election_day(year):
    d = datetime.date(year, 11, 1)
    first_monday = d + datetime.timedelta(days=(0 - d.weekday()) % 7)
    return first_monday + datetime.timedelta(days=1)


# Ad-hoc-Sonderschliessungen (ganze Handelstage), woertlich aus dem NYSE-Dokument
# "SPECIAL CLOSINGS, 1885-date" uebernommen (nur Eintraege ohne Zeitangabe wie
# "Closed at X pm", die also den ganzen Tag betreffen), plus zwei allgemein
# bekannte, oeffentlich dokumentierte Schliessungen nach dem Dokumentenstand
# (Jan. 2011): Hurrikan Sandy 2012 und Trauertag George H.W. Bush 2018.
SPECIAL_CLOSURES = {
    datetime.date(1954, 12, 24): "Weihnachtsabend (Weihnachten 1954 fiel auf Samstag, vor Boardbeschluss 1959; It. Dokument dennoch ganztags geschlossen)",
    datetime.date(1956, 12, 24): "Weihnachtsabend (lt. Dokument ganztags geschlossen, ohne Zeitangabe)",
    datetime.date(1958, 12, 26): "Tag nach Weihnachten (lt. Dokument ganztags geschlossen, ohne Zeitangabe)",
    datetime.date(1963, 11, 25): "Staatsbegraebnis Praesident John F. Kennedy",
    datetime.date(1965, 12, 24): "Weihnachtsabend, 'Closed all day'",
    datetime.date(1968, 4, 9): "Nationaler Trauertag fuer Martin Luther King, Jr.",
    datetime.date(1969, 3, 31): "Staatsbegraebnis frueherer Praesident Dwight D. Eisenhower",
    datetime.date(1969, 7, 21): "Nationaler Feiertag fuer die Mondlandung (Apollo 11)",
    datetime.date(1972, 12, 28): "Staatsbegraebnis frueherer Praesident Harry S. Truman",
    datetime.date(1973, 1, 25): "Staatsbegraebnis frueherer Praesident Lyndon B. Johnson",
    datetime.date(1977, 7, 14): "Stromausfall in New York City",
    datetime.date(1985, 9, 27): "Hurrikan Gloria",
    datetime.date(1994, 4, 27): "Staatsbegraebnis frueherer Praesident Richard M. Nixon",
    datetime.date(2001, 9, 11): "Terroranschlaege auf das World Trade Center",
    datetime.date(2001, 9, 12): "Terroranschlaege auf das World Trade Center",
    datetime.date(2001, 9, 13): "Terroranschlaege auf das World Trade Center",
    datetime.date(2001, 9, 14): "Terroranschlaege auf das World Trade Center",
    datetime.date(2004, 6, 11): "Nationaler Trauertag fuer frueheren Praesident Ronald Reagan",
    datetime.date(2007, 1, 2): "Nationaler Trauertag fuer frueheren Praesident Gerald Ford",
    datetime.date(2012, 10, 29): "Hurrikan Sandy (oeffentlich dokumentiert, ausserhalb Dokumentenstand Jan. 2011)",
    datetime.date(2012, 10, 30): "Hurrikan Sandy (oeffentlich dokumentiert, ausserhalb Dokumentenstand Jan. 2011)",
    datetime.date(2018, 12, 5): "Nationaler Trauertag fuer frueheren Praesidenten George H.W. Bush (oeffentlich dokumentiert)",
}


def build_closure_days(end):
    closed = set()

    for year in range(START.year, end.year + 1):
        # Neujahr
        d = observed_fixed(datetime.date(year, 1, 1))
        if d:
            closed.add(d)
        # Martin Luther King Jr. Day: ganztags erst ab 1998, 3. Montag Januar
        if year >= 1998:
            closed.add(nth_weekday(year, 1, 0, 3))
        # Lincoln's Birthday: nur noch 1953 (Reihe 1896-1953)
        if year == 1953:
            closed.add(datetime.date(1953, 2, 12))
        # Washington's Birthday: fest 22. Feb bis 1970, danach 3. Montag Februar
        if year <= 1970:
            d = observed_fixed(datetime.date(year, 2, 22))
            if d:
                closed.add(d)
        else:
            closed.add(nth_weekday(year, 2, 0, 3))
        # Karfreitag
        closed.add(easter_sunday(year) - datetime.timedelta(days=2))
        # Decoration/Memorial Day: fest 30. Mai bis 1970, danach letzter Montag Mai
        if year <= 1970:
            d = observed_fixed(datetime.date(year, 5, 30))
            if d:
                closed.add(d)
        else:
            closed.add(last_weekday(year, 5, 0))
        # Juneteenth: erst ab 2022 NYSE-Feiertag
        if year >= 2022:
            d = observed_fixed(datetime.date(year, 6, 19))
            if d:
                closed.add(d)
        # Unabhaengigkeitstag
        d = observed_fixed(datetime.date(year, 7, 4))
        if d:
            closed.add(d)
        # Labor Day: 1. Montag September
        closed.add(nth_weekday(year, 9, 0, 1))
        # Columbus Day: nur noch 1953 (Reihe 1909-1953)
        if year == 1953:
            closed.add(datetime.date(1953, 10, 12))
        # Election Day: jedes Jahr bis 1968, danach nur noch 1972/1976/1980
        if year <= 1968 or year in (1972, 1976, 1980):
            closed.add(election_day(year))
        # Armistice/Veterans Day: nur noch 1953 als volle Schliessung (Reihe 1934-1953)
        if year == 1953:
            closed.add(datetime.date(1953, 11, 11))
        # Thanksgiving: 4. Donnerstag November
        closed.add(nth_weekday(year, 11, 3, 4))
        # Weihnachten
        d = observed_fixed(datetime.date(year, 12, 25))
        if d:
            closed.add(d)

    # 1968 "Paperwork Crisis": Vier-Tage-Woche, jeden Mittwoch geschlossen
    d = datetime.date(1968, 6, 12)
    wed_end = datetime.date(1968, 12, 31)
    while d <= wed_end:
        if d.weekday() == 2:
            closed.add(d)
        d += datetime.timedelta(days=1)

    closed.update(SPECIAL_CLOSURES.keys())
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
                "1 an jedem Kalendertag, an dem die NYSE einen sonst reguleren "
                "Handelstag (Mo-Fr) wegen eines Feiertags oder einer "
                "Sonderschliessung GANZTAGS geschlossen war, sonst 0 (auch an "
                "Wochenenden 0). Deckt die 10 wiederkehrenden Feiertage "
                "(inkl. historischer, heute nicht mehr beobachteter wie Lincoln's "
                "Birthday/Columbus Day/Armistice Day, jeweils nur bis 1953, und "
                "Election Day bis 1968 bzw. 1972/1976/1980) sowie ~20 "
                "dokumentierte Sonderschliessungen (Staatstrauer, 9/11, Hurrikane, "
                "1968er 'Paperwork Crisis'-Mittwoche) ab, NICHT jedoch reine "
                "Handelsverkuerzungen (z.B. 'Closed at 1:00 pm' am Tag vor "
                "Weihnachten/Thanksgiving seit den 1970ern), die laut Quelle "
                "keine volle Schliessung sind."
            ),
            "quelle_url": (
                "https://www.ltadvisors.net/Info/research/closings.pdf und "
                "https://s3.amazonaws.com/armstrongeconomics-wp/2013/07/NYSE-Closings.pdf "
                "('History of New York Stock Exchange Holidays' und 'New York Stock "
                "Exchange Special Closings, 1885-date', NYSE-Dokument, revidiert bis "
                "Januar 2011); ab Jan. 2011 durch dokumentierte, allgemein bekannte "
                "Feiertagsregeln (siehe Quellcode) und zwei oeffentlich bekannte "
                "Sonderschliessungen (Hurrikan Sandy 2012, Trauertag Bush 2018) fortgeschrieben."
            ),
            "verdichtung": "keine (deterministische, aus amtlicher/dokumentierter Feiertagshistorie abgeleitete Kalenderreihe, kein externer taeglicher Datenabruf)",
            "publikation": "taeglich (Schliessungstatsache am selben Tag oeffentlich bekannt; historische Feiertage im Voraus bekannt, Sonderschliessungen teils erst kurzfristig)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
