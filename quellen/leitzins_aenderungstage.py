#!/usr/bin/env python3
import gzip
import io
import json
import os
import urllib.request

ID = "leitzins_aenderungstage"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)

URL_DFEDTAR = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTAR"
URL_DFEDTARU = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU"
URL_ECBDFR = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=ECBDFR"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse(text):
    rows = []
    for line in text.splitlines()[1:]:
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


def change_days(rows):
    out = []
    prev = None
    for d, v in rows:
        flag = 1 if (prev is not None and v != prev) else 0
        out.append((d, flag))
        prev = v
    return out


def build_fomc():
    pre = parse(fetch(URL_DFEDTAR))
    post = parse(fetch(URL_DFEDTARU))
    combined = pre + post
    combined.sort()
    return change_days(combined)


def build_ezb():
    rows = parse(fetch(URL_ECBDFR))
    return change_days(rows)


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
    fomc_rows = build_fomc()
    ezb_rows = build_ezb()
    if not fomc_rows or not ezb_rows:
        raise SystemExit("keine Daten")

    gzip_write(os.path.join(OUT_DIR, "fomc.csv.gz"), fomc_rows)
    gzip_write(os.path.join(OUT_DIR, "ezb.csv.gz"), ezb_rows)

    meta = {
        "fomc": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am Tag, an dem sich das von der Fed gesetzte Leitzins-Zielband gegenueber dem Vortag aendert (abgeleitet aus den taeglichen FRED-Reihen DFEDTAR bis 2008-12-15, danach DFEDTARU), sonst 0. Erfasst nur tatsaechliche Zielsatzaenderungen, nicht jede FOMC-Sitzung mit Halte-Entscheid.",
            "quelle_url": URL_DFEDTARU,
            "verdichtung": "keine (bereits taeglich, Aenderungsindikator aus taeglicher Zielsatzreihe abgeleitet)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
        "ezb": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am Tag, an dem sich der EZB-Einlagensatz (ECBDFR) gegenueber dem Vortag aendert, sonst 0. Erfasst nur tatsaechliche Satzaenderungen, nicht jede EZB-Ratssitzung mit Halte-Entscheid.",
            "quelle_url": URL_ECBDFR,
            "verdichtung": "keine (bereits taeglich, Aenderungsindikator aus taeglicher Zinsreihe abgeleitet)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
