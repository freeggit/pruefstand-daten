#!/usr/bin/env python3
"""Nasdaq Trader Reg-SHO-Schwellenliste (Nasdaq-gelistete Titel): Anzahl Titel je Tag.
Tagesdateien nasdaqth<JJJJMMTT>.txt, Erstellzeit in der Fusszeile (ca. 23:00 ET am Datumstag).
Etappenweise: cache.json (Datum -> Anzahl, oder "x" = keine Datei, z.B. Feiertag). Je Lauf
Zeitbudget; CSV erst, wenn der Cache lueckenlos ab START reicht. Bot-Schutzseiten werden nicht
umgangen und nicht gecacht (naechster Lauf erneut). Nichts geschaetzt, nichts aufgefuellt."""
import concurrent.futures as cf
import datetime as dt
import gzip
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

ID = "nasdaq_regsho_schwellenliste_dichte"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
URL = "https://www.nasdaqtrader.com/dynamic/symdir/regsho/nasdaqth%s.txt"
START = dt.date(2006, 1, 3)
BUDGET = float(os.environ.get("BUDGET_S", "150"))
KOPF = "Symbol|Security Name|Market Category|Reg SHO Threshold Flag"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def hole(d):
    url = URL % d.strftime("%Y%m%d")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with OPENER.open(req, timeout=30) as r:
            text = r.read().decode("latin-1")
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 404):
            return d, "x"
        if e.code in (403, 429):
            return d, "SPERRE %d" % e.code
        return d, None
    except Exception:
        return d, None
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines or not lines[0].startswith(KOPF):
        return d, None  # Bot-Schutz o.ae.: nicht cachen
    n = sum(1 for l in lines[1:] if l.count("|") >= 3)
    return d, n


def main():
    os.makedirs(D, exist_ok=True)
    cp = os.path.join(D, "cache.json")
    cache = json.load(open(cp)) if os.path.isfile(cp) else {}
    heute = dt.datetime.utcnow().date()
    tage = []
    d = START
    while d < heute:
        if d.weekday() < 5:
            k = d.isoformat()
            v = cache.get(k)
            # "x" bei juengsten Tagen erneut pruefen (Datei evtl. noch nicht erstellt)
            if v is None or (v == "x" and (heute - d).days <= 4):
                tage.append(d)
        d += dt.timedelta(days=1)
    tage.sort(reverse=True)  # neueste zuerst, damit K5 laufend erfuellt bleibt
    t0 = time.time()
    neu = 0
    sperre = None
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for i in range(0, len(tage), 40):
            if time.time() - t0 > BUDGET or sperre:
                break
            for d, v in ex.map(hole, tage[i:i + 40]):
                if isinstance(v, str) and v.startswith("SPERRE"):
                    sperre = v
                elif v is not None:
                    if v == "x" and (heute - d).days <= 1:
                        continue
                    cache[d.isoformat()] = v
                    neu += 1
            time.sleep(0.5)
    with open(cp, "w") as f:
        json.dump(dict(sorted(cache.items())), f, separators=(",", ":"))
    offen = []
    d = START
    while d < heute - dt.timedelta(days=1):
        if d.weekday() < 5 and d.isoformat() not in cache:
            offen.append(d)
        d += dt.timedelta(days=1)
    print("Cache %d Tage, neu %d, offen %d%s" % (len(cache), neu, len(offen), (", " + sperre) if sperre else ""))
    if sperre and neu == 0:
        raise SystemExit(sperre)
    if offen:
        if os.path.isfile(os.path.join(D, "anzahl.csv.gz")):
            return
        raise SystemExit("Etappe: noch %d Tage offen" % len(offen))
    rows = sorted((k, v) for k, v in cache.items() if v != "x")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for k, v in rows:
            t.write("%s,%d\n" % (k, v))
        t.flush()
    with open(os.path.join(D, "anzahl.csv.gz"), "wb") as f:
        f.write(buf.getvalue())
    meta = {"anzahl": {
        "einheit": "Anzahl Titel",
        "beschreibung": "Anzahl Nasdaq-gelisteter Titel auf der Reg-SHO-Schwellenliste (anhaltende Lieferausfaelle), Liste mit Datum = Datei nasdaqth<JJJJMMTT>.txt",
        "quelle_url": "https://www.nasdaqtrader.com/dynamic/symdir/regsho/nasdaqth<JJJJMMTT>.txt",
        "verdichtung": "Zaehlung der Listenzeilen je Tagesdatei (nur Handelstage)",
        "publikation": "taeglich (Fusszeile jeder Datei nennt die Erstellzeit, ca. 23:00 ET am Datumstag, also nach Boersenschluss; darum 1 Tag)",
        "verfuegbar_nach_tagen": 1,
        "revidiert": False,
    }}
    with open(os.path.join(D, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
