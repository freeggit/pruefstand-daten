#!/usr/bin/env python3
"""USDA WASDE (World Agricultural Supply and Demand Estimates) Veroeffentlichungs-
tage: 1 am Tag der monatlichen Berichtsveroeffentlichung, sonst 0. usda.gov selbst
ist aus dieser Umgebung mit HTTP 403 gesperrt; die vollstaendige Terminliste seit
1973 kommt stattdessen vom amtlichen Nachfolgeportal der National Agricultural
Library, https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-
demand-estimates (Economics, Statistics and Market Information System, andere
Domain als usda.gov, oeffentlich, kein Login, kein Schluessel; listet jeden
tatsaechlich erschienenen Bericht mit Datum, paginiert 10 je Seite). Die
Jahrestermine werden von USDA/OCE im Voraus als offizieller Freigabekalender
veroeffentlicht (siehe z.B. cmegroup.com-Uebersicht der 2026-Termine); die hier
verwendete ESMIS-Archivliste der tatsaechlichen Erscheinungstage ist die amtliche
Aufzeichnung dieser im Voraus bekannten Termine (Zusatz 5: keine Termine ohne
Beleg). Start 1973-09-17 (fruehester in ESMIS gelisteter WASDE-Bericht)."""
import datetime
import gzip
import io
import json
import os
import re
import time
import urllib.request

ID = "usda_wasde_veroeffentlichung"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
BASE_URL = "https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates"
ROW_PAT = re.compile(
    r'headers="view-release-date-table-column" class="views-field views-field-release-date">'
    r'<time datetime="(\d{4}-\d{2}-\d{2})T'
)
MAX_PAGES = 90


def daterange(start, end):
    d = start
    one = datetime.timedelta(days=1)
    while d <= end:
        yield d
        d += one


def fetch_page(page):
    url = BASE_URL if page == 0 else "%s?page=%d" % (BASE_URL, page)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def fetch_all_dates():
    dates = set()
    empty_streak = 0
    for page in range(MAX_PAGES):
        html = fetch_page(page)
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
        raise SystemExit("keine WASDE-Termine gefunden")
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
    all_dates = fetch_all_dates()
    start = min(all_dates)
    rows = [(d, 1 if d in all_dates else 0) for d in daterange(start, end)]
    gzip_write(os.path.join(OUT_DIR, "wasde.csv.gz"), rows)

    meta = {
        "wasde": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am Veroeffentlichungstag des monatlichen USDA-WASDE-Berichts (World Agricultural Supply and Demand Estimates), sonst 0, fuer jeden Kalendertag ab %s bis heute. Termine aus der amtlichen ESMIS-Archivliste (National Agricultural Library) der tatsaechlich erschienenen Berichte." % start.isoformat(),
            "quelle_url": "https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates (amtliches Archiv, National Agricultural Library) und https://www.usda.gov/oce/commodity/wasde/ (Urheber-Release, aus dieser Umgebung mit HTTP 403 gesperrt)",
            "verdichtung": "keine (ein Termin je Kalendertag, aus amtlichem Archiv uebernommen)",
            "publikation": "taeglich (Freigabekalender von USDA/OCE im Voraus je Jahr veroeffentlicht, z.B. https://www.cmegroup.com/articles/2026/understanding-major-usda-reports-in-2026.html; ESMIS-Archiv zeichnet die tatsaechlichen Erscheinungstage dieser im Voraus bekannten Termine auf)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
