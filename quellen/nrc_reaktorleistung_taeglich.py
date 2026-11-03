#!/usr/bin/env python3
"""NRC Power Reactor Status: Tagesberichte (Leistung je US-Reaktor in %). Reihen: mittlere Leistung aller
gemeldeten Bloecke (Mittel) und Anzahl Bloecke mit Leistung 0 (abgeschaltet). Etappenweise: Cache
cache.json (Datum -> [mittel, n, nullen]); je Lauf Zeitbudget, Rueckwaerts ab 2015-01-01 vorwaerts.
CSV erst, wenn der Cache lueckenlos ab 2015-01-01 reicht. Fehlende Berichtstage bleiben fehlend."""
import datetime, gzip, io, json, os, re, sys, time, urllib.request
ID = "nrc_reaktorleistung_taeglich"
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
B = "https://www.nrc.gov/documents-reports/document-collections/events-reports-associated-with/power-reactor-status-reports"
BUDGET = float(os.environ.get("NRC_BUDGET", "150"))
START = datetime.date(2015, 1, 1)

def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=30).read().decode("utf-8", "replace")

def agg(vals):
    return [round(sum(vals) / len(vals), 3), len(vals), sum(1 for v in vals if v == 0)]

def main():
    os.makedirs(D, exist_ok=True)
    cp = os.path.join(D, "cache.json")
    c = json.load(open(cp)) if os.path.exists(cp) else {"tage": {}, "nicht_vorhanden": []}
    t0 = time.time()
    # Schnellstart: letzte 365 Tage in einer Anfrage
    txt = get(B + "/PowerReactorStatusForLast365Days.txt")
    per = {}
    for ln in txt.splitlines()[1:]:
        p = ln.split("|")
        if len(p) == 3:
            try:
                d = datetime.datetime.strptime(p[0].split()[0], "%m/%d/%Y").date().isoformat()
                per.setdefault(d, []).append(float(p[2]))
            except ValueError:
                pass
    for d, v in per.items():
        c["tage"][d] = agg(v)
    today = datetime.datetime.now(datetime.timezone.utc).date()
    miss = set(c["nicht_vorhanden"])
    d = START
    n = 0
    while d < today and time.time() - t0 < BUDGET:
        k = d.isoformat()
        if k not in c["tage"] and k not in miss:
            try:
                h = get("%s/%d/%s%s" % (B, d.year, d.strftime("%Y%m%d"), "ps"))
                vals = []
                for row in re.findall(r"<tr>(.*?)</tr>", h, re.S):
                    td = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
                    if len(td) >= 2 and re.fullmatch(r"\s*\d+(\.\d+)?\s*", td[1]):
                        vals.append(float(td[1]))
                if vals:
                    c["tage"][k] = agg(vals)
                else:
                    miss.add(k)
                n += 1
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    miss.add(k)
                else:
                    print("HTTP", e.code, k); break
            except Exception as e:
                print("Fehler", k, e); break
            time.sleep(0.3)
        d += datetime.timedelta(days=1)
    c["nicht_vorhanden"] = sorted(miss)
    json.dump(c, open(cp, "w"))
    # Vollstaendigkeit
    ks = sorted(c["tage"])
    fehl = [x for x in (START + datetime.timedelta(days=i) for i in range((today - START).days))
            if x.isoformat() not in c["tage"] and x.isoformat() not in miss]
    print("Cache %d Tage, %s..%s, neu geholt %d, offen %d" % (len(ks), ks[0] if ks else "-", ks[-1] if ks else "-", n, len(fehl)))
    if fehl:
        return
    for name, i in (("mittlere_leistung_pct", 0), ("anzahl_abgeschaltet", 2)):
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
            g.write(("datum,wert\n" + "".join("%s,%s\n" % (k, c["tage"][k][i]) for k in ks)).encode())
        open(os.path.join(D, name + ".csv.gz"), "wb").write(buf.getvalue())
    desc = {"mittlere_leistung_pct": ("Prozent", "Mittlere Leistung aller im NRC-Tagesbericht gemeldeten US-Reaktorbloecke"),
            "anzahl_abgeschaltet": ("Anzahl", "Zahl der Bloecke mit Leistung 0 im NRC-Tagesbericht")}
    json.dump({n: {"einheit": e, "beschreibung": b, "quelle_url": B, "verdichtung": "Tagesbericht, Mittel bzw. Zaehlung ueber Bloecke",
                   "verfuegbar_nach_tagen": 1, "revidiert": False, "publikation": "taeglich: NRC veroeffentlicht den Bericht werktags, Leistung des Berichtstages"}
               for n, (e, b) in desc.items()}, open(os.path.join(D, "meta.json"), "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
