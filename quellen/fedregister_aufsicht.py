#!/usr/bin/env python3
"""Federal Register: taegliche Anzahl veroeffentlichter Dokumente je Aufsichtsbehoerde.

Mechanismus (Zusatz 6): Tage mit ungewoehnlich hoher Zahl an Regeln/Bekanntmachungen
einer Finanz- oder Wettbewerbsaufsicht (SEC, FTC, Antitrust Division) koennen kurzfristig
regulatorisch exponierte Sektoren (v.a. XLF; bei Antitrust auch M&A-lastige Sektoren wie
XLK/XLC) gegenueber dem Weltindex bewegen, analog zu Ereignisstudien zu SEC-Durchsetzungs-
Ankuendigungen in der Fachliteratur. Publikationsdatum im Federal Register ist der Tag, an
dem das Dokument oeffentlich wird (verfuegbar_nach_tagen 0). Historie ab 1994 (Beginn der
strukturierten Federal-Register-API, Zusatz 4: Schwerpunkt Historie vor 1990/1995).
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

ID = "fedregister_aufsicht"
BASE = "https://www.federalregister.gov/api/v1/documents.json"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
START_YEAR = 1994

SERIES = {
    "sec": ("securities-and-exchange-commission", "Securities and Exchange Commission"),
    "ftc": ("federal-trade-commission", "Federal Trade Commission"),
    "antitrust": ("antitrust-division", "Antitrust Division (US-Justizministerium)"),
}


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


def fetch_year_counts(slug, year, counts):
    page = 1
    per_page = 1000
    while True:
        params = {
            "conditions[agencies][]": slug,
            "conditions[publication_date][year]": str(year),
            "per_page": str(per_page),
            "page": str(page),
            "fields[]": "publication_date",
            "order": "oldest",
        }
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
    meta = {}
    os.makedirs(OUT_DIR, exist_ok=True)
    for reihe, (slug, name) in SERIES.items():
        counts = {}
        for year in range(START_YEAR, current_year + 1):
            fetch_year_counts(slug, year, counts)

        first_day = datetime.date(START_YEAR, 1, 1)
        last_day = max(datetime.date.fromisoformat(d) for d in counts)
        rows = []
        d = first_day
        while d <= last_day:
            iso = d.isoformat()
            rows.append((iso, counts.get(iso, 0)))
            d += datetime.timedelta(days=1)

        gzip_write(os.path.join(OUT_DIR, reihe + ".csv.gz"), rows)
        meta[reihe] = {
            "einheit": "Anzahl Dokumente",
            "beschreibung": "Taegliche Anzahl im Federal Register veroeffentlichter Dokumente (Regeln, Vorschlaege, Bekanntmachungen) der %s, 0 an Tagen ohne Veroeffentlichung." % name,
            "quelle_url": "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=" + slug,
            "verdichtung": "Anzahl Dokumente je Kalendertag (Publikationsdatum)",
            "publikation": "taeglich (Federal Register erscheint an jedem US-Bankarbeitstag; Dokument gilt an seinem gedruckten Publikationsdatum als oeffentlich)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        }

    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
