#!/usr/bin/env python3
import csv
import datetime
import gzip
import io
import json
import os
import urllib.request

ID = "cboe_vix9d"
URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX9D_History.csv"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def gzip_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        text = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        w = csv.writer(text)
        w.writerow(["datum", "wert"])
        for d, v in rows:
            w.writerow([d, v])
        text.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    text = fetch()
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    rows = []
    seen = set()
    for r in reader:
        if len(r) < 5 or not r[0].strip():
            continue
        try:
            dt = datetime.datetime.strptime(r[0].strip(), "%m/%d/%Y").date()
            val = float(r[4].strip())
        except ValueError:
            continue
        iso = dt.isoformat()
        if iso in seen:
            continue
        seen.add(iso)
        rows.append((iso, val))
    rows.sort(key=lambda x: x[0])

    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "vix9d.csv.gz"), rows)

    meta = {
        "vix9d": {
            "einheit": "Indexpunkte",
            "beschreibung": "Cboe VIX9D Index (implizite 9-Tage-Volatilitaet des S&P 500), taeglicher Schlusswert",
            "quelle_url": URL,
            "verdichtung": "keine (bereits taeglich); Schlusswert (CLOSE-Spalte) aus taeglicher OHLC-Datei",
            "publikation": 'taeglich (Cboe veroeffentlicht Indexschlusswerte am selben Handelstagabend)',
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
