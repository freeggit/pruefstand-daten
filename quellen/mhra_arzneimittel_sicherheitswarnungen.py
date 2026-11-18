#!/usr/bin/env python3
"""MHRA (UK Medicines and Healthcare products Regulatory Agency): Arzneimittel-Rueckrufe und
Geraete-Sicherheitswarnungen je Tag der Herausgabe.
Quelle: GOV.UK Search API (offen, ohne Schluessel), Dokumenttyp medical_safety_alert
(Finder https://www.gov.uk/drug-device-alerts). Datum = Metadatenfeld issued_date (Tag der
Herausgabe, auf GOV.UK in Stichproben gleich first_published_at; public_timestamp ist die letzte
Aenderung und wird darum NICHT verwendet).
Reihen:
  arzneimittel_rueckrufe: alert_type medicines-recall-notification (Rueckrufe Klasse 1-4 je Charge/Hersteller)
  geraete_warnungen: alert_type device-safety-information und national-patient-safety (MHRA-eigene Warnungen)
Nicht gezaehlt: field-safety-notices (woechentliche Sammellisten von Herstellermeldungen) und
mhra-safety-round-up (monatliche Zusammenfassung), weil sie Sammelpublikationen sind.
Reihe ab 2015-01-01 (vorher unvollstaendig nach GOV.UK migriert), jeder Kalendertag bis heute (UTC),
0 = keine Meldung."""
import datetime as dt
import gzip
import io
import json
import os
import urllib.error
import urllib.request

ID = "mhra_arzneimittel_sicherheitswarnungen"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
BASE = ("https://www.gov.uk/api/search.json?filter_content_store_document_type=medical_safety_alert"
        "&count=1000&start=%d&fields=issued_date,alert_type&order=public_timestamp")
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
START = dt.date(2015, 1, 1)
REIHEN = {
    "arzneimittel_rueckrufe": {"medicines-recall-notification"},
    "geraete_warnungen": {"device-safety-information", "national-patient-safety"},
}


def hole(start):
    req = urllib.request.Request(BASE % start, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit("HTTP %d" % e.code)


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
    ergebnisse, start, total = [], 0, None
    while total is None or start < total:
        d = hole(start)
        total = d["total"]
        if not d["results"]:
            break
        ergebnisse += d["results"]
        start += len(d["results"])
        if start > 20000:
            break
    ids = set()
    zaehl = {n: {} for n in REIHEN}
    for x in ergebnisse:
        if x["_id"] in ids:
            continue
        ids.add(x["_id"])
        i = x.get("issued_date")
        if not i:
            continue
        try:
            tag = dt.date.fromisoformat(i[:10])
        except ValueError:
            continue
        typen = set(x.get("alert_type") or [])
        for n, t in REIHEN.items():
            if typen & t:
                zaehl[n][tag] = zaehl[n].get(tag, 0) + 1
    if len(ids) < 1000:
        raise SystemExit("zu wenige Meldungen: %d" % len(ids))
    heute = dt.datetime.now(dt.timezone.utc).date()
    for n in REIHEN:
        rows, t = [], START
        while t <= heute:
            rows.append((t.isoformat(), zaehl[n].get(t, 0)))
            t += dt.timedelta(days=1)
        schreibe(n, rows)
    pub = ("taeglich: MHRA gibt Warnungen und Rueckrufe einzeln am Herausgabetag auf GOV.UK heraus "
           "(gov.uk/drug-device-alerts, issued_date); in Stichproben 2015-2025 war first_published_at "
           "meist gleich issued_date, einzeln bis 4 Tage spaeter, darum konservativ 1 Tag")
    meta = {
        "arzneimittel_rueckrufe": {
            "einheit": "Anzahl Meldungen",
            "beschreibung": "Taegliche Anzahl MHRA-Arzneimittelrueckrufe (Medicines Recall Notification, Klasse 1-4) nach Herausgabetag; 0 an Tagen ohne Meldung; ab 2015.",
        },
        "geraete_warnungen": {
            "einheit": "Anzahl Meldungen",
            "beschreibung": "Taegliche Anzahl MHRA-Sicherheitswarnungen zu Medizinprodukten (Device Safety Information, National Patient Safety Alert) nach Herausgabetag; ohne woechentliche Field-Safety-Notice-Sammellisten; 0 an Tagen ohne Meldung; ab 2015.",
        },
    }
    for n in meta:
        meta[n].update({
            "quelle_url": "https://www.gov.uk/drug-device-alerts",
            "verdichtung": "Zaehlung der Meldungen je Kalendertag (issued_date, UK-Ortszeit)",
            "verfuegbar_nach_tagen": 1,
            "publikation": pub,
            "revidiert": False,
            "status": "aktiv" if n == "arzneimittel_rueckrufe" else "ruhend",
        })
    with open(os.path.join(D, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
