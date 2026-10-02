#!/usr/bin/env python3
"""US-Verbraucherpreisindex (CPI) Veroeffentlichungstage: 1 am Tag der
monatlichen BLS-Veroeffentlichung, sonst 0. bls.gov selbst ist aus dieser
Umgebung mit HTTP 403 gesperrt (siehe Katalog bls_veroeffentlichungstage,
gleicher Block wie sec.gov/edgar); die Terminliste kommt stattdessen aus dem
oeffentlichen ALFRED-Textexport (alfred.stlouisfed.org, andere Domain, kein
Schluessel, kein Login), der die vom Federal Reserve Bank of St. Louis
archivierten tatsaechlichen Veroeffentlichungstage dieses Release fuehrt.
Start 1985-01-01: OMB Statistical Policy Directive No. 3 (1985) verpflichtet
die BLS seither nachweislich zu einem im Voraus veroeffentlichten Jahres-
Terminkalender fuer Principal Federal Economic Indicators (u.a. CPI); fuer
die Jahre davor (ALFRED fuehrt CPI-Termine bereits ab 1949) ist eine
vergleichbare, im Voraus bekannte Ankuendigungspraxis nicht belegt, daher
hier nicht verwendet (Zusatz 5: keine historischen Termine ohne Beleg fuer
vorherige Bekanntheit)."""
import datetime
import gzip
import io
import json
import os
import re
import urllib.request

ID = "us_cpi_termine"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
URL = "https://alfred.stlouisfed.org/release/downloaddates?rid=10&ff=txt"
START = datetime.date(1985, 1, 1)
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


# Korrektur 2.10.2026 (Datenaudit): ALFRED fuehrt jedes Vintage-Datum des Release, nicht nur den
# monatlichen CPI-News-Release. (a) Jaehrliche Neuberechnung der Saisonfaktoren im Februar, wenige
# Tage VOR dem Januar-CPI (2005-2024 belegt mit dem BLS-Archiv https://www.bls.gov/bls/news-release/cpi.htm):
# stehen im Februar zwei Termine hoechstens 10 Tage auseinander, gilt nur der spaetere.
# (b) Einzeln belegte Zusatz-Vintages ohne CPI-Release.
KEIN_RELEASE = {datetime.date(2000, 2, 29), datetime.date(2000, 9, 28)}


def nur_releases(dates):
    entfernt = set(d for d in dates if d in KEIN_RELEASE)
    je_monat = {}
    for d in sorted(dates - entfernt):
        je_monat.setdefault((d.year, d.month), []).append(d)
    for (jahr, monat), tage in je_monat.items():
        if monat == 2 and len(tage) == 2 and (tage[1] - tage[0]).days <= 10:
            entfernt.add(tage[0])
    return dates - entfernt, sorted(entfernt)


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
    gzip_write(os.path.join(OUT_DIR, "cpi.csv.gz"), rows)

    meta = {
        "cpi": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am Veroeffentlichungstag des monatlichen US-Verbraucherpreisindex (CPI, BLS), sonst 0, fuer jeden Kalendertag ab 1985-01-01 bis heute. Termine aus dem ALFRED-Archiv der tatsaechlichen Veroeffentlichungstage dieses Release (rid=10).",
            "quelle_url": "https://alfred.stlouisfed.org/release/downloaddates?rid=10&ff=txt (Terminarchiv, ALFRED/Federal Reserve Bank of St. Louis) und https://www.bls.gov/cpi/ (Urheber-Release, aus dieser Umgebung mit HTTP 403 gesperrt, siehe Katalogeintrag bls_veroeffentlichungstage)",
            "verdichtung": "keine (ein Termin je Kalendertag, aus amtlichem Terminarchiv uebernommen)",
            "publikation": "taeglich (Veroeffentlichungstermin laut OMB Statistical Policy Directive No. 3 (1985) im Voraus als Jahreskalender oeffentlich bekannt gegeben, https://www.bls.gov/bls/statistical-policy-directive-3.pdf)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
            "entfernte_vintages": [d.isoformat() for d in entfernt],
            "entfernte_vintages_grund": "ALFRED-Vintages ohne CPI-News-Release (Saisonfaktor-Revision im Februar, belegte Einzelfaelle); Datenaudit 1.10.2026",
        },
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
