#!/usr/bin/env python3
import gzip
import io
import json
import os
import urllib.request

ID = "fred_brent"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU"


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


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
    rows = parse(fetch())
    if not rows:
        raise SystemExit("keine Daten")
    gzip_write(os.path.join(OUT_DIR, "brent.csv.gz"), rows)

    meta = {
        "brent": {
            "einheit": "USD je Barrel",
            "beschreibung": "Brent Crude Oil - Europe (DCOILBRENTEU), taeglicher Spotpreis; internationaler Rohoel-Referenzpreis unabhaengig vom bereits vorhandenen WTI (USO/DCOILWTICO)",
            "quelle_url": URL,
            "verdichtung": "keine (bereits taeglich, Handelstage)",
            "publikation": 'woechentlich (EIA-Spotpreis Brent, FRED-Release zeigt 7-Tage-Luecke zwischen Aktualisierungen trotz taeglicher Beobachtungsfrequenz, geprueft 25.9.2026 an DCOILBRENTEU)',
            "verfuegbar_nach_tagen": 8,
            "revidiert": False,
        }
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
