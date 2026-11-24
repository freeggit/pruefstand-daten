#!/usr/bin/env python3
"""Oslo Boers NewsWeb (Euronext Oslo): Anzahl Pflichtmeldungen je Tag in zwei Kategorien.

Quelle: oeffentliche JSON-Schnittstelle der Seite https://newsweb.oslobors.no (ohne Login, ohne Schluessel),
https://api3.oslo.oslobors.no/v1/newsreader/list?category=<id>&fromDate=..&toDate=..
Die Liste kommt absteigend nach publishedTime und ist auf rund 600 Meldungen je Anfrage begrenzt; darum wird
rueckwaerts geblaettert (toDate = aeltester Tag der letzten Antwort, Doppel ueber messageId entfernt).

Reihen (Datum = Tag der Veroeffentlichung in UTC, 0 an Tagen ohne Meldung, bis gestern UTC):
- primaerinsider_handel: Kategorie 1102 MANAGERS' TRANSACTION / MELDEPLIKTIG HANDEL FOR PRIMAERINNSIDERE
(Kategorie 1007 eigene Aktien geprueft 24.11.2026: erst ab 2017-02-15, K2 verfehlt, nicht abgelegt.)
Berichtigungen (correctionForMessageId != 0) und Testmeldungen werden nicht gezaehlt.
"""
import datetime
import gzip
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vorfassung  # noqa: E402

ID = "oslo_newsweb_meldungen"
BASE = "https://api3.oslo.oslobors.no/v1/newsreader/list"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
START = datetime.date(1990, 1, 1)
KAPPE = 600  # Antworten mit >= KAPPE Meldungen gelten als abgeschnitten
REIHEN = {
    "primaerinsider_handel": (1102, "MANAGERS' TRANSACTION (Meldepliktig handel for primaerinnsidere)"),
}
QUELLE = "https://newsweb.oslobors.no"


def hole(kat, von, bis, tries=4):
    q = urllib.parse.urlencode({"category": kat, "issuer": "", "fromDate": von.isoformat(),
                                "toDate": bis.isoformat(), "market": "", "messageTitle": ""})
    for i in range(tries):
        try:
            req = urllib.request.Request(BASE + "?" + q, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode("utf-8"))
            return d["data"]["messages"]
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) or i == tries - 1:
                raise
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError):
            if i == tries - 1:
                raise
        time.sleep(2 * (i + 1))


def sammle(kat, bis):
    seen = {}
    oben = bis
    while True:
        msgs = hole(kat, START, oben)
        for m in msgs:
            if m.get("test"):
                continue
            if kat not in [c.get("id") for c in m.get("category", [])]:
                raise RuntimeError("Meldung %s ohne Kategorie %s" % (m.get("messageId"), kat))
            seen[m["messageId"]] = m
        if len(msgs) < KAPPE:
            break
        tage = sorted(m["publishedTime"][:10] for m in msgs)
        neu_oben = datetime.date.fromisoformat(tage[0])
        if neu_oben >= oben:
            # ein einzelner Tag mit >= KAPPE Meldungen: nicht vollstaendig abrufbar
            raise RuntimeError("Tag %s mit mindestens %d Meldungen, Liste abgeschnitten" % (oben, KAPPE))
        oben = neu_oben
    return seen


def gzip_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for d, v in rows:
            t.write("%s,%d\n" % (d, v))
        t.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    heute = datetime.datetime.now(datetime.timezone.utc).date()
    gestern = heute - datetime.timedelta(days=1)
    meta = {}
    fertig = {}
    for reihe, (kat, name) in REIHEN.items():
        msgs = sammle(kat, gestern)
        zaehl = {}
        for m in msgs.values():
            if m.get("correctionForMessageId") not in (0, None):
                continue
            d = m["publishedTime"][:10]  # publishedTime ist UTC (Z)
            if d > gestern.isoformat():
                continue
            zaehl[d] = zaehl.get(d, 0) + 1
        if not zaehl:
            raise RuntimeError("keine Meldungen fuer %s" % reihe)
        erster = datetime.date.fromisoformat(min(zaehl))
        rows = []
        d = erster
        while d <= gestern:
            rows.append((d.isoformat(), zaehl.get(d.isoformat(), 0)))
            d += datetime.timedelta(days=1)
        vorfassung.pruefe(os.path.join(OUT_DIR, reihe + ".csv.gz"), rows, ID + ":" + reihe, art="ereignis")
        fertig[reihe] = rows
        meta[reihe] = {
            "einheit": "Anzahl Meldungen",
            "beschreibung": "Oslo Boers NewsWeb: Anzahl veroeffentlichter Pflichtmeldungen der Kategorie %s (Kat.-Nr. %d) "
                            "je Tag; Datum = Veroeffentlichungstag (publishedTime, UTC); Berichtigungen und Testmeldungen "
                            "nicht gezaehlt; 0 an Tagen ohne Meldung" % (name, kat),
            "quelle_url": QUELLE,
            "verdichtung": "Summe (Anzahl Meldungen je UTC-Kalendertag)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
            "publikation": "taeglich: Pflichtmeldungen erscheinen auf NewsWeb im Moment der Veroeffentlichung "
                           "(Oslo Boers ist Officially Appointed Mechanism nach Verdipapirhandelloven); Tageszahl am Abend bekannt",
            "hinweis_revision": "Kategorien vor Einfuehrung von MAR in Norwegen (2021) und vor 2016 wurden nachtraeglich "
                                "der heutigen Kategorienliste zugeordnet; die Zuordnung ist ein einmaliger Umbau, keine "
                                "Revision einzelner Werte. Geloeschte Meldungen waeren nicht sichtbar.",
        }
    for reihe, rows in fertig.items():
        gzip_write(os.path.join(OUT_DIR, reihe + ".csv.gz"), rows)
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    for reihe, rows in fertig.items():
        print(reihe, rows[0][0], rows[-1][0], len(rows), sum(v for _, v in rows))


if __name__ == "__main__":
    main()
