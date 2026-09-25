#!/usr/bin/env python3
import datetime
import gzip
import io
import json
import os
import urllib.request

ID = "snb_saron"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
CUBE_URL = "https://data.snb.ch/api/cube/zirepo/data/csv/en"


def fetch():
    today = datetime.date.today().isoformat()
    url = CUBE_URL + "?dimSel=D0(H0)&fromDate=1999-01-01&toDate=" + today
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8-sig")
    return text


def parse(text):
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith('"'):
            continue
        parts = [p.strip('"') for p in line.split(";")]
        if len(parts) < 3:
            continue
        d, dim, val = parts[0], parts[1], parts[2]
        if dim != "H0":
            continue
        if len(d) != 10 or d[4] != "-":
            continue
        if not val:
            continue
        try:
            v = float(val)
        except ValueError:
            continue
        rows.append((d, v))
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
    gzip_write(os.path.join(OUT_DIR, "saron.csv.gz"), rows)

    meta = {
        "saron": {
            "einheit": "Prozent",
            "beschreibung": "SARON Uebernacht-Referenzzinssatz (Schlusskurs), SNB Datenportal Cube zirepo, Dimension H0",
            "quelle_url": "https://data.snb.ch/en/topics/ziredev/cube/zirepo",
            "verdichtung": "keine (bereits taeglich)",
            "publikation": 'woechentlich (SNB-Datenportal SARON-Cube aktualisiert wochentlich nachlaufend statt taeglich, siehe Katalog-Grund; verfuegbar_nach_tagen 8 bestaetigt)',
            "verfuegbar_nach_tagen": 8,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
