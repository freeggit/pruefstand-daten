#!/usr/bin/env python3
"""Federal Register: taegliche Anzahl Dokumente des US-Handelsbeauftragten (USTR).

Mechanismus (Firmenereignisse/Handelspolitik): Bekanntmachungen des USTR (Section-301-Untersuchungen und
-Zoelle, Ausnahmen von Zoellen, Handelsabkommen, Zollpraeferenzen) aendern kurzfristig die Kosten- und
Absatzlage importexponierter und exportabhaengiger Sektoren (Industrie XLI, Grundstoffe XLB, Technologie XLK)
und von Laendern (EWJ, EWG, ACWI gegenueber SPY), vgl. Ereignisstudien zu den Section-301-Zoellen 2018/19.
Ergaenzt fedregister_handelsschutz (ITA/ITC, nur Antidumping/Ausgleichszoll) um die Handelspolitik des
Weissen Hauses; andere Behoerde, keine Ueberschneidung der Dokumente.

Reihen:
- dokumente: alle USTR-Dokumente je Publikationstag
- section301: davon Volltexttreffer «Section 301»

Nullen nur bis zum letzten Tag, an dem das Federal Register ueberhaupt erschienen ist (bestaetigte Nulltage).
"""
import datetime
import gzip
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fr_inkrementell  # noqa: E402

ID = "fedregister_ustr_handelspolitik"
BASE = "https://www.federalregister.gov/api/v1/documents.json"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
START_YEAR = 1994
AGENCY = "trade-representative-office-of-united-states"
REIHEN = {"dokumente": None, "section301": '"section 301"'}


def fetch_json(url, retries=3):
    fr_inkrementell.pause()
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


def fetch_year_counts(year, term, counts):
    page = 1
    while True:
        params = [("conditions[agencies][]", AGENCY)]
        if term:
            params.append(("conditions[term]", term))
        params += [
            ("conditions[publication_date][year]", str(year)),
            ("per_page", "1000"),
            ("page", str(page)),
            ("fields[]", "publication_date"),
            ("order", "oldest"),
        ]
        data = fetch_json(BASE + "?" + urllib.parse.urlencode(params))
        results = data.get("results", []) or []
        for r in results:
            d = r.get("publication_date")
            if d:
                counts[d] = counts.get(d, 0) + 1
        total_pages = data.get("total_pages", 1) or 1
        if not results and page < total_pages:
            raise SystemExit("Abruffehler %s: leere Seite %d von %d; bisherige Datei bleibt" % (ID, page, total_pages))
        if page >= total_pages or not results:
            break
        page += 1


def letzter_fr_tag():
    params = [("per_page", "1"), ("fields[]", "publication_date"), ("order", "newest")]
    data = fetch_json(BASE + "?" + urllib.parse.urlencode(params))
    return datetime.date.fromisoformat(data["results"][0]["publication_date"])


def gzip_write(path, rows):
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
    os.makedirs(OUT_DIR, exist_ok=True)
    current_year = datetime.date.today().year
    last_day = letzter_fr_tag()
    ergebnisse = {}
    for reihe, term in REIHEN.items():
        alt, jahre = fr_inkrementell.plan(os.path.join(OUT_DIR, reihe + ".csv.gz"), START_YEAR, current_year)
        counts = dict(alt)
        for year in jahre:
            fetch_year_counts(year, term, counts)
        if not counts:
            raise RuntimeError("keine Dokumente fuer " + reihe)
        ende = max(last_day, max(datetime.date.fromisoformat(d) for d in counts))
        rows = []
        d = datetime.date(START_YEAR, 1, 1)
        while d <= ende:
            rows.append((d.isoformat(), counts.get(d.isoformat(), 0)))
            d += datetime.timedelta(days=1)
        ergebnisse[reihe] = rows
    for reihe, rows in ergebnisse.items():
        gzip_write(os.path.join(OUT_DIR, reihe + ".csv.gz"), rows)

    pub = ("taeglich (Federal Register erscheint an jedem US-Bundesarbeitstag; ein Dokument ist an seinem "
           "gedruckten Publikationsdatum oeffentlich, Beleg: federalregister.gov/reader-aids)")
    q = "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=" + AGENCY
    meta = {
        "dokumente": {
            "einheit": "Anzahl Dokumente",
            "beschreibung": "Taegliche Anzahl im Federal Register veroeffentlichter Dokumente des Office of the "
                            "United States Trade Representative (Bekanntmachungen, Regeln, Anhoerungen), 0 an Tagen "
                            "ohne USTR-Dokument; Nullen nur bis zum letzten erschienenen Federal-Register-Tag.",
            "quelle_url": q,
            "verdichtung": "Anzahl Dokumente je Kalendertag (Publikationsdatum)",
            "publikation": pub,
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
        "section301": {
            "einheit": "Anzahl Dokumente",
            "beschreibung": "Wie dokumente, eingeschraenkt auf Volltexttreffer \"section 301\" (Untersuchungen, "
                            "Zollmassnahmen, Ausnahmen nach Section 301 Trade Act 1974).",
            "quelle_url": q + "&conditions%5Bterm%5D=%22section+301%22",
            "verdichtung": "Anzahl Dokumente je Kalendertag (Publikationsdatum)",
            "publikation": pub,
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
