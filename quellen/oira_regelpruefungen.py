#!/usr/bin/env python3
"""OIRA (OMB): taegliche Anzahl abgeschlossener E.O.-12866-Pruefungen von Bundesregeln.

Mechanismus: Der Abschluss der OIRA-Pruefung ist das letzte Tor vor der Veroeffentlichung
einer Regel im Federal Register (meist Tage bis Wochen davor). Haeufungen abgeschlossener
Pruefungen kuendigen Regulierungsschuebe an; bei Umwelt- und Energiebehoerden (EPA, DOE,
Interior) betrifft das Energie und Versorger (XLE, XLU), bei HHS (FDA, CMS) Gesundheit (XLV).

Quelle: reginfo.gov XML-Jahresberichte EO_RULE_COMPLETED_<JJJJ>.xml, dazu _YTD und _30_DAYS
(oeffentlich, ohne Login und ohne Schluessel). Datum = DATE_COMPLETED (Abschlusstag).
Zaehlung ohne Entscheid «Withdrawn» (zurueckgezogene Regeln kommen nicht).
Beginn 2009-01-01: ab dann ist die taegliche oeffentliche Liste abgeschlossener Pruefungen
auf reginfo.gov belegt (End-of-Term-Archiv 2008/09); fruehere Abschluesse wurden nicht
nachweisbar am selben Tag bekanntgegeben, darum nicht abgelegt.
"""
import datetime
import gzip
import io
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET

ID = "oira_regelpruefungen"
BASE = "https://www.reginfo.gov/public/do/XMLViewFileAction?f=EO_RULE_COMPLETED_{}.xml"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
START = datetime.date(2009, 1, 1)

# Behoerdencodes (erste vier Ziffern der RIN): EPA 2040-2140 Bereich 20xx, DOE 19xx, Interior 10xx, HHS 09xx
def gruppe(code):
    if code.startswith("20") or code.startswith("19") or code.startswith("10"):
        return "energie_umwelt"
    if code.startswith("09"):
        return "gesundheit"
    return None


def fetch(tag):
    req = urllib.request.Request(BASE.format(tag), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse(raw):
    root = ET.fromstring(raw)
    rundate = root.get("RUNDATE", "")
    out = []
    for ra in root.findall("REGACT"):
        g = lambda t: (ra.findtext(t) or "").strip()
        dc = g("DATE_COMPLETED")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", dc):
            continue
        out.append((g("RIN"), g("DATE_RECEIVED"), dc, g("STAGE"), g("DECISION"), g("AGENCY_CODE")))
    return rundate, out


def write_series(name, counts, ende):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(b"datum,wert\n")
        d = START
        while d <= ende:
            gz.write(("%s,%d\n" % (d.isoformat(), counts.get(d.isoformat(), 0))).encode())
            d += datetime.timedelta(days=1)
    with open(os.path.join(OUT_DIR, name + ".csv.gz"), "wb") as f:
        f.write(buf.getvalue())


def main():
    heute = datetime.datetime.utcnow().date()
    tags = [str(y) for y in range(START.year, heute.year)] + ["YTD", "30_DAYS"]
    seen = set()
    rundates = []
    for t in tags:
        rundate, rows = parse(fetch(t))
        if t in ("YTD", "30_DAYS") and re.match(r"^\d{4}-\d{2}-\d{2}$", rundate):
            rundates.append(datetime.date.fromisoformat(rundate))
        for r in rows:
            seen.add(r)
    if not rundates:
        raise RuntimeError("kein RUNDATE im YTD/30-Tage-Bericht")
    # Stand: Vortag des Berichtsdatums (am Berichtstag selbst evtl. unvollstaendig)
    ende = max(rundates) - datetime.timedelta(days=1)
    reihen = {"anzahl": {}, "energie_umwelt": {}, "gesundheit": {}}
    for rin, rec, dc, stage, dec, code in seen:
        if dec.lower().startswith("withdrawn"):
            continue
        if dc < START.isoformat() or dc > ende.isoformat():
            continue
        reihen["anzahl"][dc] = reihen["anzahl"].get(dc, 0) + 1
        gr = gruppe(code or rin[:4])
        if gr:
            reihen[gr][dc] = reihen[gr].get(dc, 0) + 1
    os.makedirs(OUT_DIR, exist_ok=True)
    for n, c in reihen.items():
        write_series(n, c, ende)
    qurl = "https://www.reginfo.gov/public/do/XMLReportList"
    pub = ("taeglich (reginfo.gov fuehrt die Liste der in den letzten 30 Tagen abgeschlossenen "
           "E.O.-12866-Pruefungen mit taeglicher Aktualisierung; Abschlusstag dort am Folgetag sichtbar)")
    gemein = dict(einheit="Anzahl abgeschlossene Pruefungen", quelle_url=qurl,
                  verdichtung="Anzahl Pruefungen je Kalendertag des Abschlusses (DATE_COMPLETED), ohne Withdrawn, 0 an Tagen ohne Abschluss",
                  verfuegbar_nach_tagen=1, revidiert=False, publikation=pub)
    meta = {
        "anzahl": dict(gemein, beschreibung="Taegliche Anzahl abgeschlossener OIRA-Pruefungen (E.O. 12866) von Regeln aller Bundesbehoerden, alle Stufen (Prerule, Proposed, Final, Interim Final, Notice), ab 2009."),
        "energie_umwelt": dict(gemein, beschreibung="Wie anzahl, nur Behoerden EPA (RIN 20xx), Energieministerium DOE (19xx) und Innenministerium Interior (10xx)."),
        "gesundheit": dict(gemein, beschreibung="Wie anzahl, nur Gesundheitsministerium HHS (RIN 09xx, u.a. FDA und CMS)."),
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(ID, "ok", ende, {k: sum(v.values()) for k, v in reihen.items()})


if __name__ == "__main__":
    main()
