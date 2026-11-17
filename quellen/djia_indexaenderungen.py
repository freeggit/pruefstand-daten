#!/usr/bin/env python3
"""Dow Jones Industrial Average: Anzahl aufgenommener Titel je Wirksamkeitstag ab 1896.

Quelle: Wikipedia-Artikel 'Historical components of the Dow Jones Industrial Average'
(Special:Export, Wikitext). Jeder Abschnitt '== <Datum> ==' zeigt die Zusammensetzung ab
diesem Wirksamkeitstag; aufgenommene Titel sind mit dem Pfeil '↑' markiert. Gezaehlt wird
die Zahl der Pfeile je Abschnitt. Abschnitte ohne Pfeil (nur Namensaenderungen) und der
Starttag 26.5.1896 (Indexbeginn, keine Aenderung) zaehlen nicht. Reihe fuer jeden
Kalendertag vom 26.5.1896 bis heute, 0 an Tagen ohne Aenderung.
"""
import datetime
import gzip
import html
import io
import json
import os
import re
import urllib.request

ID = "djia_indexaenderungen"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
EXPORT_URL = "https://en.wikipedia.org/wiki/Special:Export/Historical_components_of_the_Dow_Jones_Industrial_Average"
ARTICLE_URL = "https://en.wikipedia.org/wiki/Historical_components_of_the_Dow_Jones_Industrial_Average"
START = datetime.date(1896, 5, 26)
MONTHS = {m: i + 1 for i, m in enumerate(
    "January February March April May June July August September October November December".split())}
HEAD = re.compile(r"^==\s*(%s)\s+(\d{1,2}),\s*(\d{4})\s*==\s*$" % "|".join(MONTHS), re.M)


def fetch():
    req = urllib.request.Request(EXPORT_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read().decode("utf-8")
    m = re.search(r"<text[^>]*>(.*)</text>", data, re.S)
    if not m:
        raise RuntimeError("Wikitext nicht gefunden")
    return html.unescape(m.group(1))


def parse(text):
    heads = list(HEAD.finditer(text))
    counts = {}
    for i, h in enumerate(heads):
        d = datetime.date(int(h.group(3)), MONTHS[h.group(1)], int(h.group(2)))
        body = text[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        n = body.count("↑")
        if d <= START or n == 0:
            continue
        if d in counts:
            raise RuntimeError("Datum doppelt: %s" % d)
        counts[d] = n
    return counts


def write_gz(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(b"datum,wert\n")
        for d, v in rows:
            gz.write(("%s,%d\n" % (d.isoformat(), v)).encode())
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    counts = parse(fetch())
    if len(counts) < 50:
        raise RuntimeError("Nur %d Aenderungstage geparst, erwartet >= 50" % len(counts))
    today = datetime.datetime.now(datetime.timezone.utc).date()
    rows, d = [], START
    while d <= today:
        rows.append((d, counts.get(d, 0)))
        d += datetime.timedelta(days=1)
    os.makedirs(OUT_DIR, exist_ok=True)
    write_gz(os.path.join(OUT_DIR, "aufnahmen.csv.gz"), rows)
    meta = {"aufnahmen": {
        "einheit": "Anzahl aufgenommener Titel",
        "beschreibung": ("Anzahl der in den Dow Jones Industrial Average aufgenommenen Titel je Wirksamkeitstag "
                         "(Abschnitte mit Pfeil im Wikipedia-Artikel der historischen Zusammensetzung), 0 an "
                         "Tagen ohne Aenderung. Indexeffekt (Shleifer 1986). Datum = Wirksamkeitstag; die "
                         "Bekanntgabe lag seit 1991 jeweils 3 bis 14 Tage davor (Belege im Artikel), der Tag "
                         "war also am Datum bereits oeffentlich bekannt."),
        "quelle_url": ARTICLE_URL,
        "verdichtung": "Anzahl Pfeile (Aufnahmen) je Abschnitt/Wirksamkeitstag; keine",
        "verfuegbar_nach_tagen": 0,
        "publikation": ("taeglich (Wirksamkeitstag wird von S&P Dow Jones Indices vorab per Pressemitteilung "
                        "angekuendigt, z.B. Alphabet 23.6.2026 fuer 29.6.2026; Beleg: Referenzen im Artikel)"),
        "revidiert": False,
    }}
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("Aenderungstage", len(counts), "Zeilen", len(rows))


if __name__ == "__main__":
    main()
