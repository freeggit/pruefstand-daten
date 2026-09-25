#!/usr/bin/env python3
import gzip
import io
import json
import os
import urllib.request

ID = "ecb_fx"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
BASE = "https://data-api.ecb.europa.eu/service/data/EXR/D.%s.EUR.SP00.A?format=csvdata&startPeriod=1999-01-01"

PAIRS = {
    "eurchf": "CHF",
    "eurjpy": "JPY",
    "eurcny": "CNY",
}


def fetch(currency):
    url = BASE % currency
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse(text):
    lines = text.splitlines()
    header = lines[0].split(",")
    ti = header.index("TIME_PERIOD")
    vi = header.index("OBS_VALUE")
    rows = {}
    for line in lines[1:]:
        if not line:
            continue
        parts = line.split(",")
        d, v = parts[ti], parts[vi]
        if not v:
            continue
        try:
            fv = float(v)
        except ValueError:
            continue
        rows[d] = fv
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
    for reihe, currency in PAIRS.items():
        rows = parse(fetch(currency))
        if not rows:
            raise SystemExit("keine Daten fuer %s" % currency)
        gzip_write(os.path.join(OUT_DIR, reihe + ".csv.gz"), rows)
        meta[reihe] = {
            "einheit": "%s je EUR" % currency,
            "beschreibung": "EZB Referenzkurs %s/EUR, 14:15 MEZ" % currency,
            "quelle_url": "https://data-api.ecb.europa.eu/service/data/EXR/D.%s.EUR.SP00.A" % currency,
            "verdichtung": "keine (bereits taeglich)",
            "publikation": 'taeglich (EZB veroeffentlicht Referenzkurse an jedem TARGET-Handelstag gegen 16:00 CET am selben Tag)',
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
