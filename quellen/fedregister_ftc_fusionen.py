#!/usr/bin/env python3
"""Federal Register: taegliche Anzahl FAA-Lufttuechtigkeitsanweisungen (Airworthiness Directives).

Mechanismus (Zusatz 6, Prioritaet 5, Flugzeug-/Industrieunfaelle): verbindliche
FAA-Anweisungen zu Flugzeugtypen, Triebwerken und Bauteilen (Rule-Dokumente
'Airworthiness Directives') belasten Hersteller und Betreiber (Luft- und
Raumfahrt, Industrie XLI) mit Nachruest- und Ausfallkosten; Notfall-Anweisungen
(Grounding) koennen kurzfristig (1 bis 20 Handelstage) einzelne Titel und damit
den Sektor gegenueber dem Weltindex bewegen. Ergaenzt ntsb_luftfahrtunfaelle
(Unfaelle) um die regulatorische Reaktion.
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

ID = "fedregister_ftc_fusionen"
BASE = "https://www.federalregister.gov/api/v1/documents.json"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
START_YEAR = 1994
AGENCIES = ["federal-trade-commission"]
TERM = 'consent agreement'


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
            ("conditions[type][]", "NOTICE"),
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
    gzip_write(os.path.join(OUT_DIR, "consent_agreements.csv.gz"), rows)

    meta = {
        "consent_agreements": {
            "einheit": "Anzahl Dokumente",
            "beschreibung": 'Taegliche Anzahl im Federal Register veroeffentlichter FTC-Notices mit Volltext-Treffer "consent agreement" (Agentur federal-trade-commission, Dokumenttyp Notice), 0 an Tagen ohne Veroeffentlichung. Datum = Veroeffentlichungsdatum im FR.',
            "quelle_url": 'https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=federal-trade-commission&conditions%5Bterm%5D=consent+agreement&conditions%5Btype%5D%5B%5D=NOTICE',
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
