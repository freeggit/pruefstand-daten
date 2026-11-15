#!/usr/bin/env python3
"""Japan MLIT: Anzahl Pressemitteilungen zu Fahrzeugrueckrufen je Tag (ab 2001).

Quelle: Ministry of Land, Infrastructure, Transport and Tourism (MLIT),
Jahresseiten «リコール・改善対策の届出» (https://www.mlit.go.jp/jidosha/recall.html
und recall_<Jahr>.html). Jede Tabellenzeile nennt einen Tag; links die
Pressemitteilungen zu Rueckrufanzeigen (リコールの届出), rechts zu
Verbesserungsmassnahmen (改善対策の届出). Gezaehlt wird je Tag die Anzahl
verlinkter Pressemitteilungen. Datum = Tag der Pressemitteilung (Bekanntgabe).
"""
import datetime
import gzip
import io
import json
import os
import re
import time
import urllib.error
import urllib.request

ID = "japan_mlit_fahrzeugrueckrufe"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
BASE = "https://www.mlit.go.jp"
INDEX = BASE + "/jidosha/recall.html"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
# nur Links auf Pressemitteilungen zaehlen (keine Menue-/Hilfslinks, keine Platzhalter)
PRESS = r'<a\s[^>]*href="\s*(?:https?://www\.mlit\.go\.jp)?/(?:report/press/[^"\s]+|jidosha/recall/[^"]+|kisha/[^"]+|page/riko[^"]+)"'
ZEN = str.maketrans("０１２３４５６７８９", "0123456789")


def fetch(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 429) or i == tries - 1:
                raise
            time.sleep(2 * (i + 1))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def label_year(label):
    s = label.translate(ZEN)
    if "令和元" in s:
        return 2019
    m = re.search(r"令和(\d+)年", s)
    if m:
        return 2018 + int(m.group(1))
    m = re.search(r"平成(\d+)年", s)
    if m:
        return 1988 + int(m.group(1))
    return None


def year_pages(index_html):
    pages = {}
    for href, label in re.findall(r'href="(/jidosha/recall[^"]*\.html)"[^>]*>([^<]+)</a>', index_html):
        y = label_year(label)
        if y and "年分" in label:
            pages.setdefault(y, BASE + href)
    return pages


def strip(s):
    return re.sub(r"<[^>]+>", "", s).translate(ZEN).replace("&nbsp;", " ").strip()


