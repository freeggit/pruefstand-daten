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
PROJECT = "de.wikipedia"
START = "2015070100"
BASE = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "%s/all-access/all-agents/%%s/daily/%s/%%s00"
) % (PROJECT, START)

ARTICLES = {
    "zinssenkung": "Zinssenkung",
    "konkurs": "Konkurs",
    "duerre": "Dürre",
    "hurrikan": "Hurrikan",
    "streik": "Streik",
    "pandemie": "Pandemie",
}


def enddate():
    return time.strftime("%Y%m%d", time.gmtime(time.time() - 2 * 86400))


def fetch(article):
    url = BASE % (urllib.parse.quote(article, safe=""), enddate())
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    attempts = 0
    while True:
        attempts += 1
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempts < 3:
                wait = int(e.headers.get("Retry-After", "10"))
                time.sleep(min(wait, 60))
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
    meta = {}
    fetched_any = False
    for reihe, article in ARTICLES.items():
        data = fetch(article)
        rows = parse(data.get("items", []))
        if not rows:
            continue
        gzip_write(os.path.join(OUT_DIR, reihe + ".csv.gz"), rows)
        meta[reihe] = {
            "einheit": "Aufrufe pro Tag",
            "beschreibung": "Wikipedia-Seitenaufrufe de.wikipedia.org Artikel '%s', alle Zugriffsarten" % article,
            "quelle_url": BASE % (urllib.parse.quote(article, safe=""), "..."),
            "verdichtung": "keine (bereits taeglich)",
            "verfuegbar_nach_tagen": 2,
            "revidiert": False,
        }
        fetched_any = True
        time.sleep(2)

    if not fetched_any:
        raise SystemExit("keine Daten (alle Artikel fehlgeschlagen)")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
