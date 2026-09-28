#!/usr/bin/env python3
"""Federal Register: taegliche Anzahl Antidumping-/Ausgleichszoll-Dokumente.

Mechanismus (Zusatz 2/Punkt 5, Handelspolitik): neue Anordnungen, vorlaeufige
Feststellungen und Untersuchungseroeffnungen zu Antidumping- und Ausgleichszoll-
massnahmen des US-Handelsministeriums (International Trade Administration) im
Federal Register veraendern kurzfristig (1 bis 20 Handelstage) die Kostenlage
importexponierter Sektoren (v.a. Grundstoffe XLB, Industrie XLI) gegenueber dem
Weltindex, analog zur Ereignisstudien-Literatur zu Handelspolitik-Ankuendigungen
(z.B. Sektionen-301/232-Zoelle 2018/19). Ersetzt den urspruenglich vorgesehenen
USITC-Dokumentensuche-Kandidaten (usitc.gov/trade_remedy/documents_search liefert
404, Seite offenbar umstrukturiert); nutzt stattdessen dieselbe bereits bewaehrte
Federal-Register-API wie fedregister_aufsicht, hier mit Volltextsuche nach
Antidumping-/Ausgleichszoll-Begriffen statt Agentur-Gesamtzahl (sonst waere die
Reihe nur eine Redundanz-Variante von fedregister_aufsicht, Zusatz 3 erlaubt dort
maximal 3 aktive Reihen und die sind mit sec/ftc/antitrust bereits belegt).
"""
import datetime
import gzip
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

ID = "fedregister_handelsschutz"
BASE = "https://www.federalregister.gov/api/v1/documents.json"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
START_YEAR = 1994
AGENCIES = ["international-trade-administration", "international-trade-commission"]
TERM = "antidumping OR countervailing"


def fetch_json(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


def fetch_year_counts(year, counts):
    page = 1
    per_page = 1000
    while True:
        params = [("conditions[agencies][]", a) for a in AGENCIES]
        params += [
            ("conditions[term]", TERM),
            ("conditions[publication_date][year]", str(year)),
            ("per_page", str(per_page)),
            ("page", str(page)),
            ("fields[]", "publication_date"),
            ("order", "oldest"),
        ]
        url = BASE + "?" + urllib.parse.urlencode(params)
        data = fetch_json(url)
        results = data.get("results", [])
        for r in results:
            d = r.get("publication_date")
            if not d:
                continue
            counts[d] = counts.get(d, 0) + 1
        total_pages = data.get("total_pages", 1)
        if page >= total_pages or not results:
            break
        page += 1


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
    current_year = datetime.date.today().year
    counts = {}
    for year in range(START_YEAR, current_year + 1):
        fetch_year_counts(year, counts)

    if not counts:
        raise RuntimeError("keine Dokumente gefunden")

    first_day = datetime.date(START_YEAR, 1, 1)
    last_day = max(datetime.date.fromisoformat(d) for d in counts)
    rows = []
    d = first_day
    while d <= last_day:
        iso = d.isoformat()
        rows.append((iso, counts.get(iso, 0)))
        d += datetime.timedelta(days=1)

    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "verfuegungen.csv.gz"), rows)

    meta = {
        "verfuegungen": {
            "einheit": "Anzahl Dokumente",
            "beschreibung": (
                "Taegliche Anzahl im Federal Register veroeffentlichter Dokumente "
                "(Anordnungen, vorlaeufige/endgueltige Feststellungen, Untersuchungs-"
                "eroeffnungen) der US-Handelsschutzbehoerden (International Trade "
                "Administration, International Trade Commission) mit Volltextsuche "
                "'antidumping OR countervailing', 0 an Tagen ohne Veroeffentlichung."
            ),
            "quelle_url": (
                "https://www.federalregister.gov/api/v1/documents.json?"
                "conditions%5Bagencies%5D%5B%5D=international-trade-administration&"
                "conditions%5Bagencies%5D%5B%5D=international-trade-commission&"
                "conditions%5Bterm%5D=antidumping+OR+countervailing"
            ),
            "verdichtung": "Anzahl Treffer je Kalendertag (Publikationsdatum)",
            "publikation": (
                "taeglich (Federal Register erscheint an jedem US-Bankarbeitstag; "
                "Dokument gilt an seinem gedruckten Publikationsdatum als oeffentlich)"
            ),
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
