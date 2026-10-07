#!/usr/bin/env python3
import datetime
import gzip
import io
import json
import os
import urllib.request

ID = "noaa_cpc_heizgradtage_taeglich"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
BASE = "https://ftp.cpc.ncep.noaa.gov/htdocs/degree_days/weighted/daily_data/%d/Population.%s.txt"
PRODUKTE = {"hdd_conus": "Heating", "cdd_conus": "Cooling"}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse(text):
    lines = text.splitlines()
    kopf = [x.strip() for x in lines[3].split("|")] if lines[3].startswith("Region") else None
    if kopf is None:
        kopf = [x.strip() for x in next(l for l in lines if l.startswith("Region")).split("|")]
    for line in lines:
        if line.startswith("CONUS|"):
            werte = line.strip().split("|")[1:]
            break
    else:
        return []
    rows = []
    for d, v in zip(kopf[1:], werte):
        if len(d) != 8 or v.strip() == "":
            continue
        try:
            x = float(v)
        except ValueError:
            continue
        rows.append(("%s-%s-%s" % (d[:4], d[4:6], d[6:8]), x))
    return rows


def gzip_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for d, v in rows:
            t.write("%s,%s\n" % (d, ("%g" % v)))
        t.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    heute = datetime.datetime.utcnow().date()
    ergebnis = {}
    for name, prod in PRODUKTE.items():
        d = {}
        for jahr in range(1981, heute.year + 1):
            for d_, v in parse(fetch(BASE % (jahr, prod))):
                if d_ <= heute.isoformat():
                    d[d_] = v
        ergebnis[name] = sorted(d.items())
        if not ergebnis[name]:
            raise SystemExit("keine Daten fuer " + name)
    for name, rows in ergebnis.items():
        gzip_write(os.path.join(OUT_DIR, name + ".csv.gz"), rows)
    gemeinsam = {
        "einheit": "Gradtage (Grad Fahrenheit-Tage, bevoelkerungsgewichtet)",
        "quelle_url": "https://ftp.cpc.ncep.noaa.gov/htdocs/degree_days/weighted/daily_data/",
        "verdichtung": "keine (Tageswerte, bereits taeglich)",
        "verfuegbar_nach_tagen": 1,
        "publikation": "taeglich (NOAA CPC veroeffentlicht die Tageswerte am Folgetag; Stichprobe: letzter Wert 2 Tage alt)",
        "revidiert": False,
    }
    meta = {
        "hdd_conus": dict(gemeinsam, beschreibung="Heizgradtage CONUS, bevoelkerungsgewichtet (NOAA CPC, Census-Divisionen, Zeile CONUS), Schwelle 65F"),
        "cdd_conus": dict(gemeinsam, beschreibung="Kuehlgradtage CONUS, bevoelkerungsgewichtet (NOAA CPC, Census-Divisionen, Zeile CONUS), Schwelle 65F"),
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
