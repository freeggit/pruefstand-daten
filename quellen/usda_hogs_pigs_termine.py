#!/usr/bin/env python3
"""USDA NASS Quarterly Hogs and Pigs, Veroeffentlichungstage: 1 am Tag der
Veroeffentlichung (Ende Maerz/Juni/September/Dezember), sonst 0. Terminliste aus
dem oeffentlichen USDA-ESMIS-Archiv (esmis.nal.usda.gov, kein Schluessel, kein Login),
Seitendurchlauf bis zur leeren Seite. NASS gibt den Kalender im Voraus bekannt."""
import datetime
import gzip
import io
import json
import os
import re
import urllib.request

ID = "usda_hogs_pigs_termine"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
URL = "https://esmis.nal.usda.gov/publication/hogs-and-pigs?page=%d"
START = datetime.date(2005, 1, 1)  # davor im Archiv zusaetzliche Nicht-Quartalstermine (2001-2004)
PAT = re.compile(r"hogs-and-pigs/((?:19|20)\d\d-\d\d-\d\d)")


def daterange(start, end):
    d = start
    one = datetime.timedelta(days=1)
    while d <= end:
        yield d
        d += one


def fetch_release_dates():
    dates = set()
    for page in range(0, 60):
        req = urllib.request.Request(URL % page, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", "replace")
        found = set(PAT.findall(text))
        if not found:
            break
        dates |= {datetime.date.fromisoformat(x) for x in found}
    if not dates:
        raise SystemExit("keine Veroeffentlichungstermine gefunden")
    return dates


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
    event_days = fetch_release_dates()
    start = max(min(event_days).replace(month=1, day=1), START)
    rows = [(d, 1 if d in event_days else 0) for d in daterange(start, end)]
    gzip_write(os.path.join(OUT_DIR, "hogs_pigs.csv.gz"), rows)
    meta = {
        "hogs_pigs": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am Veroeffentlichungstag des vierteljaehrlichen USDA-NASS-Berichts Hogs and Pigs (Schweinebestand), sonst 0, fuer jeden Kalendertag ab 2005-01-01 bis heute (Archiv enthaelt vereinzelt Zusatztermine, z.B. 2016-03-21, 2018-12-10). Termine aus dem ESMIS-Archiv.",
            "quelle_url": "https://esmis.nal.usda.gov/publication/hogs-and-pigs",
            "verdichtung": "keine (ein Termin je Kalendertag, aus amtlichem Archiv uebernommen)",
            "publikation": "taeglich (NASS veroeffentlicht den Berichtskalender im Voraus, https://www.nass.usda.gov/Publications/Calendar/; Archivtermin = tatsaechlicher Veroeffentlichungstag)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
