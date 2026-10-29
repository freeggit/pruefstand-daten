#!/usr/bin/env python3
import gzip
import io
import json
import os
import urllib.request
from datetime import date

ID = "norges_bank_leitzins_entscheidtage"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)

# Norges Bank Datenportal (SDMX), Leitzins (Sight Deposit Rate), Bankarbeitstage, ohne Schluessel
URL = "https://data.norges-bank.no/api/data/IR/B.KPRA.SD.?format=csv&startPeriod=1991-01-01"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def gzip_write(path, rows, fmt):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for d, v in rows:
            t.write(fmt % (d, v))
        t.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    heute = date.today()
    raw = {}
    for line in fetch(URL).splitlines()[1:]:
        p = line.split(";")
        if len(p) > 12 and p[12]:
            raw[p[11]] = float(p[12])
    rows = sorted(raw.items())
    if len(rows) < 500:
        raise SystemExit("zu wenige Daten")
    flags, prev = [], None
    for d, v in rows:
        flags.append((d, 1 if d >= "1994-02-04" and prev is not None and abs(v - prev) >= 0.1 - 1e-9 else 0))
        prev = v
    gzip_write(os.path.join(OUT_DIR, "aenderungstage.csv.gz"), flags, "%s,%d\n")
    gzip_write(os.path.join(OUT_DIR, "ziel.csv.gz"), rows, "%s,%s\n")
    q = "https://data.norges-bank.no/api/data/IR/B.KPRA.SD."
    meta = {
        "aenderungstage": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am ersten Tag, an dem ein geaenderter Leitzins der Norges Bank (Sight Deposit Rate) gilt (Wirksamkeitstag), sonst 0 (Aenderungen ab 0,10 Prozentpunkten, Flags erst ab 4.2.1994 gemaess Regel Zusatz 5). Der Entscheid wird vorher bekanntgegeben (am oder vor Wirksamkeit), der Flag liegt also nie vor der Bekanntgabe.",
            "quelle_url": q,
            "verdichtung": "keine (Aenderungsindikator aus Tagesreihe abgeleitet)",
            "publikation": "taeglich (Bekanntgabe liegt vor dem Wirksamkeitstag; Quelle: Norges Bank Pressemitteilungen zu Zinsentscheiden; Wirksamkeit am oder nach dem Bekanntgabetag)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
        "ziel": {
            "einheit": "% p.a.",
            "beschreibung": "Leitzins der Norges Bank (Sight Deposit Rate), Wirksamkeitsdatum, Bankarbeitstage",
            "quelle_url": q,
            "verdichtung": "keine",
            "publikation": "taeglich (Satz vor Wirksamkeit bekanntgegeben)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
            "status": "ruhend",
        },
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
