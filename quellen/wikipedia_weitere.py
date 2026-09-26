#!/usr/bin/env python3
import gzip
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

ID = "wikipedia_weitere"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
START = "2015070100"
BASE_TMPL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "%s/all-access/all-agents/%%s/daily/%s/%%s00"
)

# reihe -> (Wikipedia-Projekt, Artikeltitel). DE-Artikel seit dem ersten Lauf,
# EN-Artikel ergaenzt (Zusatz 2, Punkt 6): englischsprachige Aufmerksamkeit
# misst etwas anderes als deutschsprachige (globale/US- vs. CH/DE-Leserschaft).
ARTICLES = {
    "zinssatz": ("de.wikipedia", "Zinssatz"),
    "konkurs": ("de.wikipedia", "Konkurs"),
    "duerre": ("de.wikipedia", "Dürre"),
    "hurrikan": ("de.wikipedia", "Hurrikan"),
    "streik": ("de.wikipedia", "Streik"),
    "pandemie": ("de.wikipedia", "Pandemie"),
    "oelpreis": ("de.wikipedia", "Ölpreis"),
    "halbleiter": ("de.wikipedia", "Halbleiter"),
    "rezession": ("de.wikipedia", "Rezession"),
    "zinssatz_en": ("en.wikipedia", "Interest rate"),
    "rezession_en": ("en.wikipedia", "Recession"),
    "oelpreis_en": ("en.wikipedia", "Price of oil"),
    "halbleiter_en": ("en.wikipedia", "Semiconductor"),
    "pandemie_en": ("en.wikipedia", "Pandemic"),
}


def enddate():
    return time.strftime("%Y%m%d", time.gmtime(time.time() - 2 * 86400))


# run_all.py toetet das Skript nach 180s (main, nicht aenderbar). 14 Artikel
# muessen darin Platz haben, auch wenn Wikimedia einzelne Abrufe drosselt;
# darum ein hartes Zeitbudget statt langer Retry-Wartezeiten.
DEADLINE_S = 150
_START = time.time()


def restzeit():
    return DEADLINE_S - (time.time() - _START)


def fetch(project, article):
    base = BASE_TMPL % (project, START)
    url = base % (urllib.parse.quote(article, safe=""), enddate())
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    attempts = 0
    while True:
        attempts += 1
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempts < 2 and restzeit() > 20:
                wait = int(e.headers.get("Retry-After", "8"))
                time.sleep(max(0, min(wait, 8, restzeit() - 10)))
                continue
            raise


def parse(items):
    rows = {}
    for it in items:
        ts = it["timestamp"]
        d = "%s-%s-%s" % (ts[0:4], ts[4:6], ts[6:8])
        rows[d] = rows.get(d, 0) + int(it["views"])
    return sorted(rows.items())


def gzip_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for d, v in rows:
            t.write("%s,%s\n" % (d, v))
        t.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    meta_path = os.path.join(OUT_DIR, "meta.json")
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    fetched_any = False
    failed = []
    for reihe, (project, article) in ARTICLES.items():
        if restzeit() < 15:
            failed.append((reihe, "zeitbudget"))
            continue
        try:
            data = fetch(project, article)
        except urllib.error.HTTPError as e:
            failed.append((reihe, e.code))
            continue
        rows = parse(data.get("items", []))
        if not rows:
            failed.append((reihe, "leer"))
            time.sleep(2)
            continue
        gzip_write(os.path.join(OUT_DIR, reihe + ".csv.gz"), rows)
        base = BASE_TMPL % (project, START)
        meta[reihe] = {
            "einheit": "Aufrufe pro Tag",
            "beschreibung": "Wikipedia-Seitenaufrufe %s.org Artikel '%s', alle Zugriffsarten" % (project, article),
            "quelle_url": base % (urllib.parse.quote(article, safe=""), "..."),
            "verdichtung": "keine (bereits taeglich)",
            "publikation": 'taeglich (Wikimedia Pageviews API veroeffentlicht Tageszaehlungen mit rund 1-2 Tagen Verzug, kein Wochenbatch)',
            "verfuegbar_nach_tagen": 2,
            "revidiert": False,
        }
        fetched_any = True
        time.sleep(2)

    if not fetched_any and not meta:
        raise SystemExit("keine Daten (alle Artikel fehlgeschlagen): %r" % failed)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)

    if failed:
        print("Teilweise fehlgeschlagen (alte Dateien fuer diese Artikel bleiben stehen, falls vorhanden):", failed)


if __name__ == "__main__":
    main()
