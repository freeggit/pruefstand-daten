#!/usr/bin/env python3
import csv
import gzip
import io
import json
import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "neu", "boj_call_rate")
URL = (
    "https://www.stat-search.boj.or.jp/api/v1/getDataCode"
    "?format=csv&lang=en&db=FM01&code=STRDCLUCON"
)
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse(text):
    rows = []
    reader = csv.reader(io.StringIO(text))
    in_data = False
    for row in reader:
        if not row:
            continue
        if row[0] == "SERIES_CODE":
            in_data = True
            continue
        if not in_data:
            continue
        if row[0] != "STRDCLUCON":
            continue
        survey_date = row[6]
        value = row[7]
        if value == "null" or value == "":
            continue
        d = "%s-%s-%s" % (survey_date[0:4], survey_date[4:6], survey_date[6:8])
        rows.append((d, float(value)))
    rows.sort(key=lambda r: r[0])
    seen = set()
    out = []
    for d, v in rows:
        if d in seen:
            continue
        seen.add(d)
        out.append((d, v))
    return out


def write_csv_gz(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.StringIO()
    buf.write("datum,wert\n")
    for d, v in rows:
        buf.write("%s,%s\n" % (d, v))
    data = buf.getvalue().encode("utf-8")
    with open(path, "wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as gz:
            gz.write(data)


def main():
    text = fetch()
    rows = parse(text)
    if len(rows) < 500:
        raise RuntimeError("zu wenige Werte: %d" % len(rows))
    write_csv_gz(os.path.join(OUT_DIR, "call_rate.csv.gz"), rows)
    meta = {
        "call_rate": {
            "einheit": "Prozent p.a.",
            "beschreibung": "Bank of Japan, Uncollateralized Overnight Call Rate (Mutan-Satz), Tagesdurchschnitt, ueber die BOJ Time-Series Data Search API (DB FM01, Series STRDCLUCON).",
            "quelle_url": URL,
            "verdichtung": "keine (bereits Tageswert lt. Quelle)",
            "publikation": 'taeglich (Bank of Japan veroeffentlicht Tagesgeldsatz am naechsten Geschaeftstag)',
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("boj_call_rate: %d Zeilen, %s bis %s" % (len(rows), rows[0][0], rows[-1][0]))


if __name__ == "__main__":
    main()
