#!/usr/bin/env python3
"""Kalifornien, Attorney General: gemeldete Datenlecks (Cal. Civ. Code 1798.82) je Meldetag."""
import csv
import datetime
import gzip
import io
import json
import os
import urllib.request

ID = "ca_ag_datenlecks"
URL = "https://oag.ca.gov/privacy/databreach/list-export"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)


def gzip_write(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("datum,wert\n" + "".join("%s,%s\n" % r for r in rows)).encode("utf-8"))
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    head = [h.strip().lower() for h in rows[0]]
    col = [i for i, h in enumerate(head) if h.startswith("reported date")]
    if not col:
        raise RuntimeError("Spalte 'Reported Date' fehlt: %r" % rows[0])
    col = col[0]
    counts = {}
    for r in rows[1:]:
        if len(r) <= col:
            continue
        try:
            d = datetime.datetime.strptime(r[col].strip(), "%m/%d/%Y").date()
        except ValueError:
            continue
        counts[d] = counts.get(d, 0) + 1
    if len(counts) < 500:
        raise RuntimeError("zu wenige Meldetage: %d" % len(counts))
    today = datetime.datetime.now(datetime.timezone.utc).date()
    last = min(max(max(counts), today - datetime.timedelta(days=1)), today)
    out, cur = [], min(counts)
    while cur <= last:
        out.append((cur.isoformat(), counts.get(cur, 0)))
        cur += datetime.timedelta(days=1)
    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "meldungen.csv.gz"), out)
    meta = {
        "meldungen": {
            "einheit": "Anzahl Meldungen",
            "beschreibung": (
                "Anzahl der beim Attorney General von Kalifornien eingereichten und veroeffentlichten "
                "Datenleck-Meldungen (Pflicht ab 500 betroffenen Kaliforniern, Cal. Civ. Code 1798.29/1798.82) "
                "je Kalendertag. Datum = 'Reported Date' der Liste (Tag der Meldung an den AG und Aufnahme in "
                "die oeffentliche Liste), nicht der Tag des Lecks; 0 an Tagen ohne Meldung. Betroffen sind "
                "Firmen aller Sektoren, besonders Gesundheit und Finanz -- Mechanismus Cyberrisiko (XLV, XLF, XLK)."
            ),
            "quelle_url": "https://oag.ca.gov/privacy/databreach/list",
            "verdichtung": "Anzahl Meldungen je Kalendertag (Reported Date)",
            "publikation": (
                "taeglich: Die Liste oag.ca.gov/privacy/databreach/list wird laufend ergaenzt; im Abruf "
                "2026-11-14T00Z waren bereits Meldungen mit Reported Date 2026-11-13 enthalten. Vereinzelt "
                "nachtraeglich eingestellte Meldungen mit frueherem Datum moeglich, darum Puffer 2 Tage."
            ),
            "verfuegbar_nach_tagen": 2,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
