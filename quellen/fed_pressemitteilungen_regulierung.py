#!/usr/bin/env python3
"""Federal Reserve Board: Pressemitteilungen der Kategorie «Banking and Consumer Regulatory Policy» je Tag.
Quelle: https://www.federalreserve.gov/json/ne-press.json (Datenquelle der Liste
https://www.federalreserve.gov/newsevents/pressreleases.htm), Eintraege mit Datum und Uhrzeit (US-Ostzeit).

Datum = Kalendertag der Veroeffentlichung in US-Ostzeit (wie von der Fed angegeben). Rund ein Viertel der Mitteilungen erscheint nach
16 Uhr ET (nach Boersenschluss); darum verfuegbar_nach_tagen 1 (konservativ), Datum nicht verschoben.
Reihe ab dem ersten Eintrag der Kategorie, jeder Kalendertag bis heute (UTC), 0 = keine Mitteilung.
Enforcement Actions und Orders on Banking Applications sind NICHT enthalten (eigene Quellen
fed_enforcement_massnahmen, fed_h2_bankantraege_genehmigungen)."""
import datetime as dt
import gzip
import io
import json
import os
import urllib.error
import urllib.request

ID = "fed_pressemitteilungen_regulierung"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
URL = "https://www.federalreserve.gov/json/ne-press.json"
KAT = "Banking and Consumer Regulatory Policy"
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)


def schreibe(name, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for k, v in rows:
            t.write("%s,%d\n" % (k, v))
        t.flush()
    with open(os.path.join(D, name + ".csv.gz"), "wb") as fh:
        fh.write(buf.getvalue())


def main():
    os.makedirs(D, exist_ok=True)
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            daten = json.loads(r.read().decode("utf-8-sig", "replace"))
    except urllib.error.HTTPError as e:
        raise SystemExit("HTTP %d" % e.code)
    eintraege = [x for x in daten if isinstance(x, dict) and "d" in x and "pt" in x]
    if len(eintraege) < 3000:
        raise SystemExit("unerwartetes Format (%d Eintraege)" % len(eintraege))
    heute = dt.datetime.now(dt.timezone.utc).date()
    z = {}
    for x in eintraege:
        if (x.get("pt") or "").strip() != KAT:
            continue
        d = dt.datetime.strptime(x["d"].split()[0], "%m/%d/%Y").date()
        if d <= heute:
            z[d] = z.get(d, 0) + 1
    start = min(z)
    rows = []
    t = start
    while t <= heute:
        rows.append((t.isoformat(), z.get(t, 0)))
        t += dt.timedelta(days=1)
    schreibe("regulierung", rows)
    meta = {"regulierung": {
        "einheit": "Anzahl Pressemitteilungen",
        "beschreibung": "Fed-Pressemitteilungen «Banking and Consumer Regulatory Policy» (Kapitalregeln, "
                        "Stresstests, Aufsichtsleitlinien, Verbraucherschutzregeln) je Veroeffentlichungstag (US-Ostzeit)",
        "quelle_url": URL,
        "verdichtung": "Zaehlung der Mitteilungen je Kalendertag der Veroeffentlichung (US-Ostzeit); Tage ohne Mitteilung = 0",
        "verfuegbar_nach_tagen": 1,
        "revidiert": False,
        "publikation": "taeglich (jede Mitteilung erscheint mit Datum und Uhrzeit auf federalreserve.gov/newsevents/"
                       "pressreleases.htm; Quelle: Feld 'd' in ne-press.json)",
    }}
    with open(os.path.join(D, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2, sort_keys=True)
    print("ok", sum(z.values()), "Mitteilungen ab", start)


if __name__ == "__main__":
    main()
