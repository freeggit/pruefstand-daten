#!/usr/bin/env python3
"""WTO-Streitbeilegung: Anzahl neuer Konsultationsgesuche (Faelle DS1 ff.) je Kalendertag.

Mechanismus: ein neues Konsultationsgesuch eroeffnet einen Handelsstreit und aendert
kurzfristig die Zollerwartungen fuer Exportlaender und -branchen (FXI, EWJ, EWG, EEM,
Stahl/Agrar), gegenueber dem Weltindex (1 bis 20 Handelstage).

Quelle: je Fall die Seite https://www.wto.org/english/tratop_e/dispu_e/cases_e/ds<N>_e.htm,
Abschnitt «Summary of the dispute to date» / «Consultations»: das erste Datum dort ist der
Tag des Konsultationsgesuchs des (ersten) Klaegers. Ein Fall = ein Ereignis; spaetere
Beitritte weiterer Klaeger zum selben Fall werden nicht gezaehlt.

Zwischenspeicher data/neu/<id>/faelle.json: Fallnummer -> Datum. Bereits bekannte Faelle
werden nicht erneut geholt (das Datum des Gesuchs aendert sich nicht); gesucht wird nur
ab der hoechsten bekannten Nummer weiter, bis 8 Nummern in Folge nicht existieren.
"""
import datetime
import gzip
import html
import io
import json
import os
import re
import time
import urllib.error
import urllib.request

ID = "wto_streitfaelle_konsultationen"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
URL = "https://www.wto.org/english/tratop_e/dispu_e/cases_e/ds%d_e.htm"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
CACHE = os.path.join(OUT, "faelle.json")
START = datetime.date(1995, 1, 1)
MONATE = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"])}
DAT_RE = re.compile(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
                    r"September|October|November|December)\s+(\d{4})")
ZEITBUDGET_S = 160


class NichtGefunden(Exception):
    pass


class KeinRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if "error_404" in newurl:
            raise NichtGefunden(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(KeinRedirect)


def hole(n):
    req = urllib.request.Request(URL % n, headers={"User-Agent": UA})
    try:
        with OPENER.open(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise NichtGefunden(str(n))
        raise


def datum_aus(seite):
    t = html.unescape(re.sub(r"<[^>]+>", " ", seite))
    t = re.sub(r"\s+", " ", t)
    i = t.find("Summary of the dispute to date")
    if i < 0:
        return None
    j = t.find("Consultations", i)
    if j < 0:
        return None
    # erstes Datum ab 1.1.1995 (WTO-Gruendung); fruehere Daten im Text sind Verweise auf Massnahmen
    for m in DAT_RE.finditer(t, j, j + 800):
        d = datetime.date(int(m.group(3)), MONATE[m.group(2).lower()], int(m.group(1)))
        if d >= START:
            return d.isoformat()
    return None


def main():
    os.makedirs(OUT, exist_ok=True)
    faelle = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            faelle = json.load(f)
    t0 = time.time()
    n = 1
    fehlend = 0
    ohne_datum = []
    while fehlend < 8:
        if time.time() - t0 > ZEITBUDGET_S:
            raise RuntimeError("Zeitbudget erschoepft bei DS%d; naechster Lauf setzt fort" % n)
        key = str(n)
        if key in faelle:
            fehlend = 0
            n += 1
            continue
        try:
            seite = hole(n)
            fehlend = 0
            d = datum_aus(seite)
            if d:
                faelle[key] = d
            else:
                ohne_datum.append(n)
        except NichtGefunden:
            fehlend += 1
        time.sleep(0.15)
        n += 1
        if len(faelle) % 50 == 0:
            with open(CACHE, "w", encoding="utf-8") as f:
                json.dump(faelle, f, sort_keys=True, indent=0)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(faelle.items(), key=lambda kv: int(kv[0]))), f, indent=0)
    if ohne_datum:
        print("ohne Datum (Seite ohne Konsultationsabschnitt, nicht gezaehlt):", ohne_datum)

    heute = datetime.datetime.now(datetime.timezone.utc).date()
    zaehl = {}
    for d in faelle.values():
        zaehl[d] = zaehl.get(d, 0) + 1
    buf = io.StringIO()
    buf.write("datum,wert\n")
    tag = START
    while tag <= heute:
        buf.write("%s,%d\n" % (tag.isoformat(), zaehl.get(tag.isoformat(), 0)))
        tag += datetime.timedelta(days=1)
    with open(os.path.join(OUT, "konsultationen.csv.gz"), "wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as g:
            g.write(buf.getvalue().encode("utf-8"))
    meta = {"konsultationen": {
        "einheit": "Anzahl neue Streitfaelle",
        "beschreibung": "Anzahl neuer WTO-Streitfaelle (Konsultationsgesuche DS1 ff.) je Tag des Gesuchs des ersten Klaegers, 0 an Tagen ohne Gesuch; Datum aus der Fallseite der WTO.",
        "quelle_url": "https://www.wto.org/english/tratop_e/dispu_e/dispu_status_e.htm",
        "verdichtung": "Anzahl Faelle je Kalendertag (Datum des Konsultationsgesuchs)",
        "verfuegbar_nach_tagen": 5,
        "publikation": "verzoegert: das Gesuch wird von der WTO als WT/DS-Dokument und Fallseite meist wenige Tage nach dem Gesuchsdatum veroeffentlicht (Regel Art. 4.4 DSU: Notifikation an das DSB); konservativ 5 Tage.",
        "revidiert": False,
    }}
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("Faelle:", len(faelle), "letzte Nummer:", max(int(k) for k in faelle))


if __name__ == "__main__":
    main()
