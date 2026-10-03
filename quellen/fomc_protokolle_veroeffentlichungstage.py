#!/usr/bin/env python3
"""FOMC-Protokolle: 1 am Tag der Veroeffentlichung der Sitzungsprotokolle (Minutes), sonst 0,
fuer jeden Kalendertag ab 2008-01-01 bis heute. Quelle: Seiten des Federal Reserve Board
(fomchistorical<JJJJ>.htm fuer 2008-2020, fomccalendars.htm fuer 2021 ff.), Zeilen
'Minutes (Released <Datum>)' bzw. 'Released <Datum>'. Termine in der Zukunft werden nicht
geschrieben. Vor 2008 nennen die Seiten keine Veroeffentlichungsdaten -> kein Beginn davor."""
import datetime, gzip, io, json, os, re, urllib.request

ID = "fomc_protokolle_veroeffentlichungstage"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
BASE = "https://www.federalreserve.gov/monetarypolicy/"
PAT = re.compile(r"Released\s+([A-Z][a-z]+)\s+(\d{1,2}),\s+(20\d\d)")


def get(u):
    r = urllib.request.Request(u, headers={"User-Agent": UA})
    return urllib.request.urlopen(r, timeout=30).read().decode("utf-8", "replace")


def parse(html):
    out = set()
    for m, d, y in PAT.findall(html):
        out.add(datetime.datetime.strptime("%s %s %s" % (m[:3], d, y), "%b %d %Y").date())
    return out


def main():
    today = datetime.datetime.now(datetime.timezone.utc).date()
    ev = set()
    for y in range(2008, 2021):
        s = parse(get(BASE + "fomchistorical%d.htm" % y))
        if len(s) < 6:
            raise SystemExit("Seite %d liefert nur %d Termine" % (y, len(s)))
        ev |= {d for d in s if d.year == y or d.year == y + 1}
    ev |= {d for d in parse(get(BASE + "fomccalendars.htm")) if d.year >= 2021}
    # Unplanmaessige Sitzungen (Maerz 2020, Telefonkonferenzen): Termin war nicht im Voraus bekannt
    ev -= {datetime.date(2020, 3, 3), datetime.date(2020, 3, 23)}
    ev = {d for d in ev if d <= today}
    start = datetime.date(2008, 1, 1)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        d = start
        while d <= today:
            t.write("%s,%d\n" % (d.isoformat(), 1 if d in ev else 0))
            d += datetime.timedelta(days=1)
        t.flush()
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "protokolle.csv.gz"), "wb").write(buf.getvalue())
    meta = {"protokolle": {
        "einheit": "Indikator (0/1)",
        "beschreibung": "1 am Tag der Veroeffentlichung der FOMC-Sitzungsprotokolle (Minutes, i.d.R. 3 Wochen nach der Sitzung, 14 Uhr Washingtoner Zeit), sonst 0, ab 2008-01-01. Termine stehen im Fed-Kalender im Voraus.",
        "quelle_url": BASE + "fomccalendars.htm",
        "verdichtung": "keine (Ereignisreihe)",
        "publikation": "taeglich (Veroeffentlichungstermin der Protokolle ist im Fed-Kalender vorab bekannt; Quelle: federalreserve.gov/monetarypolicy/fomccalendars.htm)",
        "verfuegbar_nach_tagen": 0,
        "revidiert": False}}
    json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), ensure_ascii=False, indent=2, sort_keys=True)
    print(len(ev), "Termine")


main()
