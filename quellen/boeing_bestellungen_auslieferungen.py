#!/usr/bin/env python3
"""Boeing: Veroeffentlichungstage der Quartals-Auslieferungszahlen (Pressemitteilung) ab 1997.

Quelle: Boeing-Newsroom boeing.mediaroom.com. Die URL jeder Pressemitteilung beginnt mit dem
Veroeffentlichungsdatum (JJJJ-MM-TT). Erfasst werden Mitteilungen, deren Titel
'Reports'/'Announces' und 'Deliveries' sowie 'Quarter', 'Annual', 'Full-Year' oder
'Orders-and-Deliveries' enthaelt (Quartals-/Jahreszahlen der Auslieferungen), ohne
Quartalsergebnisse ('Results'). Zwei Wege: (1) die chronologische Liste ab neuestem Eintrag
bis vor 2013 (je 3 Seiten parallel), (2) die Stichwortsuche 'quarter deliveries' fuer die aeltere Zeit. Reihe = 1
am Veroeffentlichungstag, 0 sonst, fuer jeden Kalendertag ab dem ersten Treffer bis heute.
Keine Termine geschaetzt oder ergaenzt: fehlt eine Mitteilung im Newsroom, fehlt der Tag.
"""
import datetime
import gzip
import io
import json
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ID = "boeing_bestellungen_auslieferungen"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
BASE = "https://boeing.mediaroom.com/news-releases-statements?l=100&o=%d"
SEARCH = "https://boeing.mediaroom.com/news-releases-statements?keywords=quarter+deliveries&l=100&o=%d"
LINK = re.compile(r'href="https://boeing\.mediaroom\.com/(\d{4})-(\d{2})-(\d{2})-([^"?#]+)"')
DATE = re.compile(r'<div class="wd_date">\s*([A-Z][a-z]{2})[a-z]* (\d{1,2}), (\d{4})')
MON = {m: i + 1 for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def treffer(slug):
    s = slug.lower()
    if "deliveries" not in s or "results" in s:
        return False
    if not ("reports" in s or "announces" in s):
        return False
    return any(w in s for w in ("quarter", "annual", "full-year", "orders-and-deliveries"))


def sammle(html, tage):
    for m in LINK.finditer(html):
        if treffer(m.group(4)):
            tage.add(datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))))


def write_gz(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(b"datum,wert\n")
        for d, v in rows:
            gz.write(("%s,%d\n" % (d.isoformat(), v)).encode())
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    tage = set()
    grenze = datetime.date(2012, 12, 1)
    o, erreicht = 0, False
    with ThreadPoolExecutor(3) as ex:
        while o < 6000 and not erreicht:
            seiten = list(ex.map(get, [BASE % x for x in range(o, o + 600, 100)]))
            for html in seiten:
                sammle(html, tage)
                ds = [datetime.date(int(y), MON[m], int(d)) for m, d, y in DATE.findall(html)]
                if not ds or min(ds) < grenze:
                    erreicht = True
            o += 600
    if not erreicht:
        raise RuntimeError("Liste reicht nicht bis vor 2013")
    for o in range(0, 500, 100):
        html = get(SEARCH % o)
        sammle(html, tage)
        if "wd_date" not in html:
            break
        time.sleep(0.5)
    if len(tage) < 100:
        raise RuntimeError("Nur %d Veroeffentlichungstage, erwartet >= 100" % len(tage))
    today = datetime.datetime.now(datetime.timezone.utc).date()
    start = min(tage)
    rows, d = [], start
    while d <= today:
        rows.append((d, 1 if d in tage else 0))
        d += datetime.timedelta(days=1)
    os.makedirs(OUT_DIR, exist_ok=True)
    write_gz(os.path.join(OUT_DIR, "auslieferungen_meldung.csv.gz"), rows)
    meta = {"auslieferungen_meldung": {
        "einheit": "0/1 (1 = Veroeffentlichungstag)",
        "beschreibung": ("Tage, an denen Boeing per Pressemitteilung die Auslieferungszahlen des abgelaufenen "
                         "Quartals (bzw. Jahres) bekanntgab, laut Datum in der URL des Boeing-Newsrooms; "
                         "1 am Veroeffentlichungstag, 0 sonst. Ereignisreihe, nach dem Datum der Bekanntgabe."),
        "quelle_url": "https://boeing.mediaroom.com/news-releases-statements",
        "verdichtung": "keine (Ereignistag aus Mitteilungsdatum)",
        "verfuegbar_nach_tagen": 0,
        "publikation": ("taeglich (Pressemitteilung am Tag der Bekanntgabe, Datum Teil der Mitteilungs-URL; "
                        "Beleg: boeing.mediaroom.com, z.B. 2026-10-13-Boeing-Announces-Third-Quarter-Deliveries)"),
        "revidiert": False,
    }}
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("Veroeffentlichungstage", len(tage), "Zeilen", len(rows), "erste", start)
    for y in sorted({t.year for t in tage}):
        print(y, sorted(t.isoformat()[5:] for t in tage if t.year == y))


if __name__ == "__main__":
    main()
