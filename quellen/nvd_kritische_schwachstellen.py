#!/usr/bin/env python3
"""NIST National Vulnerability Database: neu veroeffentlichte Schwachstellen (CVE) je Tag.
Quelle: NVD-Jahresdateien https://nvd.nist.gov/feeds/json/cve/2.0/nvdcve-2.0-<JAHR>.json.gz
(gegliedert nach Jahr der CVE-Kennung, 2002 enthaelt 1999 bis 2002). Gezaehlt wird jeder Eintrag
nach seinem Feld «published» (Zeitpunkt der Erstveroeffentlichung in der NVD), einschliesslich
spaeter zurueckgezogener Eintraege (vulnStatus «Rejected»), damit kein spaeteres Wissen einfliesst.
Schweregrade (CVSS) werden NICHT verwendet: die NVD vergibt und aendert sie oft Wochen nach der
Veroeffentlichung, sie waeren nicht punktgenau (K4).
Reihe ab 2006-01-01 (Daten vor 2006 stammen aus der Uebernahme der Vorgaengerdatenbank ICAT bzw.
nachtraeglichen Sammelimporten, ihr Datum ist kein Veroeffentlichungstag der NVD), jeder Kalendertag bis gestern (UTC), 0 = keine Veroeffentlichung.
Reihe: anzahl_neu."""
import datetime as dt
import gzip
import io
import json
import os
import urllib.error
import urllib.request

ID = "nvd_kritische_schwachstellen"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
BASIS = "https://nvd.nist.gov/feeds/json/cve/2.0/nvdcve-2.0-%d.json.gz"
START = dt.date(2006, 1, 1)
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)


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


def hole(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise SystemExit("HTTP %d bei %s" % (e.code, url))


def main():
    os.makedirs(D, exist_ok=True)
    heute = dt.datetime.now(dt.timezone.utc).date()
    n, ids, weg = {}, set(), 0
    for jahr in range(2002, heute.year + 1):
        daten = json.loads(gzip.decompress(hole(BASIS % jahr)).decode("utf-8"))
        vul = daten.get("vulnerabilities")
        if not isinstance(vul, list) or (jahr < heute.year and len(vul) < 1000):
            raise SystemExit("unerwartetes Format %d" % jahr)
        for x in vul:
            c = x.get("cve", {})
            cid, p = c.get("id"), c.get("published", "")
            if not cid or cid in ids:
                continue
            ids.add(cid)
            try:
                d = dt.date.fromisoformat(p[:10])
            except ValueError:
                weg += 1
                continue
            n[d] = n.get(d, 0) + 1
        del daten, vul
    ende = heute - dt.timedelta(days=1)  # heutiger Tag noch unvollstaendig
    t = START
    rows = []
    while t <= ende:
        rows.append((t.isoformat(), n.get(t, 0)))
        t += dt.timedelta(days=1)
    schreibe("anzahl_neu", rows)
    meta = {
        "anzahl_neu": {
            "einheit": "Anzahl CVE-Eintraege",
            "beschreibung": "Neu in der NIST National Vulnerability Database veroeffentlichte Schwachstellen (CVE) "
                            "je Veroeffentlichungstag (Feld published), inklusive spaeter zurueckgezogener Eintraege; "
                            "ohne Schweregrad, da CVSS-Bewertungen nachtraeglich vergeben und geaendert werden",
            "quelle_url": "https://nvd.nist.gov/vuln/data-feeds",
            "verdichtung": "Zaehlung der CVE-Eintraege je Datum von published (Zeitstempel der NVD); "
                           "Kalendertage ohne Eintrag = 0; laufender Tag weggelassen; Beginn 2006-01-01, da fruehere Daten aus der Uebernahme der "
                           "Vorgaengerdatenbank stammen",
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
            "publikation": "taeglich (die NVD veroeffentlicht neue CVE laufend, Jahresdateien und API werden "
                           "stuendlich bis taeglich nachgefuehrt; Quelle: nvd.nist.gov/vuln/data-feeds); "
                           "1 Tag Puffer wegen Zeitzone des Zeitstempels",
        }
    }
    with open(os.path.join(D, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2, sort_keys=True)
    print("ok", len(ids), "CVE,", weg, "ohne Datum")


if __name__ == "__main__":
    main()
