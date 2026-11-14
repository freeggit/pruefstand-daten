#!/usr/bin/env python3
"""Health Canada: Zulassungen (Notice of Compliance, NOC) je Tag, ab 1994.

Quelle: oeffentliche NOC-Datenbank-API von Health Canada (JSON, ohne Login, ohne Schluessel),
nur Standardbibliothek. Datum = noc_date = Tag, an dem Health Canada die Zulassung (NOC) erteilt;
Health Canada fuehrt die NOC-Datenbank laufend nach (beobachtet: NOC vom 13.11.2026 im Abruf vom
14.11.2026). Tierarzneimittel ausgeschlossen. Reihe = 0 an Tagen ohne Zulassung bis gestern (UTC).
Reihen:
  nas_zulassungen  = Erstzulassungen neuer Wirkstoffe (Klasse New Active Substance oder Priority-NAS)
  generika_zulassungen = Erstzulassungen von Generika (Abbreviated New Drug Submission,
                         ohne Admin-/Labelling-Only-Faelle)
"""
import datetime
import gzip
import io
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vorfassung  # noqa: E402

ID = "healthcanada_noc_zulassungen"
URL = "https://health-products.canada.ca/api/notice-of-compliance/noticeofcompliancemain/?lang=en&type=json"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def gzip_write(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("datum,wert\n" + "".join("%s,%d\n" % (d, v) for d, v in rows)).encode())
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    data = fetch()
    if len(data) < 30000:
        raise SystemExit("Abruffehler %s: nur %d Eintraege" % (ID, len(data)))
    zaehl = {"nas_zulassungen": {}, "generika_zulassungen": {}}
    for x in data:
        if x.get("noc_product_type") == "Veterinary" or x.get("noc_is_suppliment") != "N":
            continue
        try:
            d = datetime.date.fromisoformat(x.get("noc_date") or "")
        except ValueError:
            continue
        typ, kl = x.get("noc_on_submission_type", ""), x.get("noc_submission_class", "")
        if typ.startswith("New Drug Submission") and kl in ("New Active Substance", "Priority-NAS"):
            reihe = "nas_zulassungen"
        elif typ.startswith("Abbreviated New Drug") and kl in ("Other", "Priority"):
            reihe = "generika_zulassungen"
        else:
            continue
        zaehl[reihe][d] = zaehl[reihe].get(d, 0) + 1
    gestern = datetime.datetime.now(datetime.timezone.utc).date() - datetime.timedelta(days=1)
    os.makedirs(OUT_DIR, exist_ok=True)
    for reihe, cnt in zaehl.items():
        cnt = {d: v for d, v in cnt.items() if d <= gestern}
        if not cnt:
            raise SystemExit("Abruffehler %s: %s leer" % (ID, reihe))
        d, out = min(cnt), []
        while d <= gestern:
            out.append((d.isoformat(), cnt.get(d, 0)))
            d += datetime.timedelta(days=1)
        pfad = os.path.join(OUT_DIR, reihe + ".csv.gz")
        vorfassung.pruefe(pfad, out, ID + ":" + reihe)
        gzip_write(pfad, out)
    pub = ("taeglich: Health Canada traegt erteilte NOC laufend in die oeffentliche NOC-Datenbank ein "
           "(beobachtet: NOC vom 13.11.2026 im Abruf vom 14.11.2026); Firmen melden kanadische "
           "Zulassungen meist am Erteilungstag oder kurz danach")
    gemein = {"einheit": "Anzahl Zulassungen", "quelle_url": URL,
              "verdichtung": "Summe der Erstzulassungen (NOC, ohne Supplements, ohne Tierarzneimittel) je Kalendertag (noc_date)",
              "verfuegbar_nach_tagen": 2, "revidiert": False, "publikation": pub}
    meta = {
        "nas_zulassungen": dict(gemein, beschreibung="Taegliche Anzahl kanadischer Erstzulassungen neuer Wirkstoffe (Health Canada NOC, Klasse New Active Substance/Priority-NAS, Human inkl. Biologika); Datum = NOC-Erteilung"),
        "generika_zulassungen": dict(gemein, beschreibung="Taegliche Anzahl kanadischer Erstzulassungen von Generika (Health Canada NOC, Abbreviated New Drug Submission, ohne Admin/Labelling-Only); Datum = NOC-Erteilung"),
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
