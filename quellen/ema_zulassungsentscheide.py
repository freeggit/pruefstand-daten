#!/usr/bin/env python3
"""EMA: EU-Zulassungen (Kommissionsentscheid) neuer Humanarzneimittel und Biosimilars je Tag.

Quelle: EMA-Gesamtbericht «Medicines output» (xlsx, taeglich neu erzeugt), nur Standardbibliothek
(zipfile + xml). Datum = «Marketing authorisation date» = Tag des Zulassungsentscheids der
EU-Kommission (oeffentliche Bekanntgabe ueber Union Register / EMA-EPAR, Firmenmitteilungen meist
am selben Tag). Zurueckgezogene, erloschene und widerrufene Zulassungen bleiben im Bericht mit
ihrem urspruenglichen Datum (kein Survivorship-Verlust); Reihe = 0 an Tagen ohne Entscheid bis zum
Erzeugungstag des Berichts.
"""
import datetime
import gzip
import io
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vorfassung  # noqa: E402

ID = "ema_zulassungsentscheide"
URL = "https://www.ema.europa.eu/en/documents/report/medicines-output-medicines-report_en.xlsx"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def lese(raw):
    z = zipfile.ZipFile(io.BytesIO(raw))
    ss = [''.join(t.text or '' for t in si.iter(M + 't'))
          for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall(M + 'si')]
    rows = []
    for r in ET.fromstring(z.read('xl/worksheets/sheet1.xml')).iter(M + 'row'):
        d = {}
        for c in r.findall(M + 'c'):
            v = c.find(M + 'v')
            x = v.text if v is not None else ''.join(t.text or '' for t in c.iter(M + 't'))
            if c.get('t') == 's':
                x = ss[int(x)]
            d[re.sub(r'\d', '', c.get('r'))] = (x or '').strip()
        rows.append(d)
    return rows


def datum(s):
    m = re.fullmatch(r'(\d{2})/(\d{2})/(\d{4})', s or '')
    if not m:
        return None
    return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))


def gzip_write(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("datum,wert\n" + "".join("%s,%d\n" % (d, v) for d, v in rows)).encode())
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    rows = lese(fetch())
    # Kopfzeile suchen und Spalten nach Namen zuordnen (robust gegen Spaltenumstellungen)
    hi = next(i for i, r in enumerate(rows) if r.get('A') == 'Category')
    col = {v: k for k, v in rows[hi].items() if v}
    def c(name):
        k = next((k for n, k in col.items() if n.replace('\n', ' ').startswith(name)), None)
        if k is None:
            raise SystemExit("Abruffehler %s: Spalte '%s' fehlt" % (ID, name))
        return k
    kat, gen, bio, mad = c('Category'), c('Generic'), c('Biosimilar'), c('Marketing authorisation date')
    gm = re.search(r'(\d{2}/\d{2}/\d{4})', rows[0].get('D', '') + ' ' + ' '.join(rows[0].values()))
    erzeugt = datum(gm.group(1)) if gm else None
    data = [r for r in rows[hi + 1:] if r.get(kat)]
    if len(data) < 2000:
        raise SystemExit("Abruffehler %s: nur %d Zeilen im Bericht" % (ID, len(data)))
    zaehl = {"zulassungen_neu": {}, "zulassungen_biosimilar": {}}
    for r in data:
        if r.get(kat) != 'Human':
            continue
        d = datum(r.get(mad))
        if d is None:
            continue
        if r.get(bio) == 'Yes':
            reihe = "zulassungen_biosimilar"
        elif r.get(gen) == 'No':
            reihe = "zulassungen_neu"
        else:
            continue
        zaehl[reihe][d] = zaehl[reihe].get(d, 0) + 1
    heute = datetime.datetime.now(datetime.timezone.utc).date()
    ende = min(erzeugt or heute, heute)
    os.makedirs(OUT_DIR, exist_ok=True)
    for reihe, cnt in zaehl.items():
        if not cnt:
            raise SystemExit("Abruffehler %s: %s leer" % (ID, reihe))
        e = max(ende, max(cnt))
        d = min(cnt)
        out = []
        while d <= e:
            out.append((d.isoformat(), cnt.get(d, 0)))
            d += datetime.timedelta(days=1)
        pfad = os.path.join(OUT_DIR, reihe + ".csv.gz")
        vorfassung.pruefe(pfad, out, ID + ":" + reihe)
        gzip_write(pfad, out)
    pub = ("taeglich: EU-Kommissionsentscheide werden im Union Register of medicinal products "
           "veroeffentlicht und von der EMA im EPAR/Medicines-Bericht (taeglich neu erzeugt, beobachtet "
           "Entscheid 12.11.2026 im Bericht vom 13.11.2026) nachgefuehrt; Firmenmitteilungen meist am Entscheidtag")
    gemein = {"einheit": "Anzahl Zulassungen", "quelle_url": URL,
              "verdichtung": "Summe der Erstzulassungen je Kalendertag (Marketing authorisation date)",
              "verfuegbar_nach_tagen": 2, "revidiert": False, "publikation": pub}
    meta = {
        "zulassungen_neu": dict(gemein, beschreibung=(
            "Taegliche Anzahl zentraler EU-Erstzulassungen von Humanarzneimitteln ohne Generika und "
            "Biosimilars (EMA, Datum = Zulassungsentscheid der EU-Kommission); inkl. spaeter "
            "zurueckgezogener Zulassungen")),
        "zulassungen_biosimilar": dict(gemein, beschreibung=(
            "Taegliche Anzahl zentraler EU-Erstzulassungen von Biosimilars (EMA, Datum = "
            "Zulassungsentscheid der EU-Kommission); Wettbewerbsdruck auf Biologika-Hersteller")),
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
