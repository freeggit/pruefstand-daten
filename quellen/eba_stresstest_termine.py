#!/usr/bin/env python3
"""EBA/CEBS: Veroeffentlichungstage der Ergebnisse der EU-weiten Bankenstresstests ab 2010.

Quelle: Jahresseiten der EBA zu den EU-weiten Stresstests (www.eba.europa.eu). Die Tage
sind als Liste hinterlegt; JEDER Tag wird bei jedem Abruf gegen den Wortlaut der
zugehoerigen EBA-Seite geprueft (Belegtext muss vorkommen), sonst bricht das Skript ab.
Die Veroeffentlichungstermine wurden von der EBA jeweils Wochen vorher angekuendigt
(z.B. 10.10.2014 fuer 26.10.2014, 21.7.2023 fuer 28.7.2023). Reihe = 1 am Tag der
Ergebnisveroeffentlichung, 0 sonst, fuer jeden Kalendertag ab 2010-01-01 bis heute.
Uhrzeiten (MEZ/MESZ): 2014 Sonntag, 2016 Freitag 22:00, 2023 und 2025 Freitag 18:00 -
also oft nach Handelsschluss Europa; die Wirkung faellt dann auf den naechsten Handelstag.
Neue Runden (alle zwei Jahre) muessen im Skript ergaenzt werden; die Seite der jeweils
laufenden Runde wird geprueft, ob ein neuer Ergebnistermin erscheint (dann Abbruch mit Hinweis).
"""
import datetime
import gzip
import html
import io
import json
import os
import re
import urllib.request

ID = "eba_stresstest_termine"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
B = "https://www.eba.europa.eu/"
RA = B + "risk-and-data-analysis/risk-analysis/"
TERMINE = [  # (Datum, Seite, Belegtext)
    ("2010-07-23", RA + "eu-wide-stress-testing/eu-wide-stress-testing-2010", "23/07/2010"),
    ("2011-07-15", RA + "eu-wide-stress-testing/eu-wide-stress-testing-2011", "on 15th July 2011"),
    ("2014-10-26", RA + "eu-wide-stress-testing/eu-wide-stress-testing-2014", "results on Sunday 26 October 2014"),
    ("2016-07-29", RA + "eu-wide-stress-testing/eu-wide-stress-testing-2016", "published on Friday 29 July 2016"),
    ("2018-11-02", RA + "eu-wide-stress-testing/eu-wide-stress-testing-2018", "02/11/2018"),
    ("2021-07-30", RA + "eu-wide-stress-testing/stress-tests-2021", "30 July 2021 EBA publishes the results"),
    ("2023-07-28", RA + "2025-eu-wide-stress-testing/stress-test-2023", "published on Friday, 28 July 2023"),
    ("2025-08-01", B + "eu-wide-stress-test-2025", "published on Friday, 1 August 2025"),
]
START = datetime.date(2010, 1, 1)


def text(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        s = r.read().decode("utf-8", "replace")
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)))


def write_gz(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(b"datum,wert\n")
        for d, v in rows:
            gz.write(("%s,%d\n" % (d.isoformat(), v)).encode())
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    cache, tage = {}, set()
    for d, url, beleg in TERMINE:
        if url not in cache:
            cache[url] = text(url)
        if beleg not in cache[url]:
            raise RuntimeError("Beleg fehlt fuer %s auf %s" % (d, url))
        tage.add(datetime.date.fromisoformat(d))
    # Uebersichtsseite: neue Runde mit angekuendigtem Ergebnistermin?
    t = text(RA + "eu-wide-stress-testing")
    for y in re.findall(r"(?:results?[^.]{0,80}published on [A-Za-z]+,? \d{1,2} [A-Z][a-z]+ (\d{4}))", t):
        if int(y) > 2025:
            raise RuntimeError("Neuer Ergebnistermin %s angekuendigt: Liste ergaenzen" % y)
    today = datetime.datetime.now(datetime.timezone.utc).date()
    rows, d = [], START
    while d <= today:
        rows.append((d, 1 if d in tage else 0))
        d += datetime.timedelta(days=1)
    os.makedirs(OUT_DIR, exist_ok=True)
    write_gz(os.path.join(OUT_DIR, "ergebnisse.csv.gz"), rows)
    meta = {"ergebnisse": {
        "einheit": "0/1 (1 = Veroeffentlichungstag)",
        "beschreibung": ("Tage, an denen EBA (2010: CEBS) die Ergebnisse des EU-weiten Bankenstresstests "
                         "veroeffentlichte; 1 am Tag, 0 sonst. Termin jeweils Wochen vorher angekuendigt. "
                         "Veroeffentlichung meist abends (18:00 bzw. 22:00 MESZ) oder am Sonntag (2014)."),
        "quelle_url": RA + "eu-wide-stress-testing",
        "verdichtung": "keine (Ereignistag)",
        "verfuegbar_nach_tagen": 0,
        "publikation": ("taeglich (Termin von der EBA vorab per Pressemitteilung angekuendigt, z.B. 21.7.2023 "
                        "fuer 28.7.2023; Beleg: EBA-Jahresseiten der Stresstests)"),
        "revidiert": False,
    }}
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("Termine", len(tage), "Zeilen", len(rows))


if __name__ == "__main__":
    main()
