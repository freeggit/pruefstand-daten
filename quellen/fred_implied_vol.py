#!/usr/bin/env python3
import gzip
import io
import json
import os
import urllib.request

ID = "fred_implied_vol"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)

SERIES = {
    "oel": ("OVXCLS", "CBOE Crude Oil ETF Volatility Index (OVX), implizite Volatilitaet aus USO-Optionen"),
    "gold": ("GVZCLS", "CBOE Gold ETF Volatility Index (GVZ), implizite Volatilitaet aus GLD-Optionen"),
    "em": ("VXEEMCLS", "CBOE Emerging Markets ETF Volatility Index (VXEEM), implizite Volatilitaet aus EEM-Optionen"),
}


def fetch(fred_id):
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=%s" % fred_id
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse(text):
    rows = []
    for line in text.splitlines()[1:]:
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
    for reihe, (fred_id, beschreibung) in SERIES.items():
        rows = parse(fetch(fred_id))
        if not rows:
            raise SystemExit("keine Daten fuer %s" % fred_id)
        gzip_write(os.path.join(OUT_DIR, reihe + ".csv.gz"), rows)
        meta[reihe] = {
            "einheit": "Index (annualisierte implizite Volatilitaet in %)",
            "beschreibung": beschreibung,
            "quelle_url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=%s" % fred_id,
            "verdichtung": "keine (bereits taeglich, Handelstage)",
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
        }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