def parse_year(html, year):
    """liefert {datum: [rueckruf, kaizen]}.

    Das HTML der aelteren Jahresseiten ist teils unvollstaendig (fehlende
    </td> oder </tr>). Darum wird linear nach Zeilen- und Zellanfaengen
    zerlegt: je Zeile Zelle 0 = Tag, 1 = Rueckruf-Links, 2 = Tag, 3 = Kaizen-Links.
    """
    out = {}
    body = html
    marks = []
    for m in re.finditer(r">\s*([0-9０-９]{1,2})\s*月(?:分)?\s*<", body):
        marks.append((m.start(), "M", int(m.group(1).translate(ZEN))))
    for m in re.finditer(r"</?tr[\s>]", body, re.I):
        marks.append((m.start(), "R", None))
    for m in re.finditer(r"<td[\s>]", body, re.I):
        marks.append((m.start(), "D", None))
    marks.sort(key=lambda t: t[0])
    month = None
    cells = []

    def flush():
        if month is None or not cells:
            return
        row_day = None
        for col in (0, 2):
            if col + 1 >= len(cells):
                continue
            dm = re.match(r"^(\d{1,2})\s*日?$", strip(cells[col]))
            day = int(dm.group(1)) if dm else row_day
            if col == 0:
                row_day = day
            n = len(re.findall(PRESS, cells[col + 1], re.I))
            if not n:
                continue
            if day is None:
                raise RuntimeError("Link ohne Tagesangabe %d-%s" % (year, month))
            d = datetime.date(year, month, day).isoformat()
            out.setdefault(d, [0, 0])[col // 2] += n

    for i, (p, kind, val) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(body)
        if kind == "M":
            flush()
            cells = []
            if month is not None and val >= month:
                raise RuntimeError("Monatsfolge unerwartet %d: %s nach %s" % (year, val, month))
            month = val
        elif kind == "R":
            flush()
            cells = []
        else:
            cells.append(body[p:end] if body[p:end].find(">") < 0 else body[p + body[p:end].find(">") + 1:end])
    flush()
    return out


def gzip_write(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("datum,wert\n" + "".join("%s,%d\n" % r for r in rows)).encode())
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    idx = fetch(INDEX)
    pages = year_pages(idx)
    cur_year = datetime.datetime.now(datetime.timezone.utc).year
    # aktuelle Seite (recall.html) traegt das laufende Jahr
    title = re.search(r'<h2 class="title">([^<]+)</h2>', idx)
    ty = label_year(title.group(1)) if title else None
    if ty:
        pages[ty] = INDEX
    if min(pages) > 2001 or len(pages) < 20:
        raise RuntimeError("Jahresseiten unvollstaendig: %s" % sorted(pages))
    counts = {}
    for y in sorted(pages):
        html = idx if pages[y] == INDEX else fetch(pages[y])
        part = parse_year(html, y)
        if not part:
            raise RuntimeError("keine Eintraege fuer %d" % y)
        for d, v in part.items():
            c = counts.setdefault(d, [0, 0])
            c[0] += v[0]
            c[1] += v[1]
        time.sleep(0.5)
    today = datetime.datetime.now(datetime.timezone.utc).date()
    last = today - datetime.timedelta(days=1)
    first = datetime.date(min(pages), 1, 1)
    future = [d for d in counts if d > last.isoformat()]
    rows_r, rows_k = [], []
    d = first
    while d <= last:
        c = counts.get(d.isoformat(), [0, 0])
        rows_r.append((d.isoformat(), c[0]))
        rows_k.append((d.isoformat(), c[1]))
        d += datetime.timedelta(days=1)
    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "rueckruf_meldungen.csv.gz"), rows_r)
    gzip_write(os.path.join(OUT_DIR, "kaizen_meldungen.csv.gz"), rows_k)
    pub = ("taeglich: MLIT veroeffentlicht jede Anzeige als datierte Pressemitteilung (報道発表) "
           "am Tag der Bekanntgabe; die Jahresseite listet sie unter diesem Tag. Tag d endet "
           "in Japan vor Handelsbeginn in Europa/USA; konservativ verfuegbar_nach_tagen 1.")
    common = {
        "quelle_url": INDEX,
        "verfuegbar_nach_tagen": 1,
        "revidiert": False,
        "publikation": pub,
        "status": "aktiv",
    }
    meta = {
        "rueckruf_meldungen": dict(common, **{
            "einheit": "Anzahl Pressemitteilungen",
            "beschreibung": ("Anzahl MLIT-Pressemitteilungen zu Rueckrufanzeigen (リコールの届出) "
                             "fuer Strassenfahrzeuge in Japan je Tag der Bekanntgabe, 0 an Tagen "
                             "ohne Meldung. Mechanismus: Rueckrufhaeufungen japanischer Hersteller "
                             "(Autos gewichtig im japanischen Index) koennen EWJ belasten."),
            "verdichtung": "Anzahl verlinkter Pressemitteilungen je Kalendertag (Spalte Rueckruf)",
        }),
        "kaizen_meldungen": dict(common, **{
            "einheit": "Anzahl Pressemitteilungen",
            "beschreibung": ("Anzahl MLIT-Pressemitteilungen zu Verbesserungsmassnahmen "
                             "(改善対策の届出, Maengel ausserhalb der Sicherheitsnormen) je Tag "
                             "der Bekanntgabe, 0 an Tagen ohne Meldung."),
            "verdichtung": "Anzahl verlinkter Pressemitteilungen je Kalendertag (Spalte Kaizen)",
            "status": "ruhend",
        }),
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    if future:
        print("Hinweis: Eintraege nach %s ignoriert: %s" % (last, sorted(future)[:5]))
    print("Jahre", min(pages), "-", max(pages), "Tage mit Meldung", len(counts))


if __name__ == "__main__":
    main()
