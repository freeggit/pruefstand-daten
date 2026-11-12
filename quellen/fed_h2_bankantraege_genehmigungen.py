#!/usr/bin/env python3
"""Federal Reserve Board: Entscheide zu Bankantraegen (Uebernahmen, Fusionen, Gruendungen) je Bekanntgabetag.
Quelle: https://www.federalreserve.gov/json/ne-press.json (Liste aller Pressemitteilungen des Board
ab 2006-01-03, Feld pt = Kategorie). Gezaehlt wird Kategorie «Orders on Banking Applications»
(Board-Entscheide, die im H.2-Wochenbericht unter «Board Actions» mit «Announced: <Datum>» stehen).
Datum = Datum der Pressemitteilung (Feld d, deckungsgleich mit dem Datum in der URL ordersJJJJMMTTx.htm).
Viele Mitteilungen erscheinen um 16:00 bis 16:30 Uhr New York, also nach Boersenschluss.
Reihe ab 2006-01-03, jeder Kalendertag bis heute (UTC), 0 = keine Bekanntgabe.
Reihe: anzahl_bekanntgaben."""
import datetime as dt
import gzip
import io
import json
import os
import re
import urllib.error
import urllib.request

ID = "fed_h2_bankantraege_genehmigungen"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
URL = "https://www.federalreserve.gov/json/ne-press.json"
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
START = dt.date(2006, 1, 3)
KAT = "Orders on Banking Applications"


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
    eintr = [x for x in daten if isinstance(x, dict) and "d" in x and "pt" in x]
    if len(eintr) < 3000:
        raise SystemExit("unerwartetes Format (%d Eintraege)" % len(eintr))
    heute = dt.datetime.now(dt.timezone.utc).date()
    n, weg = {}, 0
    for x in eintr:
        if x.get("pt") != KAT:
            continue
        try:
            d = dt.datetime.strptime(x["d"].split()[0], "%m/%d/%Y").date()
        except ValueError:
            weg += 1
            continue
        m = re.search(r"orders(\d{8})", x.get("l", ""))
        if m and m.group(1) != d.strftime("%Y%m%d"):
            weg += 1  # Datum widerspruechlich: nicht verwenden
            continue
        if d < START or d > heute:
            weg += 1
            continue
        n[d] = n.get(d, 0) + 1
    rows, t = [], START
    while t <= heute:
        rows.append((t.isoformat(), n.get(t, 0)))
        t += dt.timedelta(days=1)
    schreibe("anzahl_bekanntgaben", rows)
    meta = {
        "anzahl_bekanntgaben": {
            "einheit": "Anzahl Pressemitteilungen",
            "beschreibung": "Fed-Board-Entscheide zu Bankantraegen (meist Genehmigung von Uebernahmen und Fusionen "
                            "durch Bankholdings) je Bekanntgabetag; Pressemitteilungen der Kategorie "
                            "'Orders on Banking Applications'",
            "quelle_url": URL,
            "verdichtung": "Zaehlung der Pressemitteilungen je Datum; Kalendertage ohne Mitteilung = 0",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
            "publikation": "taeglich (jeder Board-Entscheid wird am Entscheidtag als datierte Pressemitteilung "
                           "veroeffentlicht, oft 16:00 Uhr New York; der H.2-Wochenbericht nennt dasselbe Datum als "
                           "'Announced'; Quelle: federalreserve.gov/newsevents/pressreleases.htm und /releases/h2/)",
        }
    }
    with open(os.path.join(D, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2, sort_keys=True)
    print("ok", sum(n.values()), "Bekanntgaben,", weg, "weggelassen")


if __name__ == "__main__":
    main()
