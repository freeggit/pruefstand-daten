#!/usr/bin/env python3
import datetime
import gzip
import io
import json
import os
import urllib.parse
import urllib.request

ID = "boe_sonia"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
BASE_URL = "https://www.bankofengland.co.uk/boeapps/iadb/fromshowcolumns.asp"


def fetch():
    params = {
        "csv.x": "yes",
        "Datefrom": "01/Jan/1990",
        "Dateto": "now",
        "SeriesCodes": "IUDSOIA",
        "CSVF": "TN",
        "UsingCodes": "Y",
        "VPD": "Y",
    }
    url = BASE_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def parse(text):
    lines = text.strip().splitlines()
    rows = []
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        d_raw, _, v_raw = line.partition(",")
        d_raw = d_raw.strip()
        v_raw = v_raw.strip()
        if not d_raw or not v_raw:
            continue
        day, mon, year = d_raw.split(" ")
        iso = "%04d-%02d-%02d" % (int(year), MONTHS[mon], int(day))
        try:
            v = float(v_raw)
        except ValueError:
            continue
        rows.append((iso, v))
    rows.sort()
    dedup = {}
    for d, v in rows:
        dedup[d] = v
    return sorted(dedup.items())


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
        raise SystemExit("keine Daten erhalten")

    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "sonia.csv.gz"), rows)

    meta = {
        "sonia": {
            "einheit": "Prozent",
            "beschreibung": "SONIA (Sterling Overnight Index Average), von der Bank of England administrierter GBP-Tagesgeldsatz, IADB-Serie IUDSOIA",
            "quelle_url": "https://www.bankofengland.co.uk/boeapps/database/Bank-Rate.asp",
            "verdichtung": "keine (bereits taeglich, nur Bankarbeitstage)",
            "publikation": 'taeglich (Bank of England IADB veroeffentlicht SONIA am naechsten Bankarbeitstag)',
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
