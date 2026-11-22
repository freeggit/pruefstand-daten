#!/usr/bin/env python3
"""EU-Handelsschutz: taegliche Anzahl Einleitungsbekanntmachungen und Zollverordnungen (Antidumping,
Antisubvention/Ausgleichszoll) im Amtsblatt der EU.
Quelle: Cellar-SPARQL-Endpunkt des Amts fuer Veroeffentlichungen, https://publications.europa.eu/webapi/rdf/sparql
(offen, ohne Login/Schluessel; Metadaten frei weiterverwendbar, Beschluss 2011/833/EU).
Datum = Veroeffentlichungstag im Amtsblatt (cdm:official-journal-act_date_publication, sonst Datum der
Amtsblatt-Ausgabe cdm:resource_legal_published_in_official-journal/publication_general_date_publication).
Akte ohne Veroeffentlichungsdatum werden nicht gezaehlt (kein Schaetzen).
Reihen (englischer Titel, Regeln unten, fuer alle Jahre gleich):
  einleitungen: Titel beginnt mit 'Notice of initiation' und nennt anti-dumping/anti-subsidy/countervailing
                (neue Verfahren und Ueberpruefungen).
  massnahmen:   Verordnung, deren Titel 'imposing a provisional|definitive anti-dumping|countervailing duty'
                bzw. '... duties' enthaelt, ohne Aenderungs-, Urteilsumsetzungs- und Berichtigungsakte.
Jeder Kalendertag ab START bis gestern (UTC), 0 = kein solcher Akt.
Cache je Jahr (cache/<jahr>.json); abgeschlossene Jahre bleiben, laufendes und Vorjahr werden je Lauf neu geholt."""
import concurrent.futures as cf
import datetime as dt
import gzip
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

ID = "eu_handelsschutz_antidumping"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
EP = "https://publications.europa.eu/webapi/rdf/sparql"
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
C = os.path.join(D, "cache")
START_JAHR = 1980
BUDGET = 150
Q = """PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?w ?pa ?po ?t WHERE { ?w cdm:work_date_document ?d .
FILTER(?d >= "%d-01-01"^^xsd:date && ?d <= "%d-12-31"^^xsd:date)
?e cdm:expression_belongs_to_work ?w ; cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> ;
 cdm:expression_title ?t . FILTER(REGEX(STR(?t),"anti-dumping|anti-subsidy|countervailing","i"))
OPTIONAL { ?w cdm:official-journal-act_date_publication ?pa }
OPTIONAL { ?w cdm:resource_legal_published_in_official-journal ?oj . ?oj cdm:publication_general_date_publication ?po } }"""
EINL = re.compile(r"^\s*notice of (the )?initiation\b", re.I)
MASS = re.compile(r"\bimposing (a |the )?(provisional|definitive) (anti-dumping|countervailing) dut(y|ies)", re.I)
MASS_AUS = re.compile(r"^\s*(corrigendum|judgment|order|opinion|proposal|commission (staff )?working|report)", re.I)
REG = re.compile(r"^\s*(council|commission)( implementing| delegated)? regulation", re.I)


