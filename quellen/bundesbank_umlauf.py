#!/usr/bin/env python3
import gzip
import io
import json
import os
import urllib.request

ID = "bundesbank_umlauf"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
BASE_URL = "https://api.statistiken.bundesbank.de/rest/data/BBSSY/"

REIHEN = {
    "bund2y": {
        "key": "D.REN.EUR.A610.000000WT0202.A",
        "beschreibung": "Rendite der aktuellen zweijaehrigen Bundesschatzanweisung (Daily yield of current two-year Federal Treasury notes)",
    },
    "bund10y": {
        "key": "D.REN.EUR.A630.000000WT1010.A",
        "beschreibung": "Rendite der aktuellen zehnjaehrigen Bundesanleihe (Daily yield of current 10-year federal bond)",
    },
}


def fetch(key):
    url = BASE_URL + key + "?format=csv&lang=en"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8-sig")


def parse(text):
    rows = []
    for line in text.strip().splitlines():
        parts = line.split(",")
        d = parts[0].strip('"')
        if len(d) != 10 or d[4] != "-" or d[7] != "-":
            continue
        v_raw = parts[1].strip() if len(parts) > 1 else ""
        if not v_raw or v_raw == ".":
            continue
        try:
            v = float(v_raw)
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
    os.makedirs(OUT_DIR, exist_ok=True)
    meta = {}
    for reihe, info in REIHEN.items():
        rows = parse(fetch(info["key"]))
        if not rows:
            raise SystemExit("keine Daten erhalten: %s" % reihe)
        gzip_write(os.path.join(OUT_DIR, reihe + ".csv.gz"), rows)
        meta[reihe] = {
            "einheit": "Prozent",
            "beschreibung": info["beschreibung"],
            "quelle_url": "https://www.bundesbank.de/en/statistics/money-and-capital-markets/interest-rates-and-yields/daily-yields-of-current-federal-securities-772220",
            "verdichtung": "keine (bereits taeglich, nur Bankarbeitstage; Tage ohne Wert (Feiertage) ausgelassen)",
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
        }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
