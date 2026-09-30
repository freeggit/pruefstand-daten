#!/usr/bin/env python3
"""FEMA: taegliche Anzahl neuer Katastrophenerklaerungen (Disaster Declarations), ab 1953.

Mechanismus: Erklaerungen (v.a. Hurrikane, Ueberschwemmungen, Winterstuerme) markieren Sachschaeden und Ausfaelle
in Energie-, Raffinerie- und Versicherungsregionen und koennen Energie (XLE), Versorger (XLU) und Finanzwerte (XLF)
kurzfristig gegenueber dem Weltindex bewegen.
"""
import datetime
import gzip
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

ID = "fema_katastrophenerklaerungen"
BASE = "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
STORM = {"Hurricane", "Tropical Storm", "Typhoon", "Coastal Storm", "Severe Storm", "Severe Storm(s)", "Tornado", "Flood"}


def fetch_json(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
                continue
            raise


def gzip_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        text = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        text.write("datum,wert\n")
        for d, v in rows:
            text.write("%s,%s\n" % (d, v))
        text.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    seen = {}
    skip = 0
    while True:
        q = urllib.parse.urlencode([("$select", "disasterNumber,declarationDate,incidentType"),
                                    ("$orderby", "disasterNumber"), ("$top", "1000"), ("$skip", str(skip))])
        rows = fetch_json(BASE + "?" + q).get("DisasterDeclarationsSummaries", [])
        for r in rows:
            seen[r["disasterNumber"]] = (r["declarationDate"][:10], r.get("incidentType") or "")
        if len(rows) < 1000:
            break
        skip += 1000
    if len(seen) < 3000:
        raise RuntimeError("zu wenige Erklaerungen: %d" % len(seen))
    alle, sturm = {}, {}
    for d, t in seen.values():
        alle[d] = alle.get(d, 0) + 1
        if t in STORM:
            sturm[d] = sturm.get(d, 0) + 1
    first = datetime.date.fromisoformat(min(alle))
    last = datetime.date.fromisoformat(max(alle))
    ra, rs = [], []
    d = first
    while d <= last:
        iso = d.isoformat()
        ra.append((iso, alle.get(iso, 0)))
        rs.append((iso, sturm.get(iso, 0)))
        d += datetime.timedelta(days=1)
    gzip_write(os.path.join(OUT_DIR, "anzahl.csv.gz"), ra)
    gzip_write(os.path.join(OUT_DIR, "anzahl_stuerme.csv.gz"), rs)
    pub = ("taeglich (OpenFEMA-Datensatz wird taeglich aktualisiert; Erklaerungen werden am Erklaerungstag oeffentlich "
           "bekanntgegeben, Datensatz-Eintrag spaetestens am Folgetag). Nachtraegliche Aenderungen einzelner Zeilen moeglich.")
    common = {"einheit": "Anzahl Erklaerungen", "verdichtung": "Anzahl verschiedener disasterNumber je declarationDate; 0 an Tagen ohne Erklaerung",
              "quelle_url": "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries", "publikation": pub,
              "verfuegbar_nach_tagen": 1, "revidiert": False}
    meta = {"anzahl": dict(common, beschreibung="Neue FEMA-Katastrophenerklaerungen (Major Disaster, Emergency, Fire Management) je Erklaerungstag, ab 1953-05-02."),
            "anzahl_stuerme": dict(common, beschreibung="Davon Erklaerungen mit incidentType Hurricane, Tropical Storm, Typhoon, Coastal Storm, Severe Storm, Tornado oder Flood.")}
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