def hole(jahr):
    body = urllib.parse.urlencode({"query": Q % (jahr, jahr)}).encode()
    req = urllib.request.Request(EP, data=body, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
    err = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                js = json.load(r)
            out = {}
            for b in js["results"]["bindings"]:
                w = b["w"]["value"].rsplit("/", 1)[-1]
                pd = (b.get("pa") or b.get("po") or {}).get("value")
                o = out.setdefault(w, {"pd": None, "t": []})
                if pd and (o["pd"] is None or pd < o["pd"]):
                    o["pd"] = pd[:10]
                t = b["t"]["value"]
                if t not in o["t"]:
                    o["t"].append(t)
            return out
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise SystemExit("HTTP %d (Sperre, nicht umgangen)" % e.code)
            err = e
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(3)
    raise err


def art(titel):
    t = " ".join(titel)
    if any(EINL.search(x) for x in titel):
        return "einleitungen"
    if any(REG.search(x) and MASS.search(x) for x in titel) and not any(MASS_AUS.search(x) for x in titel) \
            and not re.search(r"\b(amending|implementation of the judgment|corrigendum)\b", t, re.I):
        return "massnahmen"
    return None


def schreibe(name, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        tw = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        tw.write("datum,wert\n")
        for k, v in rows:
            tw.write("%s,%d\n" % (k, v))
        tw.flush()
    with open(os.path.join(D, name + ".csv.gz"), "wb") as fh:
        fh.write(buf.getvalue())


def main():
    os.makedirs(C, exist_ok=True)
    t0 = time.time()
    heute = dt.datetime.now(dt.timezone.utc).date()
    jahre = list(range(START_JAHR, heute.year + 1))
    frisch = {heute.year, heute.year - 1}
    offen = [j for j in jahre if j in frisch or not os.path.exists(os.path.join(C, "%d.json" % j))]
    offen.sort(key=lambda j: (j not in frisch, -j))
    with cf.ThreadPoolExecutor(3) as ex:
        futs = {}
        for j in offen:
            futs[ex.submit(hole, j)] = j
        for f in cf.as_completed(futs):
            j = futs[f]
            try:
                r = f.result()
            except SystemExit:
                raise
            except Exception as e:  # noqa: BLE001
                print("Jahr %d: %s" % (j, e))
                continue
            with open(os.path.join(C, "%d.json" % j), "w", encoding="utf-8") as fh:
                json.dump(r, fh, ensure_ascii=False, sort_keys=True)
            if time.time() - t0 > BUDGET:
                for g in futs:
                    g.cancel()
                break
    fehlt = [j for j in jahre if not os.path.exists(os.path.join(C, "%d.json" % j))]
    if fehlt:
        raise SystemExit("Cache unvollstaendig, fehlende Jahre: %s (naechster Lauf)" % fehlt)
    zahl = {"einleitungen": {}, "massnahmen": {}}
    gesehen = set()
    for j in jahre:
        with open(os.path.join(C, "%d.json" % j), encoding="utf-8") as fh:
            r = json.load(fh)
        for w, o in r.items():
            a = art(o["t"])
            if a is None or o["pd"] is None or w in gesehen:
                continue
            gesehen.add(w)
            zahl[a][o["pd"]] = zahl[a].get(o["pd"], 0) + 1
    start = dt.date(START_JAHR, 1, 1)
    ende = heute - dt.timedelta(days=1)
    for name, z in zahl.items():
        rows = []
        d = start
        while d <= ende:
            k = d.isoformat()
            rows.append((k, z.get(k, 0)))
            d += dt.timedelta(days=1)
        schreibe(name, rows)
    pub = ("taeglich: das Amtsblatt der EU erscheint werktags online (EUR-Lex), der Akt ist am Veroeffentlichungstag "
           "oeffentlich; Datum = cdm:official-journal-act_date_publication bzw. Datum der Amtsblatt-Ausgabe")
    meta = {
        "einleitungen": {
            "einheit": "Anzahl Bekanntmachungen",
            "beschreibung": "Taegliche Anzahl Einleitungsbekanntmachungen (Notice of initiation) von EU-Antidumping- und "
                            "Antisubventionsverfahren einschliesslich Ueberpruefungen im Amtsblatt (Reihe C), ab 1980. 0 = keine.",
            "quelle_url": EP, "verdichtung": "Zaehlung je Veroeffentlichungstag im Amtsblatt (Titelregel EINL)",
            "verfuegbar_nach_tagen": 0, "revidiert": False, "publikation": pub},
        "massnahmen": {
            "einheit": "Anzahl Verordnungen",
            "beschreibung": "Taegliche Anzahl Verordnungen zur Einfuehrung vorlaeufiger oder endgueltiger Antidumping- bzw. "
                            "Ausgleichszoelle im Amtsblatt (Reihe L), ohne Aenderungs- und Urteilsumsetzungsakte, ab 1980. 0 = keine.",
            "quelle_url": EP, "verdichtung": "Zaehlung je Veroeffentlichungstag im Amtsblatt (Titelregel MASS)",
            "verfuegbar_nach_tagen": 0, "revidiert": False, "publikation": pub},
    }
    with open(os.path.join(D, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2, sort_keys=True)
    print("ok", {k: sum(v.values()) for k, v in zahl.items()})


if __name__ == "__main__":
    main()
