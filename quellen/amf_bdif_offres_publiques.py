#!/usr/bin/env python3
"""AMF Frankreich, Datenbank BDIF: Dokumente zu oeffentlichen Angeboten (OPA) je Tag.

Reihen:
  dokumente             Anzahl auf BDIF aufgeschalteter Dokumente der Rubrik
                        «Offres publiques» (typesInformation=OPA: Angebotseinreichung,
                        Entscheide, Kalender, Resultate, Kauf-/Verkaufsmeldungen
                        waehrend der Angebotsfrist) je Kalendertag
  angebote_eingereicht  Anzahl Dokumente vom Typ «DepotOffre» (Einreichung eines
                        oeffentlichen Angebots bei der AMF) je Kalendertag

Datum = dateMiseEnLigne (Tag der Aufschaltung auf der AMF-Seite). Die Datenbank
wurde 2021/22 migriert; das Feld behaelt das urspruengliche Aufschaltdatum
(datePublication zeigt das Migrationsdatum und wird nicht verwendet).
Beginn 2008-01-01: davor nur Bruchstuecke (1997: 13 Dokumente, 1998-2007 keine).
0 an Tagen ohne Dokument; letzter Tag = gestern (UTC).
Offene JSON-Schnittstelle der BDIF-Webseite, ohne Login, ohne Schluessel.
"""
import calendar
import concurrent.futures
import datetime
import gzip
import io
import json
import os
import time
import urllib.error
import urllib.request

ID = "amf_bdif_offres_publiques"
API = "https://bdif.amf-france.org/back/api/v1/informations"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
START = datetime.date(2008, 1, 1)
SIZE = 1000
WORKERS = 4


def fetch_json(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise
            last = e
        except Exception as e:  # noqa
            last = e
        time.sleep(2 * (i + 1))
    raise last


def gzip_write(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for d, v in rows:
            t.write("%s,%s\n" % (d, v))
        t.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def month_docs(y, m):
    a = "%04d-%02d-01" % (y, m)
    b = "%04d-%02d-%02d" % (y, m, calendar.monthrange(y, m)[1])
    out, start, total = [], 0, None
    while True:
        url = "%s?typesInformation=OPA&size=%d&from=%d&dateDebut=%s&dateFin=%s" % (API, SIZE, start, a, b)
        d = fetch_json(url)
        total = d["total"]
        res = d["result"]
        out.extend(res)
        start += len(res)
        if not res or start >= total:
            break
    if total >= 10000:
        raise RuntimeError("Monat %s: Trefferlimit 10000 erreicht" % a)
    if len(out) != total:
        raise RuntimeError("Monat %s: %d statt %d Dokumente" % (a, len(out), total))
    return (y, m), out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    today = datetime.datetime.now(datetime.timezone.utc).date()
    last = today - datetime.timedelta(days=1)
    months = []
    y, m = START.year, START.month
    while (y, m) <= (last.year, last.month):
        months.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    seen = {}
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as ex:
        for (ym, docs) in ex.map(lambda t: month_docs(*t), months):
            for x in docs:
                d = (x.get("dateMiseEnLigne") or x.get("dateInformation") or "")[:10]
                if not d:
                    continue
                seen[x["id"]] = (d, x.get("typesDocument") or [])
    dok, dep = {}, {}
    for d, types in seen.values():
        dok[d] = dok.get(d, 0) + 1
        if "DepotOffre" in types:
            dep[d] = dep.get(d, 0) + 1
    if len(seen) < 5000:
        raise RuntimeError("zu wenige Dokumente: %d" % len(seen))
    days = []
    cur = START
    while cur <= last:
        days.append(cur.isoformat())
        cur += datetime.timedelta(days=1)
    gzip_write(os.path.join(OUT_DIR, "dokumente.csv.gz"), [(d, dok.get(d, 0)) for d in days])
    gzip_write(os.path.join(OUT_DIR, "angebote_eingereicht.csv.gz"), [(d, dep.get(d, 0)) for d in days])
    pub = ("taeglich: die AMF schaltet Angebotsdokumente (Depot, Avis, Decisions de conformite, "
           "Declarations des achats et ventes) am Tag der Veroeffentlichung in BDIF auf "
           "(Reglement general AMF, Art. 231-14 ff. und 231-46); Tageszaehlung erst am Folgetag vollstaendig, darum 1 Tag")
    meta = {
        "dokumente": {
            "einheit": "Anzahl Dokumente",
            "beschreibung": "AMF BDIF Frankreich: Anzahl aufgeschalteter Dokumente zu oeffentlichen Angeboten (OPA, OPR, OPAS u.a.) je Tag",
            "quelle_url": "https://bdif.amf-france.org/fr?typesInformation=OPA",
            "verdichtung": "Anzahl Dokumente je Kalendertag (Datum = dateMiseEnLigne), 0 an Tagen ohne Dokument",
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
            "publikation": pub,
        },
        "angebote_eingereicht": {
            "einheit": "Anzahl Dokumente",
            "beschreibung": "AMF BDIF Frankreich: Anzahl Einreichungen oeffentlicher Angebote (typesDocument DepotOffre) je Tag",
            "quelle_url": "https://bdif.amf-france.org/fr?typesInformation=OPA",
            "verdichtung": "Anzahl Dokumente vom Typ DepotOffre je Kalendertag (Datum = dateMiseEnLigne), 0 an Tagen ohne Dokument",
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
            "publikation": pub,
        },
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("%s: %d Dokumente, %d DepotOffre, %d Tage" % (ID, len(seen), sum(dep.values()), len(days)))


if __name__ == "__main__":
    main()
