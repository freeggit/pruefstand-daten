#!/usr/bin/env python3
"""DAX-Indexaenderungen je Wirksamkeitstag aus der Tabelle 'Zusammensetzungshistorie' im deutschen
Wikipedia-Artikel 'DAX' (Wikitext ueber Spezial:Exportieren). Jede Tabellenzeile = ein Paar
ausgeschieden/aufgenommen (bei der Erweiterung 2021 auch Zeilen nur mit Aufnahme)."""
import datetime
import gzip
import html
import io
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vorfassung  # noqa: E402

ID = "dax_indexaenderungen"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
EXPORT_URL = "https://de.wikipedia.org/wiki/Spezial:Exportieren/DAX"
ARTICLE_URL = "https://de.wikipedia.org/wiki/DAX#Zusammensetzungshistorie"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
BEGINN = datetime.date(1988, 7, 1)  # Einfuehrung des DAX
DATUM = re.compile(r"^\|\s*(?:rowspan=\"?\d+\"?\s*\|\s*)?(\d{2})\.(\d{2})\.(\d{4})\s*$")


def fetch():
    req = urllib.request.Request(EXPORT_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read().decode("utf-8")
    m = re.search(r"<text[^>]*>(.*)</text>", data, re.S)
    if not m:
        raise SystemExit("Abruffehler %s: kein Wikitext" % ID)
    return html.unescape(m.group(1))


def parse(wt):
    a = wt.find("=== Zusammensetzungshistorie ===")
    if a < 0:
        raise SystemExit("Abruffehler %s: Abschnitt Zusammensetzungshistorie fehlt" % ID)
    t0 = wt.find('{| class="wikitable', a)
    t1 = wt.find("\n|}", t0)
    tabelle = wt[t0:t1]
    counts = {}
    aktuell = None
    zeilen = 0
    for row in tabelle.split("\n|-")[1:]:
        lines = [ln.strip() for ln in row.split("\n") if ln.strip().startswith("|")]
        if not lines:
            continue
        m = DATUM.match(lines[0])
        if m:
            aktuell = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if aktuell is None:
            raise SystemExit("Abruffehler %s: Zeile ohne Datum vor erster Datumszeile" % ID)
        iso = aktuell.isoformat()
        counts[iso] = counts.get(iso, 0) + 1
        zeilen += 1
    return counts, zeilen


def gzip_write(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        tw = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        tw.write("datum,wert\n")
        for d, v in rows:
            tw.write("%s,%s\n" % (d, v))
        tw.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    counts, zeilen = parse(fetch())
    if zeilen < 70:
        raise SystemExit("Abruffehler %s: nur %d Tabellenzeilen geparst (erwartet >= 70)" % (ID, zeilen))
    heute = datetime.datetime.now(datetime.timezone.utc).date()
    if max(counts) > heute.isoformat():
        # angekuendigte, noch nicht wirksame Aenderung: keine Zeilen in der Zukunft
        counts = {k: v for k, v in counts.items() if k <= heute.isoformat()}
    rows = []
    d = BEGINN
    while d <= heute:
        rows.append((d.isoformat(), counts.get(d.isoformat(), 0)))
        d += datetime.timedelta(days=1)
    os.makedirs(OUT_DIR, exist_ok=True)
    pfad = os.path.join(OUT_DIR, "anzahl_aenderungen.csv.gz")
    vorfassung.pruefe(pfad, rows, ID + ":anzahl_aenderungen", "ereignis")
    gzip_write(pfad, rows)
    meta = {
        "anzahl_aenderungen": {
            "einheit": "Anzahl Indexaenderungen (Tabellenzeilen) je Tag",
            "beschreibung": (
                "Anzahl der Aenderungen der DAX-Zusammensetzung (Paar ausgeschieden/aufgenommen; bei der "
                "Erweiterung auf 40 Werte am 20.09.2021 je Aufnahme eine Zeile) je Wirksamkeitstag, gezaehlt aus "
                "der Tabelle 'Zusammensetzungshistorie' des deutschen Wikipedia-Artikels DAX, die das Dokument "
                "'Historical Index Compositions' der Deutschen Boerse/STOXX nachfuehrt. Reihe beginnt mit der "
                "Einfuehrung des DAX am 1.7.1988 (erste Aenderung 3.9.1990); 0 an Tagen ohne Aenderung. "
                "Community-gepflegte Abschrift: Korrekturen von Abschreibfehlern moeglich, die Ereignisse selbst "
                "werden nicht revidiert."
            ),
            "quelle_url": ARTICLE_URL,
            "verdichtung": "Anzahl Tabellenzeilen je Kalendertag (Wirksamkeitstag), 0 an Tagen ohne Eintrag",
            "publikation": (
                "taeglich (im Voraus bekannt): Deutsche Boerse/STOXX kuendigt Aenderungen vor der Wirksamkeit an "
                "(regulaere Ueberpruefung rund zweieinhalb Wochen vorher, ausserordentliche Aenderungen mit "
                "mindestens zwei Handelstagen Vorlauf; Beleg: Guide to the DAX Equity Indices, Abschnitt "
                "Index-Anpassungen); der Wikipedia-Eintrag folgt meist am Wirksamkeitstag"
            ),
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
