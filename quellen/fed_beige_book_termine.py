#!/usr/bin/env python3
"""Fed Beige Book: 1 am Veroeffentlichungstag, sonst 0, fuer jeden Kalendertag ab 1996-10-30 bis
heute. Quelle: Jahresseiten beigebook<JJJJ>.htm des Federal Reserve Board (Zeilen 'Monat Tag:').
Die Veroeffentlichungstermine stehen im Voraus im Fed-Kalender; Termine in der Zukunft werden nicht
geschrieben. Vor dem 30.10.1996 fuehrt das Archiv keine Termine -> kein Beginn davor."""
import datetime, gzip, io, json, os, re, urllib.request

ID = "fed_beige_book_termine"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
BASE = "https://www.federalreserve.gov/monetarypolicy/beigebook%d.htm"
PAT = re.compile(r"<td>\s*([A-Z][a-z]+)\.?\s+(\d{1,2})\s*(?::|</td>)")


def get(u):
    r = urllib.request.Request(u, headers={"User-Agent": UA})
    return urllib.request.urlopen(r, timeout=30).read().decode("utf-8", "replace")


def main():
    today = datetime.datetime.now(datetime.timezone.utc).date()
    ev = set()
    for y in range(1996, today.year + 1):
        if y == today.year:
            # Jahresseite des laufenden Jahres fehlt (404): Einzelseiten beigebook<JJJJ><MM>.htm,
            # erstes Datum 'Monat Tag, JJJJ' der Seite = Veroeffentlichungstag
            for mm in range(1, 13):
                try:
                    h = get("https://www.federalreserve.gov/monetarypolicy/beigebook%d%02d.htm" % (y, mm))
                except Exception:
                    continue
                mo = re.search(r"([A-Z][a-z]+) (\d{1,2}), %d" % y, h)
                if mo:
                    ev.add(datetime.datetime.strptime("%s %s %d" % (mo.group(1)[:3], mo.group(2), y), "%b %d %Y").date())
            continue
        html = get(BASE % y)
        s = set()
        for m, d in PAT.findall(html):
            s.add(datetime.datetime.strptime("%s %s %d" % (m[:3], d, y), "%b %d %Y").date())
        if 1996 < y < today.year and len(s) < 6:
            raise SystemExit("Seite %d liefert nur %d Termine" % (y, len(s)))
        ev |= s
    ev = {d for d in ev if d <= today}
    start = min(ev)  # Archiv der Jahresseite 1996 beginnt am 30.10.1996
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
    open(os.path.join(OUT, "termine.csv.gz"), "wb").write(buf.getvalue())
    meta = {"termine": {
        "einheit": "Indikator (0/1)",
        "beschreibung": "1 am Veroeffentlichungstag des Fed Beige Book (ca. 2 Wochen vor jeder FOMC-Sitzung, 8x pro Jahr, 14 Uhr Washingtoner Zeit), sonst 0, ab 1996-10-30.",
        "quelle_url": "https://www.federalreserve.gov/monetarypolicy/beige-book-archive.htm",
        "verdichtung": "keine (Ereignisreihe)",
        "publikation": "taeglich (Veroeffentlichungstermine stehen im Voraus im Fed-Kalender; Quelle: federalreserve.gov/monetarypolicy/beige-book-default.htm)",
        "verfuegbar_nach_tagen": 0,
        "revidiert": False}}
    json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), ensure_ascii=False, indent=2, sort_keys=True)
    print(len(ev), "Termine")


main()
