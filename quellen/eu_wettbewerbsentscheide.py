#!/usr/bin/env python3
"""EU-Kommission: Pressemitteilungen (Typ IP) zu Fusionskontrolle und Kartell-/Missbrauchsverfahren je Tag.
Quelle: Presse-API der Kommission (Press Corner), https://ec.europa.eu/commission/presscorner/api/search
?language=en&documenttype=1 (documenttype 1 = Press release, IP/..). Archiv ab 1985-01-04, ohne Login/Schluessel.
Datum = eventDate der Pressemitteilung (Tag der Veroeffentlichung). Zuordnung ueber den englischen Titel
(Schluesselwortregeln unten, ueber alle Jahrgaenge gleich): Fusionskontrolle = Titel nennt merger/acquisition/
joint venture/takeover/concentration; Kartellverfahren = Titel nennt antitrust/cartel/Missbrauch marktbeherrschender
Stellung/Wettbewerbsregeln/Statement of Objections/Preisabsprache u.a. und ist keine Fusionsmeldung. Leitlinien,
Konsultationen und Beihilfen (State aid) ausgeschlossen. Jeder Kalendertag ab 1985-01-01 bis gestern (UTC),
0 = keine solche Pressemitteilung.
Abruf: das Archiv hat >51000 Mitteilungen (515 Seiten zu 100), Vollabruf ~5 Min. Darum Cache cache.json
(refCode -> [datum, titel]); ist der Cache vollstaendig, werden je Lauf nur die neuesten 15 Seiten neu geholt.
Fehlt der Cache, wird er in Etappen (Zeitbudget je Lauf) aufgebaut; CSV erst, wenn vollstaendig."""
import concurrent.futures as cf
import datetime as dt
import gzip
import io
import json
import os
import re
import time
import urllib.error
import urllib.request

ID = "eu_wettbewerbsentscheide"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
URL = ("https://ec.europa.eu/commission/presscorner/api/search?language=en&pagesize=100"
       "&documenttype=1&pagenumber=%d")
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
CACHE = os.path.join(D, "cache.json")
START = dt.date(1985, 1, 1)
BUDGET = 150
NEUESTE = 15

FUSION = re.compile(r"\b(mergers?|acquisitions?|acquire[sd]?|joint[- ]ventures?|takeovers?|concentrations?)\b", re.I)
KARTELL = re.compile(r"\b(antitrust|cartels?|abuse of (a )?dominan\w*|dominant position|competition (concerns|rules|law)"
                     r"|anti-?competitive|statements? of objections|price[- ]fixing|bid[- ]rigging|restrictive practices"
                     r"|article 8[56]|article 10[12]|collusion|unannounced inspections)\b", re.I)
AUS = re.compile(r"\b(state aid|guidelines?|consultation|seeks? (feedback|views|comments)|report on competition policy"
                 r"|competition policy report)\b", re.I)


def hole(p):
    req = urllib.request.Request(URL % p, headers={"User-Agent": UA})
    err = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise SystemExit("HTTP %d (Sperre, nicht umgangen)" % e.code)
            err = e
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(2)
    raise err


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
    t0 = time.time()
    c = {"vollstaendig": False, "naechste_seite": 1, "docs": {}}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as fh:
            c = json.load(fh)
    erste = hole(1)
    total = erste["totalNumber"]
    seiten = (total + 99) // 100
    if total < 40000:
        raise SystemExit("unerwartet wenige Mitteilungen: %d" % total)
    if c["vollstaendig"]:
        todo = list(range(1, NEUESTE + 1))
    else:
        todo = list(range(max(1, c["naechste_seite"]), seiten + 1))
    erledigt = 0
    with cf.ThreadPoolExecutor(4) as ex:
        for i in range(0, len(todo), 8):
            if time.time() - t0 > BUDGET:
                break
            for res in ex.map(hole, todo[i:i + 8]):
                for x in res["docuLanguageListResources"]:
                    c["docs"][x["refCode"]] = [x["eventDate"][:10], x["title"] or ""]
            erledigt = i + len(todo[i:i + 8])
    if not c["vollstaendig"]:
        c["naechste_seite"] = todo[erledigt - 1] + 1 if erledigt else c["naechste_seite"]
        if erledigt >= len(todo):
            c["vollstaendig"] = True
    with open(CACHE, "w", encoding="utf-8") as fh:
        json.dump(c, fh, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if not c["vollstaendig"]:
        raise SystemExit("im Aufbau: %d von ~%d Mitteilungen im Cache, weiter ab Seite %d"
                         % (len(c["docs"]), total, c["naechste_seite"]))
    heute = dt.datetime.now(dt.timezone.utc).date()
    ende = heute - dt.timedelta(days=1)
    fus, kar = {}, {}
    for datum, titel in c["docs"].values():
        titel = " ".join(titel.split())
        d = dt.date.fromisoformat(datum)
        if d < START or d > ende or AUS.search(titel):
            continue
        if FUSION.search(titel):
            fus[d] = fus.get(d, 0) + 1
        elif KARTELL.search(titel):
            kar[d] = kar.get(d, 0) + 1
    tage = []
    t = START
    while t <= ende:
        tage.append(t)
        t += dt.timedelta(days=1)
    schreibe("fusionskontrolle", [(d.isoformat(), fus.get(d, 0)) for d in tage])
    schreibe("kartellverfahren", [(d.isoformat(), kar.get(d, 0)) for d in tage])
    gemein = {
        "quelle_url": "https://ec.europa.eu/commission/presscorner/api/search?language=en&documenttype=1",
        "verfuegbar_nach_tagen": 0,
        "revidiert": False,
        "publikation": "taeglich: Pressemitteilungen erscheinen am Tag eventDate im Press Corner "
                       "(Feld publishDate, z.B. IP/25/2048 eventDate 2025-09-12, publishDate 2025-09-12 11:07 MESZ); "
                       "Archiv wird nicht nachtraeglich ergaenzt, nur einzelne Korrekturfassungen (CORRECTED) moeglich",
    }
    meta = {
        "fusionskontrolle": dict(gemein, **{
            "einheit": "Anzahl Pressemitteilungen",
            "beschreibung": "Taegliche Anzahl Pressemitteilungen (IP) der EU-Kommission zu Fusionskontrolle "
                            "(Freigabe, Auflagen, vertiefte Pruefung, Untersagung, Busse) nach Titel-Schluesselwoertern; "
                            "ab 1985. Strukturbruch ca. 2013: einfache Freigaben seither nur noch im Midday Express, "
                            "darum weniger, aber bedeutendere Faelle. 0 = keine Mitteilung.",
            "verdichtung": "Zaehlung je eventDate (Kalendertag), Titelregel FUSION ohne AUS"}),
        "kartellverfahren": dict(gemein, **{
            "einheit": "Anzahl Pressemitteilungen",
            "beschreibung": "Taegliche Anzahl Pressemitteilungen (IP) der EU-Kommission zu Kartell- und "
                            "Missbrauchsverfahren (Bussen, Beschwerdepunkte, Verpflichtungszusagen, Durchsuchungen) "
                            "nach Titel-Schluesselwoertern, ohne Fusionsmeldungen; ab 1985. 0 = keine Mitteilung.",
            "verdichtung": "Zaehlung je eventDate (Kalendertag), Titelregel KARTELL ohne FUSION und AUS"}),
    }
    with open(os.path.join(D, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2, sort_keys=True)
    print("ok", len(c["docs"]), "Mitteilungen,", sum(fus.values()), "Fusion,", sum(kar.values()), "Kartell")


if __name__ == "__main__":
    main()
