#!/usr/bin/env python3
"""Japan MoF Devisenmarkt-Interventionen: 1 am Interventionstag, sonst 0.
Tage aus der amtlichen CSV (Quartalsveroeffentlichung, ab Mai 1991). Danach nur so weit, wie
die Monatsmeldungen (Perioden zum 28./29., Veroeffentlichung ca. 2 Tage spaeter) lueckenlos
eine Gesamtsumme von 0 melden; bei Summe > 0 endet die Reihe vor der Periode, weil der Tag
erst mit der Quartalsveroeffentlichung bekannt wird (keine Nullen erfinden)."""
import datetime
import gzip
import io
import json
import os
import re
import urllib.request

ID = "japan_mof_interventionstage"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
BASE = "https://www.mof.go.jp/english/policy/international_policy/reference/feio/"
MON = {m: i + 1 for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def quarterly():
    text = get(BASE + "foreign_exchange_intervention_operations.csv").decode("cp932", "replace")
    days, qend = set(), None
    for line in text.splitlines():
        c = [x.strip() for x in line.split(",")] if '"' not in line else next(__import__("csv").reader([line]))
        if len(c) < 7:
            continue
        if re.match(r"^(January|April|July|October) - ", c[3]):
            m = re.search(r"([A-Za-z]+) (\d{4})$", c[3])
            mo = [k for k in MON if m.group(1).startswith(k)][0]
            y, n = int(m.group(2)), MON[mo]
            e = datetime.date(y + (n == 12), n % 12 + 1, 1) - datetime.timedelta(days=1)
            qend = max(qend, e) if qend else e
        elif re.match(r"^\d{4}$", c[3]) or (c[3] == "" and re.match(r"^\d+$", c[5])):
            pass
        if re.match(r"^\d{4}$", c[3]) and c[4] in MON and c[5].isdigit():
            cur = (int(c[3]), c[4])
        if c[4] in MON and c[5].isdigit() and c[6] not in ("", "0"):
            y = int(c[3]) if re.match(r"^\d{4}$", c[3]) else cur[0]
            days.add(datetime.date(y, MON[c[4]], int(c[5])))
    return days, qend


def monthly(qend):
    h = get(BASE + "monthly/index.html").decode("utf-8", "replace")
    items = re.findall(r'href="(?:[^"]*/)?(\d{8}e?)\.html">\s*([A-Za-z]+ \d+, \d{4}) - ([A-Za-z]+ \d+, \d{4})', h)
    per = []
    for slug, a, b in items:
        pa = datetime.datetime.strptime(a, "%B %d, %Y").date()
        pb = datetime.datetime.strptime(b, "%B %d, %Y").date()
        per.append((pa, pb, slug))
    per.sort()
    end = qend
    for pa, pb, slug in per:
        if pb <= end:
            continue
        if pa > end + datetime.timedelta(days=1):
            break
        t = get(BASE + "monthly/%s.html" % slug).decode("utf-8", "replace")
        m = re.search(r"Total amount.*?(?:&yen;|¥)\s*([\d,]+)", t, re.S)
        if not m or int(m.group(1).replace(",", "")) != 0:
            break
        end = pb
    return end


def main():
    days, qend = quarterly()
    end = monthly(qend)
    start = min(days)
    rows, d = [], start
    while d <= end:
        rows.append((d, 1 if d in days else 0))
        d += datetime.timedelta(days=1)
    os.makedirs(OUT_DIR, exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for d, v in rows:
            t.write("%s,%d\n" % (d.isoformat(), v))
        t.flush()
    open(os.path.join(OUT_DIR, "intervention.csv.gz"), "wb").write(buf.getvalue())
    meta = {"intervention": {
        "einheit": "Indikator (0/1)",
        "beschreibung": "1 am Tag einer Devisenmarktintervention des japanischen Finanzministeriums (Datum der Intervention), sonst 0; ab 1991-05-13 bis zum letzten durch Veroeffentlichung abgedeckten Tag (Quartals-CSV, danach nur lueckenlos 0-Monatsmeldungen).",
        "quelle_url": BASE + "index.html",
        "verdichtung": "keine",
        "publikation": "verzoegert (Tage einer Intervention werden amtlich erst mit der Quartalsveroeffentlichung rund 30 Tage nach Quartalsende genannt, spaetestens ca. 125 Tage nach dem Tag; Monatsmeldung nennt nur die Summe: https://www.mof.go.jp/english/policy/international_policy/reference/feio/index.html)",
        "verfuegbar_nach_tagen": 125,
        "revidiert": False}}
    json.dump(meta, open(os.path.join(OUT_DIR, "meta.json"), "w"), ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
