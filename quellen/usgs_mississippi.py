#!/usr/bin/env python3
import gzip
import io
import json
import os
import urllib.parse
import urllib.request

ID = "usgs_mississippi"
SITE = "07010000"
PARAM = "00060"
BASE = "https://waterservices.usgs.gov/nwis/dv/"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)


def fetch():
    import datetime
    end = datetime.date.today().isoformat()
    params = {
        "sites": SITE,
        "parameterCd": PARAM,
        "format": "json",
        "startDT": "1900-01-01",
        "endDT": end,
    }
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
    data = fetch()
    series = data["value"]["timeSeries"]
    if not series:
        raise RuntimeError("keine Zeitreihe in Antwort")
    values = series[0]["values"][0]["value"]
    unit = series[0]["variable"]["unit"]["unitCode"]
    rows = []
    seen = set()
    for v in values:
        date_str = v["dateTime"][:10]
        if date_str in seen:
            continue
        try:
            val = float(v["value"])
        except (TypeError, ValueError):
            continue
        seen.add(date_str)
        rows.append((date_str, val))
    rows.sort(key=lambda x: x[0])

    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "abfluss.csv.gz"), rows)

    meta = {
        "abfluss": {
            "einheit": unit,
            "beschreibung": "Taeglicher mittlerer Abfluss des Mississippi bei St. Louis, MO (USGS-Station 07010000)",
            "quelle_url": "https://waterservices.usgs.gov/nwis/dv/?sites=%s&parameterCd=%s&format=json" % (SITE, PARAM),
            "verdichtung": "keine (USGS liefert bereits taegliche Mittelwerte)",
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
