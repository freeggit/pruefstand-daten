#!/usr/bin/env python3
"""ADP National Employment Report Veroeffentlichungstage: 1 am Tag der monatlichen
Veroeffentlichung, sonst 0. Terminliste aus dem oeffentlichen ALFRED-Textexport
(Release rid=194, kein Schluessel, kein Login). ALFRED fuehrt ADP-Termine ab
2011-02-02; Start 2011-01-01 (frueher nichts erfunden). Termine werden von ADP im
Voraus als Jahreskalender veroeffentlicht."""
import datetime
import gzip
import io
import json
import os
import re
import urllib.request

ID = "adp_beschaeftigung_termine"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
URL = "https://alfred.stlouisfed.org/release/downloaddates?rid=194&ff=txt"
START = datetime.date(2011, 1, 1)
DATE_PAT = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def daterange(start, end):
    d = start
    one = datetime.timedelta(days=1)
    while d <= end:
        yield d
        d += one


def fetch_release_dates():
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8", "replace")
    dates = set()
    for line in text.splitlines():
        line = line.strip()
        if DATE_PAT.match(line):
            dates.add(datetime.date.fromisoformat(line))
    if not dates:
        raise SystemExit("keine Veroeffentlichungstermine gefunden")
    return dates


def nur_releases(dates):
    return dates, []


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
    all_dates = fetch_release_dates()
    event_days, entfernt = nur_releases({d for d in all_dates if d >= START})
    if not event_days:
        raise SystemExit("keine Veroeffentlichungstermine ab %s" % START.isoformat())
    rows = [(d, 1 if d in event_days else 0) for d in daterange(START, end)]
    gzip_write(os.path.join(OUT_DIR, "adp.csv.gz"), rows)

    meta = {
        "adp": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am Veroeffentlichungstag des monatlichen ADP National Employment Report (privater Beschaeftigungsbericht, zwei Tage vor dem BLS-Arbeitsmarktbericht), sonst 0, fuer jeden Kalendertag ab 2011-01-01 bis heute. Termine aus dem ALFRED-Archiv der tatsaechlichen Veroeffentlichungstage dieses Release (rid=194).",
            "quelle_url": "https://alfred.stlouisfed.org/release/downloaddates?rid=194&ff=txt (Terminarchiv, ALFRED/Federal Reserve Bank of St. Louis) und https://adpemploymentreport.com/",
            "verdichtung": "keine (ein Termin je Kalendertag, aus amtlichem Terminarchiv uebernommen)",
            "publikation": "taeglich (Veroeffentlichungstermin von ADP im Voraus als Jahreskalender oeffentlich, https://adpemploymentreport.com/)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
            "entfernte_vintages": [d.isoformat() for d in entfernt],
            "entfernte_vintages_grund": "keine",
        },
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
