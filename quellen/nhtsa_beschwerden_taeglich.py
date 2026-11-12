#!/usr/bin/env python3
"""NHTSA ODI Verbraucherbeschwerden je Tag.

Quelle: https://static.nhtsa.gov/odi/ffdd/cmpl/FLAT_CMPL.zip (tabgetrennt, taeglich neu).
Datum = DATEA (Feld 16, Tag der Aufnahme in die oeffentliche Datei), nicht Eingangs-
oder Schadensdatum, damit nichts vorweggenommen wird. Tageszaehlung, 0 an Tagen ohne
Aufnahme, vom ersten DATEA bis zum letzten DATEA der Datei (keine Tage danach).
"""
import datetime
import gzip
import io
import json
import os
import tempfile
import urllib.request
import zipfile

ID = "nhtsa_beschwerden_taeglich"
URL = "https://static.nhtsa.gov/odi/ffdd/cmpl/FLAT_CMPL.zip"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)


def write(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(b"datum,wert\n")
        for d, v in rows:
            gz.write(("%s,%d\n" % (d, v)).encode())
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    os.makedirs(OUT, exist_ok=True)
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with tempfile.TemporaryFile() as tmp:
        with urllib.request.urlopen(req, timeout=30) as r:
            while True:
                b = r.read(1 << 22)
                if not b:
                    break
                tmp.write(b)
        tmp.seek(0)
        ges, schwer = {}, {}
        with zipfile.ZipFile(tmp) as z:
            name = z.namelist()[0]
            with z.open(name) as f:
                for line in f:
                    p = line.split(b"\t", 17)
                    if len(p) < 17:
                        continue
                    d = p[15]
                    if len(d) != 8 or not d.isdigit():
                        continue
                    ges[d] = ges.get(d, 0) + 1
                    s = (p[6] == b"Y" or p[8] == b"Y"
                         or p[9].strip() not in (b"", b"0")
                         or p[10].strip() not in (b"", b"0"))
                    if s:
                        schwer[d] = schwer.get(d, 0) + 1
    keys = sorted(ges)
    today = datetime.datetime.utcnow().date()
    d0 = datetime.date(int(keys[0][:4]), int(keys[0][4:6]), int(keys[0][6:]))
    d1 = datetime.date(int(keys[-1][:4]), int(keys[-1][4:6]), int(keys[-1][6:]))
    d1 = min(d1, today)
    r_g, r_s = [], []
    d = d0
    while d <= d1:
        k = d.strftime("%Y%m%d").encode()
        r_g.append((d.isoformat(), ges.get(k, 0)))
        r_s.append((d.isoformat(), schwer.get(k, 0)))
        d += datetime.timedelta(days=1)
    write(os.path.join(OUT, "anzahl_gesamt.csv.gz"), r_g)
    write(os.path.join(OUT, "anzahl_schwer.csv.gz"), r_s)
    pub = ("taeglich: NHTSA erneuert FLAT_CMPL.zip taeglich (Last-Modified der Datei); "
           "Datum ist DATEA = Aufnahme in die oeffentliche Beschwerdedatenbank; Datei vom 12.11.2026 endete mit DATEA 9.11., darum 3 Tage")
    common = {"einheit": "Anzahl Beschwerden je Tag", "quelle_url": URL,
              "verdichtung": "Summe je Kalendertag (DATEA), 0 an Tagen ohne Aufnahme",
              "verfuegbar_nach_tagen": 3, "revidiert": False, "publikation": pub,
              "status": "aktiv"}
    meta = {
        "anzahl_gesamt": dict(common, beschreibung="Neu in die NHTSA-ODI-Datenbank aufgenommene Verbraucherbeschwerden zu Fahrzeugen und Ausruestung je Tag (alle Hersteller)."),
        "anzahl_schwer": dict(common, beschreibung="Davon Beschwerden mit Unfall, Brand, Verletzten oder Toten (Felder CRASH, FIRE, INJURED, DEATHS)."),
    }
    with open(os.path.join(OUT, "meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(ID, len(r_g), r_g[0][0], r_g[-1][0])


if __name__ == "__main__":
    main()
