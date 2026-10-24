#!/usr/bin/env python3
"""US-JOLTS (offene Stellen) Veroeffentlichungstage: 1 am Tag der monatlichen
BLS-Veroeffentlichung, sonst 0. bls.gov ist aus dieser Umgebung mit HTTP 403
gesperrt; Terminliste aus dem oeffentlichen ALFRED-Textexport (alfred.stlouisfed.org,
Release rid=192, kein Schluessel, kein Login). ALFRED fuehrt JOLTS-Termine ab 2010;
Start 2010-01-01 (frueher nicht im Archiv, nichts erfunden). Im Voraus bekannt:
BLS-Jahreskalender nach OMB Statistical Policy Directive No. 3 (1985)."""
import datetime
import gzip
import io
import json
import os
import re
import urllib.request

ID = "bls_jolts_veroeffentlichung_termine"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
URL = "https://alfred.stlouisfed.org/release/downloaddates?rid=192&ff=txt"
START = datetime.date(2010, 1, 1)
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
    gzip_write(os.path.join(OUT_DIR, "jolts.csv.gz"), rows)

    meta = {
        "jolts": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am Veroeffentlichungstag des monatlichen US-JOLTS-Berichts (offene Stellen, BLS), sonst 0, fuer jeden Kalendertag ab 2010-01-01 bis heute. Termine aus dem ALFRED-Archiv der tatsaechlichen Veroeffentlichungstage dieses Release (rid=192).",
            "quelle_url": "https://alfred.stlouisfed.org/release/downloaddates?rid=192&ff=txt (Terminarchiv, ALFRED/Federal Reserve Bank of St. Louis) und https://www.bls.gov/jlt/ (Urheber-Release, aus dieser Umgebung mit HTTP 403 gesperrt, siehe Katalog)",
            "verdichtung": "keine (ein Termin je Kalendertag, aus amtlichem Terminarchiv uebernommen)",
            "publikation": "taeglich (Veroeffentlichungstermin laut OMB Statistical Policy Directive No. 3 (1985) im Voraus als Jahreskalender oeffentlich bekannt gegeben, https://www.bls.gov/bls/statistical-policy-directive-3.pdf)",
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
