#!/usr/bin/env python3
"""Consob (Italien): oeffentliche Netto-Leerverkaufspositionen (EU-Verordnung 236/2012), Tageszaehlung.

Eine Anfrage fuer die Seite, eine fuer die Datei PncPubbl.xlsx (Blaetter Correnti und Storiche).
Datum = Positionsdatum (Tag, an dem die Schwelle beruehrt wurde). Die Meldung an Consob ist bis 15:30 Uhr
des folgenden Handelstags faellig und wird dann veroeffentlicht (Art. 9 Abs. 2 SSR); darum
verfuegbar_nach_tagen 4 (deckt Freitag -> Montag und den taeglichen Aktualisierungsstand der Datei ab).
Reihen:
- meldungen: Anzahl oeffentlicher Meldungen je Positionsdatum (alle Schwellen 0,5 % und je 0,1 % darueber,
  inklusive Unterschreiten von 0,5 %).
- neue_positionen: Anzahl Meldungen, mit denen ein Halter (LEI) in einem Emittenten (ISIN) erstmals oder nach
  einem Unterschreiten von 0,5 % wieder die Schwelle 0,5 % erreicht.
0 an Kalendertagen ohne Meldung, vom ersten Positionsdatum bis zum letzten (hoechstens Publikationsdatum).
Nur Standardbibliothek.
"""
import datetime
import gzip
import io
import json
import os
import re
import sys
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vorfassung  # noqa: E402

ID = "consob_leerverkaeufe"
SEITE = "https://www.consob.it/web/area-pubblica/pnc"
BASIS = "https://www.consob.it"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
EXCEL_NULL = datetime.date(1899, 12, 30)


def hole(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(), r.headers.get("Content-Type", "")


def zellen(zeile, ss):
    out = {}
    for m in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>(.*?)</c>)', zeile, re.S):
        col, attr, inner = m.groups()
        v = re.search(r"<v>(.*?)</v>", inner or "", re.S)
        if v:
            v = v.group(1)
        elif inner:
            v = re.sub(r"<[^>]+>", "", inner)
        else:
            v = ""
        if 't="s"' in attr and v != "":
            v = ss[int(v)]
        out[col] = v.strip()
    return out


