#!/usr/bin/env python3
"""Federal Reserve Board: Aufsichtsmassnahmen (Enforcement Actions) je Tag der Bekanntgabe.
Quelle: https://www.federalreserve.gov/supervisionreg/files/enforcementactions.csv
(Liste hinter https://www.federalreserve.gov/supervisionreg/enforcementactions.htm).

Datum = Datum der Pressemitteilung, gelesen aus der verlinkten URL
(.../enforcementJJJJMMTT[a-z].htm, /boarddocs/press/enforcement/JJJJ/JJJJMMTT/, Dateiname der PDF).
Das Wirksamkeitsdatum (Effective Date) liegt vor der Bekanntgabe und wird NICHT verwendet.
Zeilen ohne datierte URL und Zeilen, deren URL mehr als 60 Tage nach oder vor dem Wirksamkeitsdatum
liegt (Link zeigt dann auf eine spaetere Aufhebung, Bekanntgabetag der Massnahme selbst unbelegt),
werden weggelassen (keine Schaetzung). Reihen ab 1997-01-01 (davor fehlen die URL-Daten weitgehend),
jeder Kalendertag bis heute (UTC), 0 = keine Bekanntgabe.
Reihen: institutionen (Massnahmen gegen Banken/Holdings), personen (gegen Einzelpersonen)."""
import csv
import datetime as dt
import gzip
import io
import json
import os
import re
import urllib.error
import urllib.request

ID = "fed_enforcement_massnahmen"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
URL = "https://www.federalreserve.gov/supervisionreg/files/enforcementactions.csv"
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
START = dt.date(1997, 1, 1)
DAT = re.compile(r"((?:19|20)\d{2})(\d{2})(\d{2})")


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
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode("utf-8-sig", "replace")
    except urllib.error.HTTPError as e:
        raise SystemExit("HTTP %d" % e.code)
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows or "Effective Date" not in rows[0] or len(rows) < 1000:
        raise SystemExit("unerwartetes Format")
    heute = dt.datetime.now(dt.timezone.utc).date()
    inst, pers = {}, {}
    weg = 0
    for x in rows:
        m = DAT.search(x.get("URL", ""))
        try:
            eff = dt.date.fromisoformat(x["Effective Date"].strip())
            d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
        except (ValueError, AttributeError):
            d = None
        if d is None or abs((d - eff).days) > 60 or d < START or d > heute:
            weg += 1
            continue
        if x.get("Individual", "").strip():
            pers[d] = pers.get(d, 0) + 1
        else:
            inst[d] = inst.get(d, 0) + 1
    tage = []
    t = START
    while t <= heute:
        tage.append(t)
        t += dt.timedelta(days=1)
    schreibe("institutionen", [(k.isoformat(), inst.get(k, 0)) for k in tage])
    schreibe("personen", [(k.isoformat(), pers.get(k, 0)) for k in tage])
    pub = ("taeglich (jede Massnahme wird mit einer datierten Pressemitteilung auf federalreserve.gov "
           "bekanntgegeben, Datum steht in der URL; Quelle: federalreserve.gov/supervisionreg/enforcementactions.htm)")
    gem = {
        "einheit": "Anzahl Massnahmen",
        "quelle_url": URL,
        "verdichtung": "Zaehlung der Listeneintraege je Datum der Pressemitteilung (aus URL); "
                       "Kalendertage ohne Eintrag = 0; Eintraege ohne belegtes Bekanntgabedatum weggelassen",
        "verfuegbar_nach_tagen": 0,
        "revidiert": False,
        "publikation": pub,
    }
    meta = {
        "institutionen": dict(gem, beschreibung="Fed-Aufsichtsmassnahmen gegen Banken und Bankholdings "
                              "(Written Agreement, Cease and Desist, Civil Money Penalty, PCA u.a.) je Bekanntgabetag"),
        "personen": dict(gem, beschreibung="Fed-Aufsichtsmassnahmen gegen Einzelpersonen "
                         "(Prohibition, Section 19 Letter u.a.) je Bekanntgabetag"),
    }
    with open(os.path.join(D, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2, sort_keys=True)
    print("ok", len(rows), "Eintraege,", weg, "weggelassen")


if __name__ == "__main__":
    main()
