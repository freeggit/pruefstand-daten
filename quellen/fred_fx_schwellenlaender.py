#!/usr/bin/env python3
import gzip
import io
import json
import os
import urllib.request

ID = "fred_fx_schwellenlaender"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)

SERIES = {
    "usdkrw": ("DEXKOUS", "KRW je USD", "USD/KRW-Wechselkurs Suedkorea (Federal Reserve H.10, Noon Buying Rate in New York), taeglich an US-Bankarbeitstagen (Serie DEXKOUS, ab 1981)."),
    "usdinr": ("DEXINUS", "INR je USD", "USD/INR-Wechselkurs Indien (Federal Reserve H.10, Noon Buying Rate in New York), taeglich an US-Bankarbeitstagen (Serie DEXINUS, ab 1973)."),
    "usdzar": ("DEXSFUS", "ZAR je USD", "USD/ZAR-Wechselkurs Suedafrika (Federal Reserve H.10, Noon Buying Rate in New York), taeglich an US-Bankarbeitstagen (Serie DEXSFUS, ab 1971)."),
}


def fetch(sid):
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=%s" % sid
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8"), url


def parse(text):
    lines = text.splitlines()
    rows = []
    for line in lines[1:]:
        if not line:
            continue
        d, _, v = line.partition(",")
        v = v.strip()
        if not v or v == ".":
            continue
        try:
            fv = float(v)
        except ValueError:
            continue
        rows.append((d, fv))
    rows.sort()
    return rows


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
    for reihe, (sid, einheit, beschreibung) in SERIES.items():
        text, url = fetch(sid)
        rows = parse(text)
        if not rows:
            raise SystemExit("keine Daten fuer %s" % sid)
        gzip_write(os.path.join(OUT_DIR, reihe + ".csv.gz"), rows)
        meta[reihe] = {
            "einheit": einheit,
            "beschreibung": beschreibung,
            "quelle_url": url,
            "verdichtung": "keine (bereits taeglich)",
            "publikation": 'woechentlich (Fed H.10 Devisenkurse DEXKOUS/DEXINUS/DEXSFUS: H.10 erscheint seit 2009 woechentlich montags mit den Tageskursen der Vorwoche, Beleg federalreserve.gov/releases/h10, wie fred_fx_lang; geprueft 27.11.2026)',
            "verfuegbar_nach_tagen": 8,
            "revidiert": False,
        }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
