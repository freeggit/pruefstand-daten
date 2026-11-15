#!/usr/bin/env python3
"""CFTC-Pressemitteilungen je Veroeffentlichungstag (ab 1995).

Quelle: https://www.cftc.gov/PressRoom/PressReleases (Drupal-Liste, Datum MM/DD/YYYY,
Freigabenummer). Zwei Reihen:
  vollzug  = Pressemitteilungen vom Typ «Enforcement» (Klagen, Vergleiche, Bussen)
  gesamt   = alle Pressemitteilungen
Jeder Kalendertag ab dem ersten Eintrag bis heute (UTC), 0 = keine Mitteilung.
Nur Standardbibliothek.
"""
import datetime as dt
import gzip
import io
import json
import os
import re
import time
import urllib.request

UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
BASE = "https://www.cftc.gov/PressRoom/PressReleases"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "neu", "cftc_pressemitteilungen")
ROW = re.compile(r"<tr.*?</tr>", re.S)
DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
LINK = re.compile(r'href="(/PressRoom/PressReleases/[^"]+)"')


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def sammeln(typ):
    seen = {}
    for page in range(0, 400):
        url = BASE + "?page=%d" % page
        if typ:
            url += "&field_press_release_types_value=" + typ
        h = get(url)
        neu = 0
        rows = ROW.findall(h)
        for r in rows:
            m = DATE.search(r)
            l = LINK.search(r)
            if not m or not l:
                continue
            d = dt.date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
            if l.group(1) not in seen:
                seen[l.group(1)] = d
                neu += 1
        if not rows or neu == 0 and page > 0 and not any(DATE.search(r) for r in rows):
            break
        if 'page=%d"' % (page + 1) not in h and "page=%d&" % (page + 1) not in h:
            break
        time.sleep(0.15)
    return seen


def schreiben(name, zaehl, heute):
    erste = min(zaehl)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        out = ["datum,wert"]
        t = erste
        while t <= heute:
            out.append("%s,%d" % (t.isoformat(), zaehl.get(t, 0)))
            t += dt.timedelta(days=1)
        gz.write(("\n".join(out) + "\n").encode())
    with open(os.path.join(OUT, name + ".csv.gz"), "wb") as f:
        f.write(buf.getvalue())


def main():
    heute = dt.datetime.now(dt.timezone.utc).date()
    os.makedirs(OUT, exist_ok=True)
    reihen = {"vollzug": "Enforcement", "gesamt": None}
    ergebnisse = {}
    for name, typ in reihen.items():
        seen = sammeln(typ)
        if len(seen) < 500:
            raise SystemExit("zu wenige Eintraege fuer %s: %d" % (name, len(seen)))
        z = {}
        for d in seen.values():
            if d <= heute:
                z[d] = z.get(d, 0) + 1
        ergebnisse[name] = z
    for name, z in ergebnisse.items():
        schreiben(name, z, heute)
    pub = ("taeglich (jede Mitteilung erscheint mit Datum auf cftc.gov/PressRoom/PressReleases; "
           "Datum = Veroeffentlichungstag laut Liste, US-Ostzeit)")
    meta = {
        "vollzug": {
            "einheit": "Anzahl Pressemitteilungen",
            "beschreibung": "CFTC-Pressemitteilungen vom Typ Enforcement (Klagen, Vergleiche, Bussen gegen Marktteilnehmer) je Veroeffentlichungstag",
            "quelle_url": BASE + "?field_press_release_types_value=Enforcement",
            "verdichtung": "Zaehlung der Mitteilungen je Kalendertag der Veroeffentlichung (US-Ostzeit); Tage ohne Mitteilung = 0",
            "verfuegbar_nach_tagen": 1,
            "publikation": pub,
            "revidiert": False,
        },
        "gesamt": {
            "einheit": "Anzahl Pressemitteilungen",
            "beschreibung": "Alle CFTC-Pressemitteilungen (Vollzug, Regeln, Personal, Marktaufsicht) je Veroeffentlichungstag",
            "quelle_url": BASE,
            "verdichtung": "Zaehlung der Mitteilungen je Kalendertag der Veroeffentlichung (US-Ostzeit); Tage ohne Mitteilung = 0",
            "verfuegbar_nach_tagen": 1,
            "publikation": pub,
            "revidiert": False,
        },
    }
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    for name, z in ergebnisse.items():
        print(name, len(z), min(z), max(z), sum(z.values()))


if __name__ == "__main__":
    main()
