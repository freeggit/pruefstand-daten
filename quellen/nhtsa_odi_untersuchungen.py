#!/usr/bin/env python3
"""NHTSA Office of Defects Investigation: neu eroeffnete Defekt-Untersuchungen je Eroeffnungstag.
Quelle: https://static.nhtsa.gov/odi/ffdd/inv/FLAT_INV.zip (Feldbeschreibung INV.txt daneben).
Eine Untersuchung (NHTSA ACTION NUMBER, Feld 1) hat viele Zeilen (je Marke/Modell/Jahr); gezaehlt wird
jede Nummer einmal am Datum ODATE (Feld 7, Date Opened). Gezaehlt werden von der ODI eroeffnete
Verfahren (PE Preliminary Evaluation, EA Engineering Analysis, RQ Recall Query, AQ Audit Query,
EQ/SQ Equipment-/Service-Query u.a.), NICHT Defekt-Petitionen (DP, von Dritten eingereicht).
Reihe ab 1996-01-01 (oeffentliche ODI-Datenbank im Netz; fuer die Zeit davor ist der Tag der
oeffentlichen Bekanntgabe nicht belegt), jeder Kalendertag bis heute (UTC), 0 = keine Eroeffnung."""
import datetime as dt
import gzip
import io
import json
import os
import urllib.error
import urllib.request
import zipfile

ID = "nhtsa_odi_untersuchungen"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
URL = "https://static.nhtsa.gov/odi/ffdd/inv/FLAT_INV.zip"
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
START = dt.date(1996, 1, 1)


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
            raw = r.read()
    except urllib.error.HTTPError as e:
        raise SystemExit("HTTP %d" % e.code)
    z = zipfile.ZipFile(io.BytesIO(raw))
    name = [n for n in z.namelist() if n.upper().endswith(".TXT")][0]
    ersteroeff = {}
    with z.open(name) as f:
        for line in f:
            p = line.decode("latin-1").rstrip("\r\n").split("\t")
            if len(p) < 8:
                continue
            nr, od = p[0].strip(), p[6].strip()
            if not nr or nr.upper().startswith("DP") or len(od) != 8:
                continue
            try:
                d = dt.date(int(od[:4]), int(od[4:6]), int(od[6:8]))
            except ValueError:
                continue
            if nr not in ersteroeff or d < ersteroeff[nr]:
                ersteroeff[nr] = d
    if len(ersteroeff) < 3000:
        raise SystemExit("unerwartet wenige Untersuchungen: %d" % len(ersteroeff))
    heute = dt.datetime.now(dt.timezone.utc).date()
    zahl = {}
    for d in ersteroeff.values():
        if START <= d <= heute:
            zahl[d] = zahl.get(d, 0) + 1
    rows = []
    t = START
    while t <= heute:
        rows.append((t.isoformat(), zahl.get(t, 0)))
        t += dt.timedelta(days=1)
    schreibe("untersuchungen", rows)
    meta = {"untersuchungen": {
        "einheit": "Anzahl eroeffneter Untersuchungen",
        "beschreibung": "Taegliche Anzahl neu eroeffneter NHTSA-ODI-Defektuntersuchungen (PE, EA, RQ, AQ u.a., "
                        "ohne Defekt-Petitionen DP), je Aktionsnummer einmal am Eroeffnungsdatum ODATE gezaehlt; "
                        "0 an Tagen ohne Eroeffnung; ab 1996.",
        "quelle_url": URL,
        "verdichtung": "Zaehlung verschiedener NHTSA ACTION NUMBER je Kalendertag (ODATE)",
        "verfuegbar_nach_tagen": 7,
        "revidiert": False,
        "publikation": "woechentlich: die ODI veroeffentlicht Eroeffnungsberichte (Opening Resume) auf nhtsa.gov "
                       "gesammelt, Eroeffnungstage haeufen sich auf Freitage (z.B. 2026-10-09, -10-23, -10-30, "
                       "-11-06) und standen am 2026-11-11 bereits im Flat File; ein maschinenlesbares "
                       "Veroeffentlichungsdatum fehlt, darum konservativ 7 Tage",
    }}
    with open(os.path.join(D, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2, sort_keys=True)
    print("ok", len(ersteroeff), "Untersuchungen")


if __name__ == "__main__":
    main()
