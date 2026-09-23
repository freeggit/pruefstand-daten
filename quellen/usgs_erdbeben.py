#!/usr/bin/env python3
import datetime
import gzip
import io
import json
import os
import urllib.parse
import urllib.request

ID = "usgs_erdbeben"
BASE = "https://earthquake.usgs.gov/fdsnws/event/1/query"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
START_YEAR = 2015


def fetch_year(year):
    start = "%d-01-01" % year
    today = datetime.date.today()
    if year == today.year:
        end = today.isoformat()
    else:
        end = "%d-01-01" % (year + 1)
    params = {
        "starttime": start,
        "endtime": end,
        "minmagnitude": "5",
        "format": "text",
        "orderby": "time-asc",
    }
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def gzip_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        text = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        text.write("datum,wert\n")
        for d, v in rows:
            text.write("%s,%s\n" % (d, v))
        text.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    counts = {}
    current_year = datetime.date.today().year
    for year in range(START_YEAR, current_year + 1):
        text = fetch_year(year)
        for line in text.splitlines():
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) < 2:
                continue
            time_field = parts[1]
            day = time_field[:10]
            try:
                datetime.date.fromisoformat(day)
            except ValueError:
                continue
            counts[day] = counts.get(day, 0) + 1

    first_day = datetime.date(START_YEAR, 1, 1)
    last_day = max(datetime.date.fromisoformat(d) for d in counts)
    rows = []
    d = first_day
    while d <= last_day:
        iso = d.isoformat()
        rows.append((iso, counts.get(iso, 0)))
        d += datetime.timedelta(days=1)

    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "anzahl_m5.csv.gz"), rows)

    meta = {
        "anzahl_m5": {
            "einheit": "Anzahl Ereignisse",
            "beschreibung": "Weltweite Anzahl Erdbeben ab Magnitude 5.0 pro UTC-Kalendertag (USGS Erdbebenkatalog)",
            "quelle_url": BASE,
            "verdichtung": "Summe der Ereignisse je UTC-Tag",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
