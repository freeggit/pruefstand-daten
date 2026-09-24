#!/usr/bin/env python3
import gzip
import io
import json
import os
import urllib.request

ID = "bitcoin_onchain"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
BASE = "https://api.blockchain.info/charts/%s?timespan=all&format=json&sampled=false"

CHARTS = {
    "hashrate": ("hash-rate", "TH/s", "Geschaetzte Bitcoin-Netzwerk-Hashrate (Terahashes pro Sekunde), aus Blockzeit und Difficulty berechnet"),
    "transaktionen": ("n-transactions", "Anzahl", "Bestaetigte Bitcoin-Transaktionen pro Tag"),
    "gebuehren": ("transaction-fees", "BTC", "Summe der Transaktionsgebuehren im Bitcoin-Netzwerk pro Tag, in BTC"),
}


def fetch(chart):
    url = BASE % chart
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse(payload):
    import datetime
    rows = {}
    for point in payload["values"]:
        d = datetime.datetime.utcfromtimestamp(point["x"]).strftime("%Y-%m-%d")
        v = point["y"]
        rows[d] = v
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
    for reihe, (chart, einheit, beschreibung) in CHARTS.items():
        rows = parse(fetch(chart))
        if not rows:
            raise SystemExit("keine Daten fuer %s" % chart)
        gzip_write(os.path.join(OUT_DIR, reihe + ".csv.gz"), rows)
        meta[reihe] = {
            "einheit": einheit,
            "beschreibung": beschreibung,
            "quelle_url": "https://api.blockchain.info/charts/%s" % chart,
            "verdichtung": "keine (bereits taeglich, UTC-Tagesgrenze der Quelle)",
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
        }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
