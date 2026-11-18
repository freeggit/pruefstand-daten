#!/usr/bin/env python3
"""EU-Kommission: Pressemitteilungen (Typ IP) zu staatlichen Beihilfen (State aid) je Tag.
Quelle: Presse-API der Kommission (Press Corner), https://ec.europa.eu/commission/presscorner/api/search
?language=en&documenttype=1 (documenttype 1 = Press release, IP/..). Archiv ab 1985, ohne Login/Schluessel.
Datum = eventDate der Pressemitteilung (Tag der Veroeffentlichung). Zuordnung ueber den englischen Titel
(Regeln unten, ueber alle Jahrgaenge gleich): Beihilfe = Titel nennt State aid/Beihilfeformen; ausgeschlossen
Leitlinien, Regelwerke, Konsultationen, Berichte. pruefungen = Eroeffnung vertiefter Pruefung, Negativentscheid,
Rueckforderung, Klage; genehmigungen = Genehmigung/Freigabe ohne Pruefungs-/Negativbegriff.
Jeder Kalendertag ab 1985-01-01 bis gestern (UTC), 0 = keine solche Pressemitteilung.
Abruf: >51000 Mitteilungen (515 Seiten zu 100), Vollabruf ~5 Min. Darum eigener Cache cache.json
(refCode -> [datum, titel]); ist er vollstaendig, werden je Lauf nur die neuesten 15 Seiten neu geholt.
Fehlt der Cache, wird er in Etappen aufgebaut (bei der Erstaufnahme aus dem vollstaendigen Cache derselben
API in data/neu/eu_wettbewerbsentscheide/cache.json kopiert, gleiche Quelle, kein Dritter)."""
import concurrent.futures as cf
import datetime as dt
import gzip
import io
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request

ID = "eu_beihilfe_entscheide"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
URL = ("https://ec.europa.eu/commission/presscorner/api/search?language=en&pagesize=100"
       "&documenttype=1&pagenumber=%d")
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu")
D = os.path.join(BASE, ID)
CACHE = os.path.join(D, "cache.json")
SAAT = os.path.join(BASE, "eu_wettbewerbsentscheide", "cache.json")
START = dt.date(1985, 1, 1)
BUDGET = 150
NEUESTE = 15

SA = re.compile(r"\b(state aids?|rescue aid|restructuring aid|aid schemes?|regional aid|illegal aid"
                r"|incompatible aid|tax rulings?|recapitali[sz]ation)\b", re.I)
AUS = re.compile(r"\b(guidelines?|guidance|consultation|seeks? (feedback|views|comments)|invites? comments|scoreboard"
                 r"|framework|reports?|rules|block exemption|GBER|modernisation|reform|survey|conference|speech"
                 r"|regulation|policy|communication)\b", re.I)
NEG = re.compile(r"\b(in-depth|opens?|incompatible|recover\w*|illegal|refers?|court|orders?|unlawful|repay\w*"
                 r"|investigat\w*|probe|scrutiny|negative|breach|proceedings?|initiates?|launch\w*|procedure)\b", re.I)
POS = re.compile(r"\b(approves?|approved|approval|clears?|cleared|authori[sz]\w*|endorses?|accepts?"
                 r"|does not (involve|constitute))\b", re.I)


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


def klasse(titel):
    if not SA.search(titel) or AUS.search(titel):
        return None
    if NEG.search(titel):
        return "pruefungen"
    if POS.search(titel):
        return "genehmigungen"
    return None


def main():
    os.makedirs(D, exist_ok=True)
    t0 = time.time()
    if not os.path.exists(CACHE) and os.path.exists(SAAT):
        shutil.copyfile(SAAT, CACHE)
    c = {"vollstaendig": False, "naechste_seite": 1, "docs": {}}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as fh:
            c = json.load(fh)
    erste = hole(1)
    total = erste["totalNumber"]
    seiten = (total + 99) // 100
    if total < 40000:
        raise SystemExit("unerwartet wenige Mitteilungen: %d" % total)
    todo = list(range(1, NEUESTE + 1)) if c["vollstaendig"] else list(range(max(1, c["naechste_seite"]), seiten + 1))
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
        raise SystemExit("im Aufbau: %d Mitteilungen im Cache, weiter ab Seite %d" % (len(c["docs"]), c["naechste_seite"]))
    ende = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
    z = {"genehmigungen": {}, "pruefungen": {}}
    for datum, titel in c["docs"].values():
        titel = " ".join(titel.split())
        d = dt.date.fromisoformat(datum)
        if d < START or d > ende:
            continue
        k = klasse(titel)
        if k:
            z[k][d] = z[k].get(d, 0) + 1
    tage = []
    t = START
    while t <= ende:
        tage.append(t)
        t += dt.timedelta(days=1)
    for name in z:
        schreibe(name, [(d.isoformat(), z[name].get(d, 0)) for d in tage])
    gemein = {
        "einheit": "Anzahl Pressemitteilungen",
        "quelle_url": "https://ec.europa.eu/commission/presscorner/api/search?language=en&documenttype=1",
        "verfuegbar_nach_tagen": 0,
        "revidiert": False,
        "publikation": "taeglich: Pressemitteilungen erscheinen am Tag eventDate im Press Corner "
                       "(Feld publishDate am selben Tag, z.B. IP/26/2457 eventDate 2026-11-17); Archiv wird nicht "
                       "nachtraeglich ergaenzt, nur einzelne Korrekturfassungen (CORRECTED) moeglich",
    }
    meta = {
        "genehmigungen": dict(gemein, **{
            "beschreibung": "Taegliche Anzahl Pressemitteilungen (IP) der EU-Kommission, die staatliche Beihilfen "
                            "genehmigen (Beihilferegelungen, Einzelbeihilfen, Bankenrettungen und Rekapitalisierungen), "
                            "nach Titel-Schluesselwoertern; ab 1985. Spitzen 2008-2009 (Bankenkrise), 2020-2022 "
                            "(Covid- und Energiekrisenhilfen). 0 = keine Mitteilung.",
            "verdichtung": "Zaehlung je eventDate (Kalendertag), Titelregel SA und POS ohne AUS und NEG"}),
        "pruefungen": dict(gemein, **{
            "beschreibung": "Taegliche Anzahl Pressemitteilungen (IP) der EU-Kommission zu Beihilfe-Pruefungen mit "
                            "Risiko fuer Empfaenger (Eroeffnung vertiefter Pruefung, Negativentscheid, Rueckforderung, "
                            "Verweis an den Gerichtshof, z.B. Steuervorbescheide), nach Titel-Schluesselwoertern; "
                            "ab 1985. 0 = keine Mitteilung.",
            "verdichtung": "Zaehlung je eventDate (Kalendertag), Titelregel SA und NEG ohne AUS"}),
    }
    with open(os.path.join(D, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2, sort_keys=True)
    print("ok", len(c["docs"]), "Mitteilungen,", {k: sum(v.values()) for k, v in z.items()})


if __name__ == "__main__":
    main()
