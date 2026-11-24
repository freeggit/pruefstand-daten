#!/usr/bin/env python3
"""BODACC (Frankreich): amtliche Meldungen zu Insolvenzverfahren je Ausgabetag.

Quelle: DILA, Datensatz annonces-commerciales auf bodacc-datadila.opendatasoft.com
(Licence Ouverte / Etalab, ohne Login, ohne Schluessel). Gruppierte Abfrage je
dateparution (Ausgabetag des BODACC A):
  verfahren_alle: familleavis = collective (alle Procedures collectives)
  liquidationen_eroeffnet: davon Jugement d'ouverture de liquidation judiciaire
Datum = Ausgabetag. 0 an Kalendertagen ohne Ausgabe, aber nur bis zum letzten
Ausgabetag im Bestand (keine Nullen fuer noch nicht geladene Tage).
Beginn 2008-02-03 (Januar 2008 lueckenhaft: nach 10.01. 24 Tage ohne Ausgabe).
"""
import datetime, gzip, io, json, os, urllib.parse, urllib.request

ID = "bodacc_insolvenzen_frankreich"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
B = "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/annonces-commerciales/records"
W = {"verfahren_alle": 'familleavis="collective"',
     "liquidationen_eroeffnet": 'familleavis="collective" and jugement like "*ouverture de liquidation*"'}
START = datetime.date(2008, 2, 3)
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)


def hole(where):
    q = urllib.parse.urlencode({"select": "count(*) as n", "where": where,
                                "group_by": "dateparution", "limit": 20000})
    req = urllib.request.Request(B + "?" + q, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        j = json.load(r)
    out = {}
    for x in j["results"]:
        out[datetime.date.fromisoformat(x["dateparution"][:10])] = int(x["n"])
    if len(out) < 4000:
        raise SystemExit("zu wenige Ausgabetage: %d" % len(out))
    return out


def gz(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
        g.write(b"datum,wert\n")
        for d, v in rows:
            g.write(("%s,%d\n" % (d.isoformat(), v)).encode())
    open(path, "wb").write(buf.getvalue())


def main():
    os.makedirs(D, exist_ok=True)
    heute = datetime.datetime.utcnow().date()
    daten = {n: hole(w) for n, w in W.items()}
    ende = min(max(k for k in daten["verfahren_alle"] if k <= heute), heute)
    for n, c in daten.items():
        rows, d = [], START
        while d <= ende:
            rows.append((d, c.get(d, 0)))
            d += datetime.timedelta(days=1)
        gz(os.path.join(D, n + ".csv.gz"), rows)
    pub = ("taeglich: BODACC A erscheint an Werktagen elektronisch auf bodacc.fr, der DILA-Datensatz "
           "annonces-commerciales wird mit jeder Ausgabe ergaenzt (Datum = dateparution); vorsichtig 1 Tag")
    desc = {"verfahren_alle": "Anzahl BODACC-Meldungen zu Insolvenzverfahren (Procedures collectives: Eroeffnung, Plan, Liquidation, Abschluss) je Ausgabetag, Frankreich.",
            "liquidationen_eroeffnet": "Davon Meldungen ueber die gerichtliche Eroeffnung einer Liquidation (Jugement d'ouverture de liquidation judiciaire) je Ausgabetag."}
    json.dump({n: {"einheit": "Anzahl Meldungen je Tag", "beschreibung": b,
                   "quelle_url": B + "?where=" + urllib.parse.quote(W[n]),
                   "verdichtung": "Anzahl je Kalendertag (dateparution), 0 an Tagen ohne Ausgabe bis zum letzten Ausgabetag",
                   "verfuegbar_nach_tagen": 1, "revidiert": False, "publikation": pub, "status": "aktiv"}
               for n, b in desc.items()}, open(os.path.join(D, "meta.json"), "w"), ensure_ascii=False, indent=1)
    print(ID, "bis", ende, {n: sum(c.values()) for n, c in daten.items()})


if __name__ == "__main__":
    main()
