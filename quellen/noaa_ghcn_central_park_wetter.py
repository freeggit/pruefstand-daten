#!/usr/bin/env python3
"""NOAA GHCN-Daily, Station New York Central Park (USW00094728): Niederschlag und Tageshoechsttemperatur.
Werte mit gesetztem Qualitaetsflag (QC nicht bestanden) werden weggelassen, nichts aufgefuellt."""
import csv
import datetime
import gzip
import io
import json
import os
import urllib.parse
import urllib.request

ID = "noaa_ghcn_central_park_wetter"
STATION = "USW00094728"
BASE = "https://www.ncei.noaa.gov/access/services/data/v1"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
PUB = ("taeglich, mit Verzoegerung: GHCN-Daily wird von NCEI taeglich nachgefuehrt, die Station Central Park "
       "erscheint erfahrungsgemaess 1-3 Tage nach dem Messtag (Beobachtung beim Abruf 2026-11-13: letzter Wert 2026-11-10); "
       "Beleg: NCEI GHCN-Daily Dokumentation (Update taeglich)")

REIHEN = {
    "niederschlag_mm": ("PRCP", "mm", "Tagesniederschlag in New York Central Park (GHCN-Daily PRCP, Zehntel-mm / 10)"),
    "tmax_c": ("TMAX", "Grad Celsius", "Tageshoechsttemperatur in New York Central Park (GHCN-Daily TMAX, Zehntel-Grad / 10)"),
}


def fetch():
    end = datetime.date.today().isoformat()
    params = {
        "dataset": "daily-summaries",
        "stations": STATION,
        "dataTypes": ",".join(v[0] for v in REIHEN.values()),
        "startDate": "1869-01-01",
        "endDate": end,
        "includeAttributes": "true",
        "format": "csv",
    }
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def gzip_write(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("datum,wert\n" + "".join("%s,%s\n" % r for r in rows)).encode("utf-8"))
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def fmt(x):
    s = ("%.1f" % x)
    return "0.0" if s == "-0.0" else s


def main():
    text = fetch()
    rd = list(csv.DictReader(io.StringIO(text)))
    if len(rd) < 1000:
        raise RuntimeError("zu wenige Zeilen: %d" % len(rd))
    os.makedirs(OUT_DIR, exist_ok=True)
    meta = {}
    for name, (code, einheit, beschr) in REIHEN.items():
        rows = {}
        for r in rd:
            v = (r.get(code) or "").strip()
            if not v:
                continue
            attr = (r.get(code + "_ATTRIBUTES") or "").split(",")
            qflag = attr[1].strip() if len(attr) > 1 else ""
            if qflag:
                continue
            d = r["DATE"][:10]
            rows[d] = fmt(int(v) / 10.0)
        out = sorted(rows.items())
        gzip_write(os.path.join(OUT_DIR, name + ".csv.gz"), out)
        meta[name] = {
            "einheit": einheit,
            "beschreibung": beschr + "; Werte mit Qualitaetsflag weggelassen",
            "quelle_url": BASE + "?dataset=daily-summaries&stations=%s&dataTypes=%s&format=csv" % (STATION, code),
            "verdichtung": "keine (Tageswert der Station, lokaler Beobachtungstag)",
            "verfuegbar_nach_tagen": 3,
            "revidiert": False,
            "publikation": PUB,
            "status": "aktiv",
        }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
