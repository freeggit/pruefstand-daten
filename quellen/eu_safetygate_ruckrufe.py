#!/usr/bin/env python3
import datetime
import gzip
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ID = "eu_safetygate_ruckrufe"
LIST_URL = "https://ec.europa.eu/safety-gate-alerts/api/download/weeklyReport/list/xml/en"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
# K2 verlangt Beginn spaetestens 31.12.2015; die volle Historie reicht bis 2005
# zurueck, wuerde aber pro Lauf ueber 1100 Einzelabrufe benoetigen und damit
# K7 (3 Minuten) verletzen. Darum ab 2015-12-31.
FIRST_ALLOWED = datetime.date(2015, 12, 31)
WORKERS = 10


def fetch(url, tries=3):
    last_err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_err = e
            if i < tries - 1:
                time.sleep(2 * (i + 1))
    raise last_err


def gzip_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        text = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        text.write("datum,wert\n")
        for d, v in rows:
            text.write("%s,%s\n" % (d, v))
        text.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    today = datetime.datetime.now(datetime.timezone.utc).date()

    list_xml = fetch(LIST_URL)
    entries = re.findall(r"<weeklyReport>.*?</weeklyReport>", list_xml, re.S)
    weeks = []
    for e in entries:
        dm = re.search(r"<publicationDate>(.*?)</publicationDate>", e)
        um = re.search(r"<URL>(.*?)</URL>", e)
        if not dm or not um:
            continue
        try:
            d = datetime.datetime.strptime(dm.group(1), "%d/%m/%Y").date()
        except ValueError:
            continue
        if d < FIRST_ALLOWED or d > today:
            continue
        url = um.group(1).replace("&amp;", "&")
        weeks.append((d, url))

    if not weeks:
        raise RuntimeError("keine Wochenberichte gefunden")

    weeks.sort()

    def count_week(item):
        d, url = item
        try:
            detail = fetch(url)
        except Exception:
            return (d, None)
        n = len(re.findall(r"<order>\d+</order>", detail))
        return (d, n)

    counts = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for d, n in ex.map(count_week, weeks):
            if n is None:
                continue
            counts[d] = counts.get(d, 0) + n

    if not counts:
        raise RuntimeError("keine Wochenberichte erfolgreich abgerufen")

    first_day = min(counts)
    last_day = max(counts)

    rows = []
    cur = first_day
    while cur <= last_day:
        iso = cur.isoformat()
        rows.append((iso, counts.get(cur, 0)))
        cur += datetime.timedelta(days=1)

    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "meldungen.csv.gz"), rows)

    meta = {
        "meldungen": {
            "einheit": "Anzahl Meldungen",
            "beschreibung": (
                "Taegliche Anzahl gefaehrlicher Nicht-Lebensmittel-Produkte, die im "
                "EU-Schnellwarnsystem Safety Gate (vormals RAPEX) gemeldet wurden. "
                "Safety Gate veroeffentlicht wochentlich (freitags) einen Sammelbericht "
                "mit allen Meldungen der Woche; die Anzahl Meldungen je Bericht wird auf "
                "den Publikationstag (Freitag) gebucht, alle uebrigen Wochentage sind "
                "echte Nullwerte (keine Schaetzung, an diesen Tagen erscheint kein "
                "Bericht). Ab 2015-12-31 (K2); die volle Historie beginnt 2005, wurde "
                "aber wegen K7 (3 Minuten je Abruf) nicht vollstaendig geholt. "
                "Mechanismus wie CPSC-Ruckrufe (cpsc_ruckrufe), aber unabhaengige "
                "EU-Behoerde/-Jurisdiktion: Sicherheits-/Qualitaetsprobleme betroffener "
                "Hersteller/Haendler koennen kurzfristig (1 bis 20 Handelstage) Vertrauen "
                "und Umsatz im Konsumsektor (XLY, XLP) gegenueber dem Weltindex belasten. "
                "Jeder Wochenbericht traegt ein Feld report_addendum fuer nachtraegliche "
                "Ergaenzungen zur selben Woche; in Stichproben (u.a. der aelteste und der "
                "juengste Bericht) war es leer, eine kuenftige Revision ist aber nicht "
                "ausgeschlossen."
            ),
            "quelle_url": "https://ec.europa.eu/safety-gate-alerts/api/download/weeklyReport/list/xml/en",
            "verdichtung": (
                "Summe der Meldungen (Anzahl <order>-Eintraege) je Wochenbericht, "
                "gebucht auf publicationDate (Freitag); uebrige Wochentage = 0"
            ),
            "publikation": (
                "woechentlich: Safety Gate veroeffentlicht jeden Freitag einen "
                "Sammelbericht (Feld publicationDate der weeklyReport-Liste); "
                "einzelne Meldungen tragen kein eigenes Tagesdatum innerhalb der Woche"
            ),
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
