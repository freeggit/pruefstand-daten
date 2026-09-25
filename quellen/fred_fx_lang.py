#!/usr/bin/env python3
import gzip
import io
import json
import os
import urllib.request

ID = "fred_fx_lang"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)

SERIES = {
    "gbpusd": ("DEXUSUK", "USD je GBP", "USD/GBP-Wechselkurs (Federal Reserve H.10, Noon Buying Rate/Referenzkurs), taeglich an US-Bankarbeitstagen (Serie DEXUSUK)."),
    "usdcad": ("DEXCAUS", "CAD je USD", "USD/CAD-Wechselkurs (Federal Reserve H.10, Noon Buying Rate/Referenzkurs), taeglich an US-Bankarbeitstagen (Serie DEXCAUS)."),
    "audusd": ("DEXUSAL", "USD je AUD", "USD/AUD-Wechselkurs (Federal Reserve H.10, Noon Buying Rate/Referenzkurs), taeglich an US-Bankarbeitstagen (Serie DEXUSAL)."),
}


def fetch(sid):
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=%s" % sid
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8"), url


def parse(text):
    lines = text.splitlines()
    rows = []
    for line in lines[1:]:
        if not line:
            continue
        d, _, v = line.partition(",")
        v = v.strip()
        if not v or v == ".":
            continue
        try:
            fv = float(v)
        except ValueError:
            continue
        rows.append((d, fv))
    rows.sort()
    return rows


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
    meta = {}
    for reihe, (sid, einheit, beschreibung) in SERIES.items():
        text, url = fetch(sid)
        rows = parse(text)
        if not rows:
            raise SystemExit("keine Daten fuer %s" % sid)
        gzip_write(os.path.join(OUT_DIR, reihe + ".csv.gz"), rows)
        meta[reihe] = {
            "einheit": einheit,
            "beschreibung": beschreibung,
            "quelle_url": url,
            "verdichtung": "keine (bereits taeglich)",
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
        }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
