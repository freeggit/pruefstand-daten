#!/usr/bin/env python3
"""USDA NASS Acreage (jaehrlich, Ende Juni) und Grain Stocks (quartalsweise) Veroeffentlichungstage:
je Reihe 1 am Berichtstag, sonst 0, fuer jeden Kalendertag bis heute. usda.gov ist gesperrt; die Terminlisten kommen
vom amtlichen Archiv esmis.nal.usda.gov (National Agricultural Library), das jeden tatsaechlich erschienenen Bericht
mit Datum fuehrt. NASS veroeffentlicht den Kalender jeweils im Voraus (Zusatz 5). Start: Acreage 1975, Grain Stocks 1973."""
import datetime
import gzip
import io
import json
import os
import re
import time
import urllib.request

ID = "usda_acreage_grainstocks_termine"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
BASE_URL = "https://esmis.nal.usda.gov/publication/"
ROW_PAT = re.compile(r'views-field-release-date"><time datetime="(\d{4}-\d{2}-\d{2})T')
MAX_PAGES = 90
def daterange(start, end):
    d = start
    one = datetime.timedelta(days=1)
    while d <= end:
        yield d
        d += one


def fetch_page(name, page):
    url = BASE_URL + name if page == 0 else "%s%s?page=%d" % (BASE_URL, name, page)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def fetch_all_dates(name):
    dates = set()
    empty_streak = 0
    for page in range(MAX_PAGES):
        html = fetch_page(name, page)
        found = ROW_PAT.findall(html)
        if not found:
            empty_streak += 1
            if empty_streak >= 2:
                break
        else:
            empty_streak = 0
            for s in found:
                dates.add(datetime.date.fromisoformat(s))
        time.sleep(0.1)
    if not dates:
        raise SystemExit("keine Termine gefunden")
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


SERIEN = {
    "acreage": ("acreage", "USDA-NASS-Bericht Acreage (Anbauflaechen, jaehrlich Ende Juni)"),
    "grain_stocks": ("grain-stocks", "USDA-NASS-Bericht Grain Stocks (Lagerbestaende, quartalsweise)"),
}


def main():
    end = datetime.datetime.now(datetime.timezone.utc).date()
    meta = {}
    for reihe, (name, text) in SERIEN.items():
        dates = fetch_all_dates(name)
        start = min(dates)
        rows = [(d, 1 if d in dates else 0) for d in daterange(start, end)]
        gzip_write(os.path.join(OUT_DIR, reihe + ".csv.gz"), rows)
        meta[reihe] = {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am Veroeffentlichungstag des %s, sonst 0, fuer jeden Kalendertag ab %s bis heute. Termine aus der ESMIS-Archivliste (National Agricultural Library)." % (text, start.isoformat()),
            "quelle_url": BASE_URL + name,
            "verdichtung": "keine (ein Termin je Kalendertag)",
            "publikation": "taeglich (NASS veroeffentlicht den Berichtskalender im Voraus; ESMIS zeichnet die tatsaechlichen Erscheinungstage auf)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
