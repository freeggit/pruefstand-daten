#!/usr/bin/env python3
"""EZB-Ratssitzungen mit geldpolitischem Beschluss (Tage der Pressemitteilung
«Monetary policy decisions»), 0/1-Reihe je Kalendertag.

Quelle: Jahreslisten der EZB unter
https://www.ecb.europa.eu/press/govcdec/mopo/<JAHR>/html/index_include.en.html
Ereignistag = isoDate eines Eintrags mit Titel «Monetary policy decisions» oder
«Combined monetary policy decisions and statement» (Tag der Bekanntgabe).
Ausgeschlossen: ausserordentliche, nicht im Voraus terminierte Beschluesse
(17.9.2001 nach den Anschlaegen, 8.10.2008 koordinierte Zinssenkung).
Reihe beginnt am ersten Listeneintrag (1999-03-04); die Sitzungen Jan/Feb 1999
fehlen in der EZB-Liste und werden nicht ergaenzt.
"""
import datetime
import gzip
import io
import json
import os
import re
import time
import urllib.request

ID = "ecb_ratssitzungen_termine"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
URL = "https://www.ecb.europa.eu/press/govcdec/mopo/%d/html/index_include.en.html"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
AUSSERORDENTLICH = {"2001-09-17", "2008-10-08"}
RE_ITEM = re.compile(r'<dt isoDate="(\d{4}-\d{2}-\d{2})">.*?<div class="title"><a [^>]*>([^<]*)</a>', re.S)


def fetch(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def gzip_write(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("datum,wert\n" + "".join("%s,%d\n" % r for r in rows)).encode())
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    heute = datetime.datetime.utcnow().date()
    tage = set()
    for jahr in range(1999, heute.year + 1):
        s = fetch(URL % jahr)
        for d, t in RE_ITEM.findall(s):
            t = t.strip().lower()
            if t.startswith("monetary policy decisions") or t.startswith("combined monetary policy decisions"):
                if d not in AUSSERORDENTLICH:
                    tage.add(d)
        time.sleep(0.3)
    if len(tage) < 300:
        raise SystemExit("zu wenige Sitzungstage: %d" % len(tage))
    start = datetime.date.fromisoformat(min(tage))
    rows = []
    d = start
    while d <= heute:
        rows.append((d.isoformat(), 1 if d.isoformat() in tage else 0))
        d += datetime.timedelta(days=1)
    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "sitzung.csv.gz"), rows)
    meta = {"sitzung": {
        "einheit": "Indikator (0/1)",
        "beschreibung": "1 am Tag einer planmaessigen geldpolitischen EZB-Ratssitzung (Tag der Pressemitteilung 'Monetary policy decisions', auch ohne Zinsaenderung), sonst 0, je Kalendertag ab 1999-03-04. Ausserordentliche Beschluesse (2001-09-17, 2008-10-08) ausgeschlossen; Sitzungen Jan/Feb 1999 fehlen in der EZB-Liste. Bis Okt. 2001 zwei Zinssitzungen je Monat, danach monatlich, ab 2015 sechswoechentlich.",
        "quelle_url": "https://www.ecb.europa.eu/press/govcdec/mopo/html/index.en.html",
        "verdichtung": "keine (Ereignistage aus amtlicher EZB-Liste der geldpolitischen Beschluesse)",
        "verfuegbar_nach_tagen": 0,
        "revidiert": False,
        "publikation": "taeglich (Sitzungstermine veroeffentlicht die EZB im Voraus im Sitzungskalender; Beschluss wird am Sitzungstag 13:45/14:15 MEZ bekanntgegeben)",
        "status": "aktiv",
    }}
    with open(os.path.join(OUT_DIR, "meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1, sort_keys=True)
    print("sitzung", rows[0][0], rows[-1][0], len(rows), sum(v for _, v in rows))


if __name__ == "__main__":
    main()