def gzip_write(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as g:
        g.write(b"datum,wert\n")
        for d, v in rows:
            g.write(("%s,%d\n" % (d, v)).encode())
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    html, _ = hole(SEITE)
    m = re.search(rb'href="(/documents/[^"]*PncPubbl\.xlsx[^"]*)"', html)
    if not m:
        raise SystemExit("Link PncPubbl.xlsx auf der Seite nicht gefunden")
    daten, ctype = hole(BASIS + m.group(1).decode())
    if not daten.startswith(b"PK"):
        raise SystemExit("Datei ist keine xlsx (Content-Type %s, %d Bytes), vermutlich Bot-Sperre" % (ctype, len(daten)))
    z = zipfile.ZipFile(io.BytesIO(daten))
    ss = [re.sub(r"<[^>]+>", "", s) for s in
          re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode("utf-8"), re.S)]
    ss = [s.replace("&amp;", "&") for s in ss]
    blaetter = re.findall(r'<sheet name="([^"]*)"[^>]*r:id="(rId\d+)"', z.read("xl/workbook.xml").decode())
    rels = {}
    rel_xml = z.read("xl/_rels/workbook.xml.rels").decode()
    for rel in re.findall(r"<Relationship [^>]*/>", rel_xml):
        rid = re.search(r'Id="([^"]+)"', rel).group(1)
        tgt = re.search(r'Target="([^"]+)"', rel).group(1)
        rels[rid] = tgt.lstrip("/").replace("xl/", "")

    meldungen = []  # (datum, lei_halter|name, isin, prozent)
    pub = None
    for name, rid in blaetter:
        xml = z.read("xl/" + rels[rid]).decode("utf-8")
        zeilen = re.findall(r"<row[^>]*>(.*?)</row>", xml, re.S)
        if "Pubb" in name:
            for zl in zeilen:
                c = zellen(zl, ss)
                t = c.get("A", "")
                if re.match(r"\d\d/\d\d/\d{4}$", t):
                    pub = datetime.datetime.strptime(t, "%d/%m/%Y").date()
            continue
        for zl in zeilen[2:]:
            c = zellen(zl, ss)
            try:
                d = EXCEL_NULL + datetime.timedelta(days=int(float(c["G"])))
                p = float(c["F"].replace(",", "."))
            except (KeyError, ValueError):
                continue
            halter = c.get("B") or c.get("A", "")
            meldungen.append((d, halter, c.get("E", ""), p, name))
    if len(meldungen) < 1000:
        raise SystemExit("zu wenige Meldungen (%d), Abruf unvollstaendig" % len(meldungen))
    if pub is None:
        raise SystemExit("Publikationsdatum nicht gefunden")

    # Doppel zwischen Correnti und Storiche entfernen (gleiche Meldung in beiden Blaettern)
    eindeutig = sorted(set((d, h, i, p) for d, h, i, p, _ in meldungen))
    zaehl = {}
    neu = {}
    letzte_p = {}
    for d, h, i, p in eindeutig:
        zaehl[d] = zaehl.get(d, 0) + 1
        vor = letzte_p.get((h, i))
        if p >= 0.5 and (vor is None or vor < 0.5):
            neu[d] = neu.get(d, 0) + 1
        letzte_p[(h, i)] = p

    erste = min(zaehl)
    letzte = min(max(zaehl), pub)
    r_meld, r_neu = [], []
    d = erste
    while d <= letzte:
        r_meld.append((d.isoformat(), zaehl.get(d, 0)))
        r_neu.append((d.isoformat(), neu.get(d, 0)))
        d += datetime.timedelta(days=1)

    os.makedirs(OUT_DIR, exist_ok=True)
    p_meld = os.path.join(OUT_DIR, "meldungen.csv.gz")
    p_neu = os.path.join(OUT_DIR, "neue_positionen.csv.gz")
    vorfassung.pruefe(p_meld, r_meld, ID + ":meldungen")
    vorfassung.pruefe(p_neu, r_neu, ID + ":neue_positionen")
    gzip_write(p_meld, r_meld)
    gzip_write(p_neu, r_neu)

    gemein = {
        "einheit": "Anzahl Meldungen",
        "quelle_url": SEITE,
        "verfuegbar_nach_tagen": 4,
        "publikation": "taeglich: Meldepflicht bis 15:30 Uhr des folgenden Handelstags nach Positionsdatum, "
                       "Consob veroeffentlicht die Meldungen danach in PncPubbl.xlsx (Art. 9 Abs. 2 VO (EU) 236/2012; "
                       "Blatt 'Pubb. Data' nennt den Stand); 4 Tage decken Wochenende und Aktualisierungsstand ab",
        "revidiert": "nein: Meldungen sind Einzelangaben mit Positionsdatum; neue Meldungen kommen hinzu, alte werden "
                     "nicht geaendert. Verspaetete Meldungen koennen einen vergangenen Tag nachtraeglich erhoehen.",
    }
    meta = {
        "meldungen": dict(gemein, beschreibung="Anzahl oeffentlicher Netto-Leerverkaufsmeldungen in italienischen Aktien "
                          "je Positionsdatum (Schwellen 0,5 % und je 0,1 % darueber sowie Unterschreiten von 0,5 %), "
                          "Blaetter Correnti und Storiche, Doppel entfernt",
                          verdichtung="Anzahl Meldungen je Kalendertag (Positionsdatum), 0 an Tagen ohne Meldung"),
        "neue_positionen": dict(gemein, beschreibung="Anzahl Meldungen, mit denen ein Halter in einer italienischen Aktie "
                                "erstmals oder nach Unterschreiten wieder 0,5 % netto leer verkauft ist",
                                verdichtung="Anzahl neuer Positionen je Kalendertag (Positionsdatum), 0 an Tagen ohne"),
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("%s: %d Meldungen, %s bis %s, Stand %s" % (ID, len(eindeutig), erste, letzte, pub))


if __name__ == "__main__":
    main()
