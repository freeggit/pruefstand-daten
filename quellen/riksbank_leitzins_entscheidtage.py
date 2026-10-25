#!/usr/bin/env python3
import gzip
import io
import json
import os
import urllib.request
from datetime import date

ID = "riksbank_leitzins_entscheidtage"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)

# Riksbank SWEA-API, Repo-Satz (SECBREPOEFF), Bankarbeitstage, ohne Schluessel
URL = "https://api.riksbank.se/swea/v1/Observations/SECBREPOEFF/1994-01-01/{b}"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
    for r in fetch(URL.format(b=heute.isoformat())):
        raw[r["date"]] = float(r["value"])
    rows = sorted(raw.items())
    if len(rows) < 500:
        raise SystemExit("zu wenige Daten")
    flags, prev = [], None
    for d, v in rows:
        flags.append((d, 1 if prev is not None and abs(v - prev) >= 0.1 - 1e-9 else 0))
        prev = v
    gzip_write(os.path.join(OUT_DIR, "aenderungstage.csv.gz"), flags, "%s,%d\n")
    gzip_write(os.path.join(OUT_DIR, "ziel.csv.gz"), rows, "%s,%s\n")
    q = "https://api.riksbank.se/swea/v1/Observations/SECBREPOEFF"
    meta = {
        "aenderungstage": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am ersten Tag, an dem ein geaenderter Repo-Satz der Riksbank gilt (Wirksamkeitstag), sonst 0 (nur Aenderungen ab 0,10 Prozentpunkten; kleinere Schritte des Marktsatzes 1994-95 zaehlen nicht). Der Entscheid wird vorher bekanntgegeben (meist ca. eine Woche vor Wirksamkeit), der Flag liegt also nie vor der Bekanntgabe.",
            "quelle_url": q,
            "verdichtung": "keine (Aenderungsindikator aus Tagesreihe abgeleitet)",
            "publikation": "taeglich (Bekanntgabe liegt vor dem Wirksamkeitstag; Quelle: Riksbank Pressemitteilungen zu Zinsentscheiden)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
        "ziel": {
            "einheit": "% p.a.",
            "beschreibung": "Repo-Satz der Riksbank, Wirksamkeitsdatum, Bankarbeitstage",
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
