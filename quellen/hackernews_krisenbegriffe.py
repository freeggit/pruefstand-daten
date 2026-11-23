#!/usr/bin/env python3
"""Tageszahl der Hacker-News-Beitraege (Stories), deren Titel einen Krisenbegriff enthaelt.

Quelle: oeffentliche HN-Such-API von Algolia (ohne Login, ohne Schluessel).
Abfrage je Kalendermonat (UTC), hitsPerPage 1000; hat ein Fenster 1000 Treffer,
wird es halbiert. Datum = UTC-Tag des Beitrags (created_at_i). Tage ohne Beitrag = 0
(Tageszaehlung). Der laufende UTC-Tag wird nicht geschrieben.
"""
import calendar
import datetime as dt
import gzip
import io
import json
import os
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ID = "hackernews_krisenbegriffe"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
API = "https://hn.algolia.com/api/v1/search_by_date"
START = dt.date(2007, 2, 1)  # erste HN-Beitraege Feb./Okt. 2006/2007; Index ab 2007
BEGRIFFE = {"layoffs": "layoffs"}  # "recession" verworfen: 2012-2017 nur 16-41 Treffer je Jahr, zu duenn


def abfrage(begriff, von, bis):
    q = urllib.parse.urlencode({
        "query": begriff, "tags": "story", "typoTolerance": "false",
        "restrictSearchableAttributes": "title", "attributesToRetrieve": "created_at_i",
        "attributesToHighlight": "", "hitsPerPage": 1000,
        "numericFilters": "created_at_i>=%d,created_at_i<%d" % (von, bis)})
    req = urllib.request.Request(API + "?" + q, headers={"User-Agent": UA})
    for versuch in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise
            if versuch == 2:
                raise
            time.sleep(2)
        except Exception:
            if versuch == 2:
                raise
            time.sleep(2)
    hits = [h["created_at_i"] for h in d.get("hits", [])]
    if len(hits) >= 1000 and bis - von > 3600:
        mitte = (von + bis) // 2
        return abfrage(begriff, von, mitte) + abfrage(begriff, mitte, bis)
    if len(hits) >= 1000:
        raise RuntimeError("Fenster mit 1000 Treffern nicht teilbar")
    return hits


def fenster(heute):
    out = []
    y, m = START.year, START.month
    ende = calendar.timegm(heute.timetuple())
    while True:
        a = calendar.timegm(dt.date(y, m, 1).timetuple())
        if a >= ende:
            break
        y2, m2 = (y + 1, 1) if m == 12 else (y, m + 1)
        b = min(calendar.timegm(dt.date(y2, m2, 1).timetuple()), ende)
        out.append((a, b))
        y, m = y2, m2
    return out


def schreiben(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("datum,wert\n" + "".join("%s,%d\n" % r for r in rows)).encode("utf-8"))
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    heute = dt.datetime.utcnow().date()  # Abfrage bis Beginn des heutigen UTC-Tages
    fs = fenster(heute)
    ergebnis = {}
    for reihe, begriff in BEGRIFFE.items():
        with ThreadPoolExecutor(6) as ex:
            teile = list(ex.map(lambda f: abfrage(begriff, *f), fs))
        zaehl = {}
        for t in teile:
            for ts in t:
                d = dt.datetime.utcfromtimestamp(ts).date()
                zaehl[d] = zaehl.get(d, 0) + 1
        if not zaehl:
            raise RuntimeError("keine Treffer fuer " + begriff)
        rows, d = [], START
        while d < heute:
            rows.append((d.isoformat(), zaehl.get(d, 0)))
            d += dt.timedelta(days=1)
        ergebnis[reihe] = rows
    os.makedirs(OUT_DIR, exist_ok=True)
    meta = {}
    for reihe, rows in ergebnis.items():
        schreiben(os.path.join(OUT_DIR, reihe + ".csv.gz"), rows)
        meta[reihe] = {
            "einheit": "Anzahl Beitraege pro Tag",
            "beschreibung": "Hacker News: Anzahl Stories je UTC-Tag mit dem Wort '%s' im Titel (ohne Tippfehlertoleranz), 0 an Tagen ohne Treffer" % BEGRIFFE[reihe],
            "quelle_url": API + "?query=%s&tags=story&restrictSearchableAttributes=title&typoTolerance=false" % BEGRIFFE[reihe],
            "verdichtung": "Summe je UTC-Tag (Zaehlung der Einzelbeitraege)",
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
            "publikation": "taeglich (Beitraege sind sofort oeffentlich und ueber die Algolia-HN-API minutennah abrufbar; Tag gilt nach Ablauf des UTC-Tages als vollstaendig)",
            "hinweis": "Nachtraeglich geloeschte oder gesperrte Beitraege koennen fehlen (geringe Abweichung gegenueber dem damaligen Stand).",
            "status": "aktiv",
        }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("OK", {k: len(v) for k, v in ergebnis.items()})


if __name__ == "__main__":
    main()
