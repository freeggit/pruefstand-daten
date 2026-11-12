#!/usr/bin/env python3
"""US Coast Guard National Response Center (NRC): eingegangene Meldungen zu Oel- und Chemiefreisetzungen je Tag.
Quelle: FOIA-Jahresdateien https://nrc.uscg.mil/FOIAFiles/CY<JJ>.xlsx (ab 1990), Tabellenblatt CALLS.
Gezaehlt werden Meldungen mit CALLTYPE «INC» (Vorfall) nach DATE_TIME_RECEIVED (Eingang beim NRC,
Ortszeit Washington). Die Datei des laufenden Jahres wird etwa woechentlich nachgefuehrt.
Zwischenstand: abgeschlossene Jahre werden als Tageszaehlung in data/neu/<id>/cache/<JJJJ>.json
abgelegt und nur neu geholt, wenn die Datei auf dem Server neuer ist (Last-Modified) - so bleibt der
Abruf unter 3 Minuten. Reihe: anzahl_meldungen."""
import datetime as dt
import gzip
import io
import json
import os
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ID = "uscg_nrc_meldungen_oel_chemie"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
BASIS = "https://nrc.uscg.mil/FOIAFiles/CY%02d.xlsx"
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
C = os.path.join(D, "cache")
N = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
START_JAHR = 1990
BUDGET_S = 150


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


def kopf(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="HEAD")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.headers.get("Last-Modified", "")


def lade(url, ziel):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r, open(ziel, "wb") as fh:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            fh.write(b)


def spalte(ref):
    return "".join(ch for ch in ref if ch.isalpha())


def zaehle(pfad, jahr):
    z = zipfile.ZipFile(pfad)
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    ziele = {r.get("Id"): r.get("Target") for r in rels}
    blatt = None
    for s in wb.iter(N + "sheet"):
        if s.get("name", "").upper() == "CALLS":
            rid = s.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            blatt = "xl/" + ziele[rid].lstrip("/").replace("xl/", "", 1)
    if blatt is None:
        raise SystemExit("Blatt CALLS fehlt %d" % jahr)
    strs = []
    if "xl/sharedStrings.xml" in z.namelist():
        for ev, el in ET.iterparse(z.open("xl/sharedStrings.xml")):
            if el.tag == N + "si":
                strs.append("".join(t.text or "" for t in el.iter(N + "t")))
                el.clear()
    n, kopfzeile, sp_d, sp_t, weg = {}, True, None, None, 0
    basis = dt.datetime(1899, 12, 30)
    for ev, el in ET.iterparse(z.open(blatt)):
        if el.tag != N + "row":
            continue
        vals = {}
        for c in el.findall(N + "c"):
            v = c.find(N + "v")
            x = v.text if v is not None else None
            if c.get("t") == "s" and x is not None:
                x = strs[int(x)]
            elif c.get("t") == "inlineStr":
                x = "".join(t.text or "" for t in c.iter(N + "t"))
            vals[spalte(c.get("r", ""))] = x
        el.clear()
        if kopfzeile:
            inv = {str(v).strip().upper(): k for k, v in vals.items() if v}
            sp_d, sp_t = inv.get("DATE_TIME_RECEIVED"), inv.get("CALLTYPE")
            if not sp_d or not sp_t:
                raise SystemExit("Kopfzeile unerwartet %d: %s" % (jahr, sorted(inv)))
            kopfzeile = False
            continue
        if (vals.get(sp_t) or "").strip().upper() != "INC":
            continue
        try:
            d = (basis + dt.timedelta(days=float(vals.get(sp_d)))).date()
        except (TypeError, ValueError):
            weg += 1
            continue
        if d.year != jahr:
            weg += 1  # Eintrag ausserhalb des Dateijahrs: nicht verwenden
            continue
        n[d.isoformat()] = n.get(d.isoformat(), 0) + 1
    return n, weg


def main():
    os.makedirs(C, exist_ok=True)
    t0 = time.time()
    heute = dt.datetime.now(dt.timezone.utc).date()
    alle, offen, fehler = {}, [], []
    for jahr in range(START_JAHR, heute.year + 1):
        url = BASIS % (jahr % 100)
        cp = os.path.join(C, "%d.json" % jahr)
        alt = None
        if os.path.exists(cp):
            with open(cp, encoding="utf-8") as fh:
                alt = json.load(fh)
        try:
            lm = kopf(url)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise SystemExit("HTTP %d bei %s" % (e.code, url))
            fehler.append("%d: HTTP %d" % (jahr, e.code))
            lm = None
        if alt is not None and (lm is None or alt.get("last_modified") == lm):
            alle.update(alt["tage"])
            continue
        if lm is None or time.time() - t0 > BUDGET_S:
            offen.append(jahr)
            if alt is not None:
                alle.update(alt["tage"])
            continue
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "x.xlsx")
            lade(url, p)
            n, weg = zaehle(p, jahr)
        if sum(n.values()) < 1000 and jahr < heute.year:
            raise SystemExit("zu wenige Meldungen %d" % jahr)
        with open(cp, "w", encoding="utf-8") as fh:
            json.dump({"last_modified": lm, "weggelassen": weg, "tage": n}, fh, sort_keys=True)
        alle.update(n)
    if offen:
        print("Etappe: offen", offen)
    # Reihe nur bis zum letzten lueckenlos vorhandenen Jahr fortschreiben
    jahre = sorted(int(k[:4]) for k in alle)
    if not jahre:
        raise SystemExit("keine Daten")
    letzte = max(alle)
    rows, t = [], dt.date(START_JAHR, 1, 1)
    # letzten Eingangstag weglassen: die Datei kann mitten am Tag geschnitten sein
    ende = dt.date.fromisoformat(letzte) - dt.timedelta(days=1)
    while t <= ende:
        if t.year in offen and t.isoformat() not in alle:
            break
        rows.append((t.isoformat(), alle.get(t.isoformat(), 0)))
        t += dt.timedelta(days=1)
    schreibe("anzahl_meldungen", rows)
    meta = {
        "anzahl_meldungen": {
            "einheit": "Anzahl Meldungen",
            "beschreibung": "Beim National Response Center der US-Kuestenwache eingegangene Vorfallmeldungen "
                            "(CALLTYPE INC: Freisetzung von Oel, Chemikalien, Gefahrgut; u.a. Pipelines, Raffinerien, "
                            "Schiffe, Bahn) je Eingangstag",
            "quelle_url": "https://nrc.uscg.mil/",
            "verdichtung": "Zaehlung der Meldungen je Datum von DATE_TIME_RECEIVED (Ortszeit Washington); "
                           "Tage ohne Meldung = 0; Reihe endet am Tag vor dem letzten Eingangstag der aktuellen Jahresdatei (dieser kann unvollstaendig sein)",
            "verfuegbar_nach_tagen": 8,
            "revidiert": False,
            "publikation": "woechentlich (die Jahresdatei CY<JJ>.xlsx des laufenden Jahres wird etwa einmal je "
                           "Woche ersetzt, Last-Modified 9.11.2026 mit Meldungen bis 8.11.2026; Quelle: "
                           "nrc.uscg.mil, Abschnitt FOIA Files)",
        }
    }
    with open(os.path.join(D, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2, sort_keys=True)
    print("ok", len(rows), "Tage,", sum(alle.values()), "Meldungen", ("; " + ", ".join(fehler)) if fehler else "")


if __name__ == "__main__":
    main()
