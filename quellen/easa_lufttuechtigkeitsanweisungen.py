#!/usr/bin/env python3
"""EASA Airworthiness Directives (eigene EASA-ADs) je Ausgabetag.

Quelle: EASA Safety Publications Tool, CSV-Export der erweiterten Suche je Jahr
(https://ad.easa.europa.eu/?fi_action=advanced&fi_date_start=..&fi_date_end=..&format=csv).
Gezaehlt werden nur von der EASA selbst ausgegebene ADs (Nummer JJJJ-NNNN, inkl.
Revisionen RN, Notfall-ADs -E und Korrekturen), nicht die im Tool gespiegelten ADs
anderer Behoerden (US-, CF-, BR- usw.). Datum = Issue Date (Tag der Veroeffentlichung
im Tool); Kalendertage ohne AD = 0, Ende = gestern (UTC).

Abgeschlossene Jahre aelter als Vorjahr werden als Zwischenstand in cache.json
gehalten (je Jahr Liste der AD-Nummern mit Datum), Vorjahr und laufendes Jahr werden
bei jedem Lauf neu geholt.
"""
import csv
import datetime
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ID = "easa_lufttuechtigkeitsanweisungen"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "neu", ID)
CACHE = os.path.join(OUT, "cache.json")
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
URL = ("https://ad.easa.europa.eu/?fi_action=advanced&fi_keyword=&fi_date_start=%d-01-01"
       "&fi_date_end=%d-12-31&r=9000&format=csv&sep=c")
ERSTES_JAHR = 2003
EIGEN = re.compile(r"^(\d{4})-(\d{4})(R\d+)?(-[A-Z]+)?$")


def hole_jahr(jahr):
    req = urllib.request.Request(URL % (jahr, jahr), headers={"User-Agent": UA})
    letzte = None
    for versuch in range(2):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                ctype = r.headers.get("Content-Type", "")
                roh = r.read().decode("utf-8-sig")
            break
        except Exception as e:  # Zeitlimit: einmal wiederholen
            if getattr(e, "code", None) in (403, 429):
                raise
            letzte = e
            time.sleep(3)
    else:
        raise letzte
    if not roh.startswith('"AD class"'):
        raise RuntimeError("Jahr %d: kein CSV (Content-Type %s)" % (jahr, ctype))
    eintraege = []
    for z in csv.DictReader(io.StringIO(roh)):
        nr = (z.get("Class number") or "").strip()
        dat = (z.get("Issue Date") or "").strip()
        if not nr or not EIGEN.match(nr):
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dat):
            continue
        if not dat.startswith(str(jahr)):
            continue
        eintraege.append([nr, dat, (z.get("AD class") or "").strip()])
    return eintraege


def schreibe(name, werte):
    pfad = os.path.join(OUT, name + ".csv.gz")
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as g:
        g.write(b"datum,wert\n")
        for d, v in werte:
            g.write(("%s,%d\n" % (d, v)).encode())
    with open(pfad + ".tmp", "wb") as f:
        f.write(buf.getvalue())
    os.replace(pfad + ".tmp", pfad)


def main():
    os.makedirs(OUT, exist_ok=True)
    heute = datetime.datetime.now(datetime.timezone.utc).date()
    cache = {}
    if os.path.isfile(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    jahre = list(range(ERSTES_JAHR, heute.year + 1))
    zu_holen = [j for j in jahre if str(j) not in cache or j >= heute.year - 1]
    with ThreadPoolExecutor(3) as ex:
        ergebnisse = dict(zip(zu_holen, ex.map(hole_jahr, zu_holen)))
    for j, e in ergebnisse.items():
        if j < heute.year - 1:
            cache[str(j)] = e
    alle = []
    for j in jahre:
        alle.extend(ergebnisse[j] if j in ergebnisse else cache[str(j)])
    # Doppel (gleiche Nummer) nur einmal zaehlen
    gesehen = {}
    for nr, dat, kl in alle:
        gesehen.setdefault(nr, (dat, kl))
    if len(gesehen) < 3000:
        raise RuntimeError("zu wenige EASA-ADs: %d" % len(gesehen))
    gesamt, notfall = {}, {}
    for nr, (dat, kl) in gesehen.items():
        gesamt[dat] = gesamt.get(dat, 0) + 1
        if kl == "EAD" or nr.endswith("-E"):
            notfall[dat] = notfall.get(dat, 0) + 1
    start = datetime.date.fromisoformat(min(gesamt))
    ende = heute - datetime.timedelta(days=1)
    tage = []
    d = start
    while d <= ende:
        tage.append(d.isoformat())
        d += datetime.timedelta(days=1)
    schreibe("anzahl_ads", [(t, gesamt.get(t, 0)) for t in tage])
    schreibe("notfall_ads", [(t, notfall.get(t, 0)) for t in tage])
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, sort_keys=True, separators=(",", ":"))
    pub = ("taeglich (EASA veroeffentlicht jede AD am Ausgabetag im Safety Publications Tool; "
           "Issue Date = Veroeffentlichung, Effective Date meist 14 Tage spaeter; Notfall-ADs "
           "wirksam am Ausgabetag; Quelle: ad.easa.europa.eu, EASA AD FAQ)")
    gemeinsam = {
        "quelle_url": "https://ad.easa.europa.eu/",
        "verfuegbar_nach_tagen": 0,
        "publikation": pub,
        "revidiert": False,
    }
    meta = {
        "anzahl_ads": dict(gemeinsam, **{
            "einheit": "Anzahl ADs",
            "beschreibung": "Von der EASA ausgegebene Airworthiness Directives (inkl. Revisionen und Notfall-ADs) je Ausgabetag; ohne gespiegelte ADs anderer Behoerden",
            "verdichtung": "Zaehlung je Issue Date (Nummern JJJJ-NNNN[Rn][-E]); Kalendertage ohne AD = 0; Abschluss vor heute",
        }),
        "notfall_ads": dict(gemeinsam, **{
            "einheit": "Anzahl Notfall-ADs",
            "beschreibung": "Von der EASA ausgegebene Emergency Airworthiness Directives (Klasse EAD bzw. Nummer -E) je Ausgabetag",
            "verdichtung": "Zaehlung je Issue Date; Kalendertage ohne Notfall-AD = 0; Abschluss vor heute",
        }),
    }
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("EASA-ADs %d, Tage %d, %s bis %s" % (len(gesehen), len(tage), tage[0], tage[-1]))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Fehler: %r" % (e,), file=sys.stderr)
        sys.exit(1)
