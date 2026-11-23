#!/usr/bin/env python3
"""Federal Register: USITC Section-337-Verfahren (Patentverletzung bei Einfuhren) je Tag.

Mechanismus: Section-337-Verfahren drohen mit Einfuhrverboten wegen Patentverletzung, meist gegen Halbleiter,
Elektronik und Medizintechnik; Haeufungen belasten kurzfristig Technologie (XLK) und asiatische Exportlaender
gegenueber dem Weltindex.

Abruf: alle Federal-Register-Dokumente der International Trade Commission je Jahr (Titel und Publikationsdatum),
Auswahl ueber den Titel. Section-337-Verfahren tragen Titel der Form «Certain <Ware>; Notice of Investigation»
bzw. «In the Matter of Certain <Ware>; Notice of Institution ...» (Antidumping-Verfahren heissen «<Ware> From
<Land>» und fallen heraus). Reihen:
  einleitungen  = Titel beginnt mit «Certain» oder «In the Matter of Certain» und enthaelt «Notice of
                  Investigation», «Institution of» (Untersuchung, Einleitung)
Ausschlussverfuegungen («Exclusion Order», rund 10 je Jahr) werden nicht gezaehlt: zu selten fuer eine Reihe.
Inkrementell nach fr_inkrementell (nur Vorjahr und laufendes Jahr neu).
"""
import datetime, gzip, io, json, os, sys, time, urllib.error, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fr_inkrementell  # noqa: E402

ID = "fedregister_itc_337_patentverfahren"
BASE = "https://www.federalregister.gov/api/v1/documents.json"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
START_YEAR = 1994
AGENCY = "international-trade-commission"
REIHEN = ("einleitungen",)


def fetch_json(url, retries=3):
    fr_inkrementell.pause()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (500, 502, 503) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise


def klassiere(titel):
    t = " ".join((titel or "").split())
    tl = t.lower()
    if not (tl.startswith("certain ") or tl.startswith("in the matter of certain")):
        return None
    if "exclusion order" in tl:
        return None
    if "notice of investigation" in tl or "institution of" in tl:
        return "einleitungen"
    return None


def fetch_year(year, counts):
    page = 1
    while True:
        params = [("conditions[agencies][]", AGENCY), ("conditions[publication_date][year]", str(year)),
                  ("per_page", "1000"), ("page", str(page)), ("fields[]", "publication_date"),
                  ("fields[]", "title"), ("order", "oldest")]
        data = fetch_json(BASE + "?" + urllib.parse.urlencode(params))
        res = data.get("results", [])
        tp = data.get("total_pages", 1)
        if not res and page < tp:
            raise SystemExit("Abruffehler %s: leere Seite %d von %d; bisherige Datei bleibt" % (ID, page, tp))
        for r in res:
            k = klassiere(r.get("title"))
            d = r.get("publication_date")
            if k and d:
                counts[k][d] = counts[k].get(d, 0) + 1
        if page >= tp or not res:
            break
        page += 1


def write(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("datum,wert\n" + "".join("%s,%d\n" % r for r in rows)).encode())
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    cy = datetime.date.today().year
    # Beide Reihen gemeinsam planen: Jahre aus der ersten Reihe; fehlt eine Datei, ganze Historie
    plaene = [fr_inkrementell.plan(os.path.join(OUT_DIR, r + ".csv.gz"), START_YEAR, cy) for r in REIHEN]
    jahre = max((p[1] for p in plaene), key=len)
    if len(jahre) == cy - START_YEAR + 1:
        counts = {r: {} for r in REIHEN}
    else:
        counts = {r: {d: v for d, v in p[0].items() if v} for r, p in zip(REIHEN, plaene)}
    for y in jahre:
        fetch_year(y, counts)
    if not counts["einleitungen"]:
        raise RuntimeError("keine Dokumente gefunden")
    # bis gestern (UTC) bzw. letzter Publikationstag, keine Zukunft
    heute = datetime.datetime.utcnow().date()
    last = heute
    for r in REIHEN:
        rows, d = [], datetime.date(START_YEAR, 1, 1)
        while d <= last:
            rows.append((d.isoformat(), counts[r].get(d.isoformat(), 0)))
            d += datetime.timedelta(days=1)
        write(os.path.join(OUT_DIR, r + ".csv.gz"), rows)
    pub = ("taeglich (Federal Register erscheint an jedem US-Bankarbeitstag ab 6 Uhr ET; das Dokument ist an "
           "seinem gedruckten Publikationsdatum oeffentlich, Beleg: federalregister.gov/reader-aids)")
    url = BASE + "?conditions%5Bagencies%5D%5B%5D=" + AGENCY
    meta = {
        "einleitungen": {"einheit": "Anzahl Dokumente",
                         "beschreibung": "Taegliche Anzahl Federal-Register-Bekanntmachungen der USITC zur Einleitung "
                                         "von Section-337-Untersuchungen (Titel 'Certain ...; Notice of Investigation/"
                                         "Institution of Investigation'), 0 an Tagen ohne Bekanntmachung.",
                         "quelle_url": url, "verdichtung": "Anzahl je Publikationsdatum (Titelfilter)",
                         "publikation": pub, "verfuegbar_nach_tagen": 0, "revidiert": False},
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
