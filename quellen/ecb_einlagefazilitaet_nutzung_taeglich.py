#!/usr/bin/env python3
"""EZB Liquiditaetslage (Dataflow ILM, taeglich): Einlagefazilitaet und Girokonten der Banken."""
import gzip
import io
import json
import os
import urllib.request

ID = "ecb_einlagefazilitaet_nutzung_taeglich"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
BASE = "https://data-api.ecb.europa.eu/service/data/ILM/D.U2.C.%s.U2.EUR"

REIHEN = {
    "einlagefazilitaet": ("L020200", "Inanspruchnahme der Einlagefazilitaet des Eurosystems (Tagesendstand)"),
    "girokonten": ("L020100", "Guthaben der Kreditinstitute des Euroraums auf Girokonten beim Eurosystem (Tagesendstand, inkl. Mindestreserven)"),
}
PUB = ("taeglich (EZB veroeffentlicht die Liquiditaetslage des Eurosystems am folgenden TARGET-Geschaeftstag; "
       "Tageswerte aus Bilanzposten, keine statistische Revision)")


def fetch(key):
    url = (BASE % key) + "?format=csvdata&detail=dataonly"
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
        parts = line.split(",")
        if len(parts) <= max(ti, vi) or not parts[vi]:
            continue
        try:
            rows[parts[ti]] = float(parts[vi])
        except ValueError:
            continue
    return sorted(rows.items())


def gzip_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for d, v in rows:
            t.write("%s,%s\n" % (d, repr(round(v, 4))))
        t.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    meta = {}
    for reihe, (key, besch) in REIHEN.items():
        rows = parse(fetch(key))
        if len(rows) < 500:
            raise SystemExit("zu wenig Daten fuer %s" % key)
        gzip_write(os.path.join(OUT_DIR, reihe + ".csv.gz"), rows)
        meta[reihe] = {
            "einheit": "Mio. EUR",
            "beschreibung": "EZB ILM " + key + ": " + besch,
            "quelle_url": BASE % key,
            "verdichtung": "keine (bereits taeglich, nur TARGET-Geschaeftstage)",
            "publikation": PUB,
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
        }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
