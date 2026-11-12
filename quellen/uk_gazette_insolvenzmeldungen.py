#!/usr/bin/env python3
"""The Gazette (UK): amtliche Insolvenzmeldungen je Veroeffentlichungstag.

Je Kalendertag eine Abfrage des Atom-Feeds (Feld f:total) fuer
  firmen_insolvenz: Kategorie G205010000 (Corporate Insolvency, alle Meldungsarten)
  abwicklungsantraege: Meldungsart 2450 (Petitions to Wind Up (Companies), Glaeubigerantraege)
Datum = publish-date der Gazette (Tag der amtlichen Veroeffentlichung).
Etappenweise: cache.json (Datum -> [firmen, antraege]); CSV erst, wenn der Bestand
ab Start lueckenlos ist. Die juengsten 14 Tage werden jeden Lauf neu abgefragt.
"""
import concurrent.futures, datetime, gzip, io, json, os, time, urllib.error, urllib.request

ID = "uk_gazette_insolvenzmeldungen"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
B = "https://www.thegazette.co.uk/insolvency/notice/data.feed"
Q = {"firmen_insolvenz": "categorycode=G205010000",
     "abwicklungsantraege": "noticetypes=2450"}
START = datetime.date(1998, 1, 1)
BUDGET = 135
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)


def total(q, d):
    url = "%s?%s&start-publish-date=%s&end-publish-date=%s&results-page-size=1" % (B, q, d, d)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        t = r.read().decode("utf-8", "replace")
    i = t.find("<f:total>")
    if i < 0:
        raise ValueError("kein f:total fuer %s" % d)
    return int(t[i + 9:t.index("<", i + 9)])


def tag(d):
    for v in range(2):
        try:
            return [total(Q["firmen_insolvenz"], d), total(Q["abwicklungsantraege"], d)]
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise
            err = e
        except Exception as e:
            err = e
        time.sleep(3)
    return err


def gz(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
        g.write(b"datum,wert\n")
        for d, v in rows:
            g.write(("%s,%d\n" % (d, v)).encode())
    open(path, "wb").write(buf.getvalue())


def main():
    t0 = time.time()
    os.makedirs(D, exist_ok=True)
    cp = os.path.join(D, "cache.json")
    c = json.load(open(cp)) if os.path.exists(cp) else {"tage": {}}
    heute = datetime.datetime.utcnow().date()
    ende = heute - datetime.timedelta(days=1)
    alle = []
    d = START
    while d <= ende:
        alle.append(d.isoformat())
        d += datetime.timedelta(days=1)
    jung = alle[-14:]
    offen = jung + [x for x in alle[:-14] if x not in c["tage"]]
    fehler = None
    nfehl = 0
    with concurrent.futures.ThreadPoolExecutor(3) as ex:
        for i in range(0, len(offen), 30):
            if time.time() - t0 > BUDGET:
                break
            teil = offen[i:i + 30]
            try:
                for x, v in zip(teil, ex.map(tag, teil)):
                    if isinstance(v, list):
                        c["tage"][x] = v
                    else:
                        nfehl += 1
                        fehler = "%s bei %s: %s" % (type(v).__name__, x, v)
                if nfehl > 20:
                    break
            except Exception as e:
                fehler = "%s: %s" % (type(e).__name__, e)
                break
    json.dump(c, open(cp, "w"))
    fehlt = [x for x in alle if x not in c["tage"]]
    print(ID, "Cache", len(c["tage"]), "offen", len(fehlt), "Fehler", fehler)
    if fehler and not c["tage"]:
        raise SystemExit(fehler)
    if fehlt:
        return
    for k, n in enumerate(Q):
        rows = [(x, c["tage"][x][k]) for x in alle]
        while rows and rows[0][1] == 0:
            rows.pop(0)
        gz(os.path.join(D, n + ".csv.gz"), rows)
    pub = ("taeglich: The Gazette veroeffentlicht Meldungen am publish-date online (Feed sofort abrufbar); "
           "Datum = publish-date, Wert am Folgetag vollstaendig")
    desc = {"firmen_insolvenz": "Amtliche Insolvenzmeldungen zu Firmen (Kategorie Corporate Insolvency) in The Gazette je Veroeffentlichungstag.",
            "abwicklungsantraege": "Davon Antraege auf Zwangsabwicklung von Firmen (Petitions to Wind Up, Meldungsart 2450) je Veroeffentlichungstag."}
    json.dump({n: {"einheit": "Anzahl Meldungen je Tag", "beschreibung": b,
                   "quelle_url": B + "?" + Q[n], "verdichtung": "Anzahl je Kalendertag (publish-date), 0 an Tagen ohne Ausgabe",
                   "verfuegbar_nach_tagen": 1, "revidiert": False, "publikation": pub, "status": "aktiv"}
               for n, b in desc.items()}, open(os.path.join(D, "meta.json"), "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
