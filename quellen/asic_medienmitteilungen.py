#!/usr/bin/env python3
"""ASIC (Australian Securities and Investments Commission): Medienmitteilungen je Tag.

Liste der Mitteilungen aus der oeffentlichen sitemap.xml von asic.gov.au, Datum je
Mitteilung aus dem Meta-Feld displayDate der Detailseite (= Veroeffentlichungstag,
australische Ortszeit). Zwischenstand je Jahr in data/neu/<id>/_cache/<jahr>.json,
damit keine Seite doppelt geholt wird. Die CSV-Dateien werden erst geschrieben, wenn
alle Jahre vollstaendig im Zwischenstand liegen (nichts auffuellen, nichts schaetzen).
"""
import datetime
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ID = "asic_medienmitteilungen"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
SITEMAP = "https://www.asic.gov.au/sitemap.xml"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "neu", ID)
CACHE = os.path.join(OUT, "_cache")
START = "2015-01-01"  # Sitemap vor 2015 lueckenhaft (2014: 203 von 347 Nummern, 2008: 33 von 219); ab 2015 >= 92 %
BUDGET_S = float(os.environ.get("ASIC_BUDGET_S", "160"))
WORKERS = 6
LOC = re.compile(r"<loc>(https://www\.asic\.gov\.au/about-asic/news-centre/find-a-media-release/(\d{4})-releases/[^<]+)</loc>")
# displayDate = angezeigtes Veroeffentlichungsdatum; dcterms.date.created ist teils das Datum einer CMS-Migration
DATE = re.compile(r'name="displayDate"\s+content="(\d{1,2} [A-Za-z]+ \d{4})"')
TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
DURCH = re.compile(
    r"\b(ban|banned|bans|penalt|charged|charges|court|sentenc|jail|prison|disqualif|infringement|"
    r"enforceable undertaking|cancel|convict|guilty|fined|sues|sued|proceedings|suspend|"
    r"civil penalty|stop order|freez|wind(ing)? up|liquidat)", re.I)


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise
            if e.code == 404:
                return None
            if i == tries - 1:
                raise
        except Exception:
            if i == tries - 1:
                raise
        time.sleep(2 * (i + 1))


def seite(url):
    h = get(url)
    if h is None:
        return url, None
    m = DATE.search(h)
    d = datetime.datetime.strptime(m.group(1), "%d %B %Y").date().isoformat() if m else None
    t = TITLE.search(h)
    t = re.sub(r"\s+", " ", t.group(1)).strip() if t else ""
    return url, {"datum": d, "quelle": "displayDate", "titel": t[:300]}


def gz(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as f:
        f.write(("datum,wert\n" + "".join(f"{a},{b}\n" for a, b in rows)).encode())
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    t0 = time.time()
    os.makedirs(CACHE, exist_ok=True)
    sm = get(SITEMAP)
    jahre = {}
    for url, j in LOC.findall(sm):
        if "/attachment" in url:
            continue
        if j >= START[:4]:
            jahre.setdefault(j, set()).add(url)
    offen = 0
    for j in sorted(jahre):
        p = os.path.join(CACHE, f"{j}.json")
        c = json.load(open(p)) if os.path.exists(p) else {}
        todo = sorted(u for u in jahre[j] if u not in c or (c[u] or {}).get("quelle") != "displayDate")
        if todo and time.time() - t0 < BUDGET_S:
            with ThreadPoolExecutor(WORKERS) as ex:
                futs = []
                for u in todo:
                    futs.append(ex.submit(lambda u=u: seite(u) if time.time() - t0 < BUDGET_S else (u, "skip")))
                for f in futs:
                    u, v = f.result()
                    if v != "skip":
                        c[u] = v
            with open(p, "w") as f:
                json.dump(c, f, indent=0, sort_keys=True)
        rest = sum(1 for u in jahre[j] if u not in c or (c[u] or {}).get("quelle") != "displayDate")
        offen += rest
        print(j, len(jahre[j]), "offen", rest, file=sys.stderr)
    if offen:
        print(f"Zwischenstand: {offen} Seiten offen, keine CSV geschrieben", file=sys.stderr)
        return 0
    alle, durch = {}, {}
    ohne = 0
    for j in jahre:
        c = json.load(open(os.path.join(CACHE, f"{j}.json")))
        for u in jahre[j]:
            v = c.get(u)
            if not v or not v.get("datum"):
                ohne += 1
                continue
            d = v["datum"]
            alle[d] = alle.get(d, 0) + 1
            if DURCH.search(v.get("titel", "")):
                durch[d] = durch.get(d, 0) + 1
    # nur abgeschlossene australische Tage (UTC+10), damit kein Teiltag erscheint
    heute = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=10))).date() - datetime.timedelta(days=1)
    tag = datetime.date.fromisoformat(START)
    r1, r2 = [], []
    while tag <= heute:
        s = tag.isoformat()
        r1.append((s, alle.get(s, 0)))
        r2.append((s, durch.get(s, 0)))
        tag += datetime.timedelta(days=1)
    gz(os.path.join(OUT, "anzahl_mitteilungen.csv.gz"), r1)
    gz(os.path.join(OUT, "anzahl_durchsetzung.csv.gz"), r2)
    pub = ("taeglich: Mitteilungen erscheinen am Veroeffentlichungstag auf asic.gov.au/newsroom/media-releases "
           "(Meta displayDate = angezeigtes Erscheinungsdatum); australischer Tag liegt vor dem US-Handelstag, 1 Tag Sicherheitsabstand")
    gem = dict(quelle_url="https://www.asic.gov.au/newsroom/media-releases", verfuegbar_nach_tagen=1,
               revidiert=False, publikation=pub, einheit="Anzahl Mitteilungen")
    meta = {
        "anzahl_mitteilungen": dict(gem, beschreibung=(
            "Taegliche Anzahl Medienmitteilungen der australischen Finanzmarktaufsicht ASIC ab 2015 "
            "(Liste aus der oeffentlichen sitemap.xml, Datum = angezeigtes Veroeffentlichungsdatum displayDate der Mitteilung, australische Ortszeit), "
            "0 an Tagen ohne Mitteilung. Hinweis: von ASIC spaeter entfernte Mitteilungen fehlen (Zaehlung kann "
            "nachtraeglich leicht sinken)."),
            verdichtung="Anzahl Mitteilungen je Kalendertag (Veroeffentlichungsdatum)"),
        "anzahl_durchsetzung": dict(gem, beschreibung=(
            "Teilmenge: Mitteilungen mit Durchsetzungsbezug laut Titel (Stichworte ban, penalty, charged, court, "
            "sentenced, disqualified, infringement, enforceable undertaking, cancel, convicted, fined, sues, "
            "proceedings, suspend, stop order, freeze, wind up, liquidat)."),
            verdichtung="Anzahl Mitteilungen je Kalendertag mit Stichwort im Titel"),
    }
    with open(os.path.join(OUT, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False, sort_keys=True)
    print(f"geschrieben: {len(r1)} Tage, {sum(alle.values())} Mitteilungen, ohne Datum {ohne}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
