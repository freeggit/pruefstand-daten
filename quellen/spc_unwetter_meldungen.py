#!/usr/bin/env python3
"""NOAA Storm Prediction Center, vorlaeufige Tagesberichte (Local Storm Reports), je Tag eine Datei
https://www.spc.noaa.gov/climo/reports/YYMMDD_rpts.csv mit drei Abschnitten (Tornado, Wind, Hagel).
Reihen: Anzahl Tornado-Meldungen und Anzahl Unwetter-Meldungen gesamt je Berichtstag (12 UTC bis 12 UTC
des Folgetags, Datum = Dateidatum). Etappenweise: Cache cache.json (Datum -> [tornado, wind, hagel]);
je Lauf Zeitbudget, ab 2005-01-01 vorwaerts (fruehere Dateien ohne Abschnittskoepfe). CSV erst, wenn der Cache lueckenlos bis gestern reicht.
Tage ohne Datei (404) oder mit leerer Datei bleiben fehlend; eine vorhandene Datei ohne Meldungen ergibt 0.
Die letzten 3 Tage werden je Lauf neu geholt (Berichtstag kann noch offen sein)."""
import concurrent.futures, datetime, gzip, io, json, os, sys, time, urllib.error, urllib.request
ID = "spc_unwetter_meldungen"
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
B = "https://www.spc.noaa.gov/climo/reports/"
BUDGET = float(os.environ.get("SPC_BUDGET", "140"))
START = datetime.date(2005, 1, 1)  # Dateien vor ca. 2004-05 ohne Abschnittskoepfe, nicht eindeutig zerlegbar


def holen(d):
    u = B + d.strftime("%y%m%d") + "_rpts.csv"
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=30)
        txt = r.read().decode("latin-1")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return d, "404"
        return d, "HTTP %d" % e.code
    except Exception as e:
        return d, "Fehler %s" % e
    if not txt.strip():
        return d, "404"  # leere Datei: Tag fehlt im Archiv, nicht als 0 werten
    z = {"t": 0, "w": 0, "h": 0}
    ab = None
    kopf = 0
    for ln in txt.splitlines():
        if not ln.strip():
            continue
        if ln.startswith("Time,"):
            kopf += 1
            f = ln.split(",")[1].lower()
            ab = "t" if f.startswith("f") else "w" if f.startswith("speed") else "h" if f.startswith("size") else None
            continue
        if ab:
            z[ab] += 1
    if kopf != 3:
        return d, "Format (%d Abschnitte)" % kopf
    return d, [z["t"], z["w"], z["h"]]


def main():
    os.makedirs(D, exist_ok=True)
    cp = os.path.join(D, "cache.json")
    c = json.load(open(cp)) if os.path.exists(cp) else {"tage": {}, "nicht_vorhanden": []}
    t0 = time.time()
    heute = datetime.datetime.now(datetime.timezone.utc).date()
    for i in range(1, 4):
        c["tage"].pop((heute - datetime.timedelta(days=i)).isoformat(), None)
    miss = set(c["nicht_vorhanden"])
    offen = [START + datetime.timedelta(days=i) for i in range((heute - START).days)]
    offen = [x for x in offen if x.isoformat() not in c["tage"] and x.isoformat() not in miss]
    offen = offen[-3:] + offen[:-3]  # juengste Tage zuerst, dann Rueckstand vorwaerts
    n = 0
    stop = None
    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        for j in range(0, len(offen), 40):
            if time.time() - t0 > BUDGET or stop:
                break
            for d, r in ex.map(holen, offen[j:j + 40]):
                k = d.isoformat()
                if r == "404":
                    miss.add(k)
                elif isinstance(r, list):
                    c["tage"][k] = r
                else:
                    stop = stop or "%s %s" % (k, r)
                n += 1
            time.sleep(0.5)
    c["nicht_vorhanden"] = sorted(miss)
    json.dump(c, open(cp, "w"))
    ks = sorted(c["tage"])
    fehl = [x for x in (START + datetime.timedelta(days=i) for i in range((heute - START).days))
            if x.isoformat() not in c["tage"] and x.isoformat() not in miss]
    print("Cache %d Tage, %s..%s, geholt %d, offen %d" % (len(ks), ks[0] if ks else "-", ks[-1] if ks else "-", n, len(fehl)))
    if stop:
        print("Abbruch:", stop)
        if "HTTP 403" in stop or "HTTP 429" in stop:
            sys.exit(2)
    if fehl:
        return
    reihen = {"tornado_meldungen": lambda v: v[0], "unwetter_meldungen_gesamt": lambda v: v[0] + v[1] + v[2]}
    for name, f in reihen.items():
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
            g.write(("datum,wert\n" + "".join("%s,%d\n" % (k, f(c["tage"][k])) for k in ks)).encode())
        open(os.path.join(D, name + ".csv.gz"), "wb").write(buf.getvalue())
    pub = ("taeglich: SPC stellt die vorlaeufigen Local Storm Reports laufend am Berichtstag ins Netz "
           "(spc.noaa.gov/climo/reports); der Berichtstag endet 12 UTC des Folgetags, darum 1 Tag.")
    desc = {"tornado_meldungen": "Anzahl vorlaeufiger Tornado-Meldungen (USA) je SPC-Berichtstag, ungefiltert (Mehrfachmeldungen moeglich)",
            "unwetter_meldungen_gesamt": "Anzahl vorlaeufiger Unwetter-Meldungen (Tornado + Wind + Hagel, USA) je SPC-Berichtstag, ungefiltert"}
    json.dump({n: {"einheit": "Anzahl", "beschreibung": b, "quelle_url": B + "YYMMDD_rpts.csv",
                   "verdichtung": "Summe (Zaehlung der Meldungszeilen) je Berichtstag 12 UTC bis 12 UTC",
                   "verfuegbar_nach_tagen": 1, "revidiert": False, "status": "aktiv", "publikation": pub}
               for n, b in desc.items()}, open(os.path.join(D, "meta.json"), "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
