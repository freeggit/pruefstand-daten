#!/usr/bin/env python3
import datetime
import gzip
import io
import json
import os
import re
import urllib.error
import urllib.request

ID = "kalender_ereignisse"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
START = datetime.date(2001, 1, 1)
# Zusatz 4 (25.9.2026), E11 Historie vor 1990: ustax bleibt vorerst bei 2001 (Regeländerungen
# der US-Vierteljahres-Steuertermine vor 1967/1954 nicht abschliessend belegt, siehe grund in
# katalog.json); opex_verfall und fomc_sitzung sind so weit zurueckverlaengert, wie die
# jeweilige Quelle/der Marktmechanismus belegt ist (keine Tage erfunden).
OPEX_START = datetime.date(1973, 4, 27)  # Tag nach Beginn des boersengehandelten Optionshandels (CBOE, 26.4.1973)
FOMC_START = datetime.date(1936, 1, 1)  # erstes Jahr mit von der Fed veroeffentlichten historischen Sitzungsunterlagen
TAX_MONTHS_DAYS = ((1, 15), (4, 15), (6, 15), (9, 15), (12, 15))
QUARTER_MONTHS = (3, 6, 9, 12)
FOMC_HISTORICAL_LAST_YEAR = 2020
FOMC_MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}
# Gruppe 4 faengt eine optionale Klammerannotation ("(unscheduled)", "(cancelled)",
# "(notation vote)") ein: Zusatz 5 (25.9.2026) verlangt nur planmaessige Sitzungen mit
# im Voraus bekanntem Termin, also ohne "Conference Call" (Telefonkonferenz,
# typischerweise ausserplanmaessige Notfallaktionen) und ohne als "unscheduled" oder
# "cancelled" annotierte Eintraege.
FOMC_HIST_PAT = re.compile(
    r'([A-Za-z]+) (\d{1,2})(?:-(\d{1,2}))?\s*(?:\(([^)]*)\)\s*)?(Meeting|Conference Call)'
)
FOMC_EXCLUDE_NOTE = re.compile(r"unscheduled|cancelled", re.I)
FOMC_CAL_PAT = re.compile(
    r'fomc-meeting__month[^>]*><strong>([A-Za-z]+)</strong></div>\s*'
    r'<div class="fomc-meeting__date[^>]*>([^<]+)</div>', re.S
)
FOMC_CAL_YEAR_PAT = re.compile(r'<h4><a id="\d+">(\d{4}) FOMC Meetings</a></h4>')


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
    for year in range(OPEX_START.year, end.year + 1):
        for month in QUARTER_MONTHS:
            d = third_friday(year, month)
            if d >= OPEX_START:
                event_days.add(d)
    return [(d, 1 if d in event_days else 0) for d in daterange(OPEX_START, end)]


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def fomc_historical_dates(year):
    url = "https://www.federalreserve.gov/monetarypolicy/fomchistorical%d.htm" % year
    try:
        html = http_get(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise
    out = []
    for month_name, d1, d2, note, mtype in FOMC_HIST_PAT.findall(html):
        if mtype != "Meeting":
            continue
        if note and FOMC_EXCLUDE_NOTE.search(note):
            continue
        month = FOMC_MONTHS.get(month_name)
        if not month:
            continue
        day = int(d2) if d2 else int(d1)
        out.append(datetime.date(year, month, day))
    return out


def fomc_calendar_dates():
    html = http_get("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm")
    pieces = FOMC_CAL_YEAR_PAT.split(html)
    out = []
    for i in range(1, len(pieces), 2):
        year = int(pieces[i])
        block = pieces[i + 1]
        for month_name, daytext in FOMC_CAL_PAT.findall(block):
            month = FOMC_MONTHS.get(month_name)
            if not month:
                continue
            m = re.match(r"(\d{1,2})(?:-(\d{1,2}))?", daytext.strip())
            if not m:
                continue
            d1, d2 = m.group(1), m.group(2)
            day = int(d2) if d2 else int(d1)
            out.append(datetime.date(year, month, day))
    return out


def fomc_decision_days(end):
    days = set()
    for year in range(FOMC_START.year, FOMC_HISTORICAL_LAST_YEAR + 1):
        days.update(fomc_historical_dates(year))
    days.update(fomc_calendar_dates())
    days = {d for d in days if FOMC_START <= d <= end}
    if not days:
        raise SystemExit("keine FOMC-Termine gefunden")
    return days


def build_fomc(end, decision_days):
    return [(d, 1 if d in decision_days else 0) for d in daterange(FOMC_START, end)]


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

    fomc_days = fomc_decision_days(end)

    rows_ustax = build_ustax(end)
    rows_opex = build_opex(end)
    rows_fomc = build_fomc(end, fomc_days)

    gzip_write(os.path.join(OUT_DIR, "ustax.csv.gz"), rows_ustax)
    gzip_write(os.path.join(OUT_DIR, "opex_verfall.csv.gz"), rows_opex)
    gzip_write(os.path.join(OUT_DIR, "fomc_sitzung.csv.gz"), rows_fomc)

    meta = {
        "ustax": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 an US-Steuerterminen (15.1., 15.4., 15.6., 15.9., 15.12., feste Kalenderdaten ohne Wochenend-/Feiertagsverschiebung), sonst 0, fuer jeden Kalendertag ab 2001-01-01.",
            "quelle_url": "https://www.irs.gov/filing/tax-day-when-are-taxes-due (feste, oeffentlich bekannte Kalendertermine)",
            "verdichtung": "keine (deterministische Kalenderreihe, kein externer Datenabruf)",
            "publikation": 'taeglich (Ereignisdatum im Voraus oeffentlich bekannt, Reihe wird taeglich fortgeschrieben)',
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
        "opex_verfall": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am dritten Freitag der Quartalsmonate Maerz/Juni/September/Dezember (grosser Verfall / Quadruple Witching, zugleich seit ca. 2005 Stichtag der S&P-Quartalsneugewichtung), sonst 0, fuer jeden Kalendertag ab 1973-04-27 (Tag nach Beginn des boersengehandelten Optionshandels an der CBOE, 26.4.1973; erster erfasster Verfalltag damit Juni 1973, siehe Zusatz 4 25.9.2026 E11).",
            "quelle_url": "https://www.cboe.com/optionsexpirationcalendar/ (Marktkonvention: dritter Freitag der Quartalsmonate) und https://www.cboe.com/about/history/ (Handelsbeginn 26.4.1973)",
            "verdichtung": "keine (deterministische Kalenderreihe, kein externer Datenabruf)",
            "publikation": 'taeglich (Ereignisdatum im Voraus oeffentlich bekannt, Reihe wird taeglich fortgeschrieben)',
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
        "fomc_sitzung": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am letzten Tag einer planmaessigen FOMC-Sitzung mit im Voraus oeffentlich bekanntem Termin, sonst 0, fuer jeden Kalendertag ab 1936-01-01 (erstes Jahr mit von der Fed veroeffentlichten historischen Sitzungsunterlagen unter fomchistorical<JAHR>.htm) bis heute. Zusatz 5 (25.9.2026): als 'Conference Call', 'unscheduled' oder 'cancelled' annotierte Telefonkonferenzen/Notfall-/Ad-hoc-Sitzungen sind ausgeschlossen, da deren Termin nicht im Voraus bekannt war.",
            "quelle_url": "https://www.federalreserve.gov/monetarypolicy/fomchistorical<JAHR>.htm (1936-2020) und https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm (ab 2021)",
            "verdichtung": "keine (aus amtlichen FOMC-Sitzungskalendern der Fed abgeleitet)",
            "publikation": 'taeglich (Ereignisdatum im Voraus oeffentlich bekannt, Reihe wird taeglich fortgeschrieben)',
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
