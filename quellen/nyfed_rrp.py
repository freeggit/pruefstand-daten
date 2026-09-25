#!/usr/bin/env python3
import gzip
import io
import json
import os
import urllib.request

ID = "nyfed_rrp"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=RRPONTSYD"


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
    gzip_write(os.path.join(OUT_DIR, "rrp.csv.gz"), rows)

    meta = {
        "rrp": {
            "einheit": "Milliarden USD",
            "beschreibung": "NY Fed Overnight Reverse Repo Facility (ON RRP), taegliches Gesamtvolumen der akzeptierten Gebote (Treasury-Sicherheiten)",
            "quelle_url": URL,
            "verdichtung": "keine (bereits taeglich, Handelstage)",
            "publikation": 'taeglich (NY Fed veroeffentlicht RRP-Volumen am selben Tag nach Handelsschluss)',
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        }
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
