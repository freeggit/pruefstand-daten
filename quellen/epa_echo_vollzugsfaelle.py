#!/usr/bin/env python3
"""EPA ECHO: Bundes-Vollzugsfaelle (ICIS-FE&C) je Tag der Erfassung in der oeffentlichen Datenbank.
Quelle: https://echo.epa.gov/files/echodownloads/case_downloads.zip (CASE_MILESTONES.csv, CASE_ENFORCEMENTS.csv),
beschrieben auf https://echo.epa.gov/tools/data-downloads (woechentliche Aktualisierung).

Datum = Meilenstein «Enforcement Action Data Entered» (Tag, an dem der Fall in ICIS erfasst wurde und damit
mit der naechsten woechentlichen ECHO-Aktualisierung oeffentlich wird). Das Datum des Final Order liegt oft
Wochen vor der Erfassung und wird NICHT verwendet (sonst rueckwirkende Nachtraege = Revision).
Reihen ab 1997-01-01 (vorher Massenmigration alter Faelle mit Erfassung lange nach dem Entscheid),
jeder Kalendertag bis zum letzten Erfassungstag der Datei (keine Tage danach), 0 = keine Erfassung.
Reihen: faelle_gesamt (alle Faelle), faelle_justiz (gerichtliche Faelle, Activity Type JDC)."""
import csv
import datetime as dt
import gzip
import io
import json
import os
import urllib.error
import urllib.request
import zipfile

ID = "epa_echo_vollzugsfaelle"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
URL = "https://echo.epa.gov/files/echodownloads/case_downloads.zip"
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
START = dt.date(1997, 1, 1)


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


def lies(z, name):
    return csv.DictReader(io.TextIOWrapper(z.open(name), encoding="latin-1", newline=""))


def main():
    os.makedirs(D, exist_ok=True)
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            blob = r.read()
    except urllib.error.HTTPError as e:
        raise SystemExit("HTTP %d" % e.code)
    z = zipfile.ZipFile(io.BytesIO(blob))
    typ = {}
    for x in lies(z, "CASE_ENFORCEMENTS.csv"):
        typ[x["ACTIVITY_ID"]] = x["ACTIVITY_TYPE_CODE"]
    erfasst = {}
    for x in lies(z, "CASE_MILESTONES.csv"):
        if x["SUB_ACTIVITY_TYPE_DESC"].strip() != "Enforcement Action Data Entered" or not x["ACTUAL_DATE"]:
            continue
        try:
            d = dt.datetime.strptime(x["ACTUAL_DATE"].strip(), "%m/%d/%Y").date()
        except ValueError:
            continue
        a = x["ACTIVITY_ID"]
        if a not in erfasst or d < erfasst[a]:
            erfasst[a] = d
    if len(erfasst) < 50000:
        raise SystemExit("unerwartetes Format: %d Faelle" % len(erfasst))
    heute = dt.datetime.now(dt.timezone.utc).date()
    ges, jus = {}, {}
    for a, d in erfasst.items():
        if d < START or d > heute:
            continue
        ges[d] = ges.get(d, 0) + 1
        if typ.get(a) == "JDC":
            jus[d] = jus.get(d, 0) + 1
    ende = max(ges)
    tage = []
    t = START
    while t <= ende:
        tage.append(t)
        t += dt.timedelta(days=1)
    schreibe("faelle_gesamt", [(k.isoformat(), ges.get(k, 0)) for k in tage])
    schreibe("faelle_justiz", [(k.isoformat(), jus.get(k, 0)) for k in tage])
    pub = ("woechentlich (ECHO-Datendownloads werden woechentlich aus ICIS aktualisiert, siehe "
           "echo.epa.gov/tools/data-downloads; ein am Tag X erfasster Fall ist spaetestens mit der "
           "Aktualisierung der Folgewoche oeffentlich)")
    gem = {
        "einheit": "Anzahl Faelle",
        "quelle_url": URL,
        "verdichtung": "Zaehlung der Faelle je Tag des Meilensteins 'Enforcement Action Data Entered'; "
                       "Kalendertage ohne Erfassung = 0",
        "verfuegbar_nach_tagen": 8,
        "revidiert": False,
        "revision_hinweis": "Erfassungsdatum aendert sich nicht; einzelne spaeter geloeschte Faelle koennen "
                            "Altwerte geringfuegig senken",
        "publikation": pub,
    }
    meta = {
        "faelle_gesamt": dict(gem, beschreibung="Neu erfasste formelle EPA-Vollzugsfaelle (administrativ und "
                              "gerichtlich, Clean Air/Water Act, RCRA, CERCLA u.a.) je Erfassungstag"),
        "faelle_justiz": dict(gem, beschreibung="Neu erfasste gerichtliche EPA-Vollzugsfaelle (an DOJ/Gericht, "
                              "meist Grossfirmen mit hohen Bussen) je Erfassungstag"),
    }
    with open(os.path.join(D, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2, sort_keys=True)
    print("ok", len(erfasst), "Faelle, letzter Erfassungstag", ende)


if __name__ == "__main__":
    main()
