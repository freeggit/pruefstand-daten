#!/usr/bin/env python3
"""Nasdaq Trader Trade-Halt-Archiv: Anzahl Handelsunterbrechungen je Tag (HaltDate, US-Ostzeit).
RSS https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts&haltdate=MMTTJJJJ je Werktag.
Zwei Reihen: firmen (Nachrichten-, Regulierungs-, Delisting- und sonstige Einzelfirmen-Halts,
alle Codes ausser Volatilitaetspausen) und volatilitaet (LUDP/LUDS/M/MWC*, ab Start LULD
2013-04-08). Etappenweise: cache.json (Datum -> [firmen, volatilitaet]). Je Lauf Zeitbudget;
CSV erst, wenn der Cache lueckenlos ab START reicht. 403/429 = Befund, nicht umgangen.
Nichts geschaetzt, nichts aufgefuellt; 0 = Archiv nennt fuer den Werktag keine Unterbrechung."""
import concurrent.futures as cf
import datetime as dt
import gzip
import io
import json
import os
import re
import time
import urllib.error
import urllib.request

ID = "nasdaq_handelsunterbrechungen"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
URL = "https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts&haltdate=%s"
START = dt.date(2006, 1, 3)
START_VOL = dt.date(2013, 4, 8)  # Limit-Up-Limit-Down-Plan, Phase 1
BUDGET = float(os.environ.get("BUDGET_S", "150"))
VOL = re.compile(r"^(LUDP|LUDS|M|MWC\d*)$")
ITEM = re.compile(r"<item>(.*?)</item>", re.S)
CODE = re.compile(r"<ndaq:ReasonCode>([^<]*)</ndaq:ReasonCode>")
HDAT = re.compile(r"<ndaq:HaltDate>([^<]*)</ndaq:HaltDate>")
NUM = re.compile(r"<ndaq:numItems>(\d+)</ndaq:numItems>")


def hole(d):
    url = URL % d.strftime("%m%d%Y")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            return d, "SPERRE %d" % e.code
        return d, None
    except Exception:
        return d, None
    m = NUM.search(text)
    if "NASDAQ Trade Halts" not in text or not m:
        return d, None  # Schutzseite o.ae.: nicht cachen
    items = ITEM.findall(text)
    if len(items) != int(m.group(1)):
        return d, None
    soll = d.strftime("%m/%d/%Y")
    f = v = 0
    for it in items:
        h = HDAT.search(it)
        if not h or h.group(1).strip() != soll:
            continue
        c = CODE.search(it)
        c = c.group(1).strip() if c else ""
        if VOL.match(c):
            v += 1
        else:
            f += 1
    return d, [f, v]


def schreibe(name, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for k, v in rows:
            t.write("%s,%d\n" % (k, v))
        t.flush()
    with open(os.path.join(D, name + ".csv.gz"), "wb") as fh:
        fh.write(buf.getvalue())


def main():
    os.makedirs(D, exist_ok=True)
    cp = os.path.join(D, "cache.json")
    cache = json.load(open(cp)) if os.path.isfile(cp) else {}
    heute = dt.datetime.utcnow().date()
    # Tag d gilt als abgeschlossen ab heute > d+1 (UTC), Nachhandel endet 20:00 ET
    ende = heute - dt.timedelta(days=1)
    tage = []
    d = START
    while d < ende:
        if d.weekday() < 5 and d.isoformat() not in cache:
            tage.append(d)
        d += dt.timedelta(days=1)
    tage.sort(reverse=True)  # neueste zuerst
    t0 = time.time()
    neu = 0
    sperre = None
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for i in range(0, len(tage), 40):
            if time.time() - t0 > BUDGET or sperre:
                break
            for d, v in ex.map(hole, tage[i:i + 40]):
                if isinstance(v, str):
                    sperre = v
                elif v is not None:
                    cache[d.isoformat()] = v
                    neu += 1
            time.sleep(0.5)
    with open(cp, "w") as fh:
        json.dump(dict(sorted(cache.items())), fh, separators=(",", ":"))
    offen = []
    d = START
    while d < ende:
        if d.weekday() < 5 and d.isoformat() not in cache:
            offen.append(d)
        d += dt.timedelta(days=1)
    print("Cache %d Tage, neu %d, offen %d%s" % (len(cache), neu, len(offen), (", " + sperre) if sperre else ""))
    if sperre and neu == 0:
        raise SystemExit(sperre)
    if offen:
        if os.path.isfile(os.path.join(D, "firmen.csv.gz")):
            return
        raise SystemExit("Etappe: noch %d Tage offen" % len(offen))
    ks = sorted(cache)
    schreibe("firmen", [(k, cache[k][0]) for k in ks])
    schreibe("volatilitaet", [(k, cache[k][1]) for k in ks if k >= START_VOL.isoformat()])
    pub = ("taeglich (Echtzeit-Feed: jede Unterbrechung erscheint im Moment der Anordnung; "
           "Tag abgeschlossen mit Ende Nachhandel 20:00 ET; Quelle: nasdaqtrader.com Trade Halts RSS)")
    gem = {"einheit": "Anzahl Unterbrechungen", "quelle_url": URL % "<MMTTJJJJ>",
           "publikation": pub, "verfuegbar_nach_tagen": 0, "revidiert": False}
    meta = {
        "firmen": dict(gem, beschreibung="Anzahl Handelsunterbrechungen an Nasdaq-Systemen je HaltDate (US-Ostzeit), alle Gruende ausser Volatilitaetspausen: ausstehende Nachrichten (T1/T3), Regulierung (H-Codes), Delisting u.a.; Grundcode wird nach Wiederaufnahme von T1 auf T3 nachgefuehrt, darum zusammengefasst",
                   verdichtung="Zaehlung der Archiv-Eintraege je Werktag; Werktage ohne Eintrag = 0 (auch Boersenfeiertage)"),
        "volatilitaet": dict(gem, beschreibung="Anzahl Volatilitaetspausen (LULD LUDP/LUDS, M, MWC*) je HaltDate, ab Start des Limit-Up-Limit-Down-Plans 2013-04-08",
                   verdichtung="Zaehlung der Archiv-Eintraege je Werktag; Werktage ohne Eintrag = 0 (auch Boersenfeiertage)"),
    }
    with open(os.path.join(D, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
