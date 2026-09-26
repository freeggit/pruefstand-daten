#!/usr/bin/env python3
import gzip
import io
import json
import os
import urllib.parse
import urllib.request
from datetime import date, timedelta

ID = "boe_bankrate_aenderungstage"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)

# Bank of England Interactive Statistical Database (IADB), Bank Rate series IUDBEDR.
# Oeffentlicher CSV-Export ohne Login/Schluessel, dokumentiert unter
# https://www.bankofengland.co.uk/boeapps/database/Bank-Rate.asp
URL = (
    "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
    "?csv.x=yes&SeriesCodes=IUDBEDR&UsingCodes=Y&CSVF=TN"
    "&Datefrom=01/Jan/1975&Dateto={dateto}"
)

MONATE = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8-sig")


def parse_boe_date(s):
    # Format "02 Jan 1975"
    tag, mon, jahr = s.strip().split()
    return "%04d-%02d-%02d" % (int(jahr), MONATE[mon], int(tag))


def parse(text):
    rows = []
    lines = text.splitlines()
    if not lines:
        return rows
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        d, _, v = line.partition(",")
        v = v.strip()
        if not v:
            continue
        try:
            fv = float(v)
        except ValueError:
            continue
        rows.append((parse_boe_date(d), fv))
    rows.sort()
    # keine Doppel: bei mehrfachem selben Datum letzten Wert behalten
    dedup = {}
    for d, v in rows:
        dedup[d] = v
    return sorted(dedup.items())


def change_days(rows):
    out = []
    prev = None
    for d, v in rows:
        flag = 1 if (prev is not None and v != prev) else 0
        out.append((d, flag))
        prev = v
    return out


def gzip_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for d, v in rows:
            t.write("%s,%d\n" % (d, v))
        t.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    heute = date.today()
    dateto = heute.strftime("%d/%b/%Y")
    rows = parse(fetch(URL.format(dateto=dateto)))
    if not rows or len(rows) < 500:
        raise SystemExit("keine/zu wenige Daten")
    flags = change_days(rows)

    gzip_write(os.path.join(OUT_DIR, "aenderungstage.csv.gz"), flags)

    meta = {
        "aenderungstage": {
            "einheit": "Indikator (0/1)",
            "beschreibung": (
                "1 an dem Handelstag, an dem sich die von der Bank of England "
                "gesetzte Bank Rate (Serie IUDBEDR) gegenueber dem vorherigen "
                "veroeffentlichten Wert aendert, sonst 0. Reihe enthaelt nur "
                "Handelstage (keine Wochenenden/Feiertage), wie von der Quelle "
                "geliefert."
            ),
            "quelle_url": "https://www.bankofengland.co.uk/boeapps/database/Bank-Rate.asp",
            "verdichtung": "keine (bereits taeglich/handelstaeglich, Aenderungsindikator aus taeglicher Zinsreihe abgeleitet)",
            "publikation": "taeglich (Entscheiddatum am Tag der Bekanntgabe oeffentlich in der IADB, Reihe wird fortgeschrieben)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
