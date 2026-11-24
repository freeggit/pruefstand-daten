#!/usr/bin/env python3
"""Federal Register: taegliche Anzahl Proklamationen des US-Praesidenten zu Handel und Zoellen.

Mechanismus: Handelsproklamationen (Section 232/201-Zoelle auf Stahl, Aluminium, Solarmodule, Waschmaschinen;
Aenderungen am Zolltarif, GSP-Praeferenzen, Freihandelsabkommen) treffen einzelne Branchen (XLB, XLI, XLY) und
Exportlaender (EWJ, EWG) direkt und koennen sie kurzfristig gegenueber dem Weltindex bewegen.

Auswahl: Presidential Documents vom Typ «proclamation», deren Volltext «imports» oder «tariff» enthaelt
(Volltextsuche der Federal-Register-API, Vereinigung beider Abfragen nach Dokumentnummer), ohne Gedenk- und
Feiertagsproklamationen (Titel endet auf eine Jahreszahl, z.B. «Labor Day, 2026»). Datum = Publikations-
datum im Federal Register (nicht Unterzeichnungstag), damit nichts vorweggenommen wird.
"""
import datetime
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fr_inkrementell  # noqa: E402

ID = "fedregister_proklamationen_handel"
BASE = "https://www.federalregister.gov/api/v1/documents.json"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
START_YEAR = 1994
TERME = ["imports", "tariff"]
GEDENK = re.compile(r",\s*(19|20)\d\d\s*$")
CACHE = os.path.join(OUT_DIR, "_dokumente.json")   # {dokumentnummer: publikationsdatum}


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


def fetch_year(year, docs):
    for term in TERME:
        page = 1
        while True:
            params = [
                ("conditions[presidential_document_type][]", "proclamation"),
                ("conditions[type][]", "PRESDOCU"),
                ("conditions[publication_date][year]", str(year)),
                ("conditions[term]", term),
                ("per_page", "1000"),
                ("page", str(page)),
                ("fields[]", "publication_date"),
                ("fields[]", "document_number"),
                ("fields[]", "title"),
                ("order", "oldest"),
            ]
            data = fetch_json(BASE + "?" + urllib.parse.urlencode(params))
            results = data.get("results", [])
            for r in results:
                if GEDENK.search(r.get("title") or ""):
                    continue   # Gedenk- und Feiertagsproklamationen («Labor Day, 2026») erwaehnen Zoelle nur beilaeufig
                if r.get("publication_date") and r.get("document_number"):
                    docs[r["document_number"]] = r["publication_date"]
            total_pages = data.get("total_pages", 1) or 1
            if not results and page < total_pages:
                raise SystemExit("Abruffehler %s: leere Seite %d von %d; bisherige Datei bleibt" % (ID, page, total_pages))
            if page >= total_pages or not results:
                break
            page += 1


def letzter_fr_tag():
    params = [("per_page", "1"), ("order", "newest"), ("fields[]", "publication_date")]
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
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(buf.getvalue())
    os.replace(tmp, path)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    heute = datetime.date.today()
    docs = {}
    jahre = list(range(START_YEAR, heute.year + 1))
    if os.path.isfile(CACHE):
        try:
            with open(CACHE, encoding="utf-8") as f:
                alt = json.load(f)
            grenze = "%04d-01-01" % (heute.year - 1)
            docs = {k: v for k, v in alt.items() if v < grenze}
            if docs and min(docs.values()) < "%04d-12-31" % START_YEAR:
                jahre = [y for y in jahre if y >= heute.year - 1]
            else:
                docs = {}
        except (OSError, ValueError):
            docs = {}
    for y in jahre:
        fetch_year(y, docs)
    if len(docs) < 50:
        raise SystemExit("Abruffehler %s: nur %d Dokumente" % (ID, len(docs)))
    ende = min(letzter_fr_tag(), heute)
    counts = {}
    for d in docs.values():
        counts[d] = counts.get(d, 0) + 1
    rows = []
    d = datetime.date(START_YEAR, 1, 1)
    while d <= ende:
        rows.append((d.isoformat(), counts.get(d.isoformat(), 0)))
        d += datetime.timedelta(days=1)
    gzip_write(os.path.join(OUT_DIR, "anzahl.csv.gz"), rows)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(docs, f, sort_keys=True, indent=0)
    meta = {
        "anzahl": {
            "einheit": "Anzahl Proklamationen",
            "beschreibung": "Taegliche Anzahl im Federal Register veroeffentlichter Proklamationen des US-Praesidenten, deren Volltext 'imports' oder 'tariff' enthaelt (Zoelle, Importbeschraenkungen, Zolltarif, Handelspraeferenzen), ohne Gedenk- und Feiertagsproklamationen (Titel endet auf Jahreszahl); 0 an Tagen ohne solche Proklamation; Beginn 1994-01-01, Ende am letzten Federal-Register-Tag.",
            "quelle_url": "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bpresidential_document_type%5D%5B%5D=proclamation&conditions%5Bterm%5D=imports",
            "verdichtung": "Anzahl verschiedener Dokumente je Kalendertag (Publikationsdatum), Vereinigung der Volltextsuchen 'imports' und 'tariff'",
            "publikation": "taeglich (Federal Register erscheint an jedem US-Bundesarbeitstag; Proklamation gilt spaetestens am gedruckten Publikationsdatum als oeffentlich, meist einige Tage nach Unterzeichnung und Mitteilung des Weissen Hauses)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
