#!/usr/bin/env python3
import datetime
import gzip
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ID = "accc_produktrueckrufe_australien"
BASE = "https://www.productsafety.gov.au/views/ajax"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
PER_PAGE = 100
# Vor 2003 nur lueckenhaft nachgetragene Altbestaende (1986-1997 je 0-4 im Jahr,
# Uebernahme aus dem Vorgaengersystem 1998-2002 mit Sammeltagen 16./19.8.2002).
START = "2003-01-01"
WORKERS = 3
PARAMS = {
    "_wrapper_format": "drupal_ajax",
    "view_name": "psa_listing_search",
    "view_display_id": "listing_search_date_range_filter",
    "view_args": "psa_recall",
    "view_path": "/node/196",
    "pager_element": "0",
    "items_per_page": str(PER_PAGE),
}
CARD = re.compile(
    r'data_url="([^"]+)"[^>]*data_type="psa-recall".*?'
    r'field--name-field-psa-recall-published-date.*?datetime="(\d{4}-\d{2}-\d{2})T',
    re.S,
)


def fetch(page, per_page=PER_PAGE, tries=4):
    q = dict(PARAMS)
    q["items_per_page"] = str(per_page)
    if page:
        q["page"] = str(page)
    url = BASE + "?" + urllib.parse.urlencode(q)
    for i in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            cmds = d.values() if isinstance(d, dict) else d
            return "".join(str(c.get("data", "")) for c in cmds if isinstance(c, dict))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def gzip_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        text = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        text.write("datum,wert\n")
        for d, v in rows:
            text.write("%s,%s\n" % (d, v))
        text.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    today = datetime.datetime.now(datetime.timezone.utc).date()
    seen = {}
    first = fetch(0)
    m = re.search(r"([0-9][0-9,]*) items", first)
    if not m:
        raise RuntimeError("Gesamtzahl nicht gefunden")
    total = int(m.group(1).replace(",", ""))
    n_pages = (total + PER_PAGE - 1) // PER_PAGE

    # Einzelne Seiten liefert der Server zuweilen leer; diese Bereiche werden
    # mit kleinerer Seitengroesse (50, dann 25) erneut abgedeckt.
    def cover(page):
        out = []
        html = first if page == 0 else fetch(page)
        c = CARD.findall(html)
        if c:
            return c
        for sub in (2 * page, 2 * page + 1):
            c = CARD.findall(fetch(sub, 50))
            if c:
                out += c
                continue
            for sub2 in (2 * sub, 2 * sub + 1):
                out += CARD.findall(fetch(sub2, 25))
        return out

    # Neue Rueckrufe waehrend des Abrufs verschieben die Seitengrenzen; dann
    # fallen einzelne Eintraege durch. Bis zu zwei weitere Durchgaenge werden
    # vereinigt (Lernrunde 2026-11-21: 8273 von 8280 in 2 Laeufen).
    for durchgang in range(3):
        with ThreadPoolExecutor(WORKERS) as ex:
            for cards in ex.map(cover, range(n_pages)):
                for url, day in cards:
                    seen.setdefault(url, day)
        if len(seen) >= total - 5:
            break
        time.sleep(5)
    if len(seen) < total - 5:
        raise RuntimeError("unvollstaendig: %d von %d Rueckrufen" % (len(seen), total))

    counts = {}
    for day in seen.values():
        counts[day] = counts.get(day, 0) + 1
    first_day = datetime.date.fromisoformat(START)
    rows = []
    cur = first_day
    while cur <= today:
        iso = cur.isoformat()
        rows.append((iso, counts.get(iso, 0)))
        cur += datetime.timedelta(days=1)
    gzip_write(os.path.join(OUT_DIR, "anzahl_rueckrufe.csv.gz"), rows)

    meta = {
        "anzahl_rueckrufe": {
            "einheit": "Anzahl Rueckrufe",
            "beschreibung": (
                "Taegliche Anzahl der von der australischen Wettbewerbs- und "
                "Verbraucherbehoerde ACCC auf productsafety.gov.au veroeffentlichten "
                "Produktrueckrufe ab 2003 (vorher lueckenhafter Altbestand; alle Kategorien: Fahrzeuge, Elektrogeraete, Spielzeug, "
                "Lebensmittel u.a.), Datum = Veroeffentlichungsdatum (published date, "
                "australische Ortszeit), 0 an Tagen ohne Rueckruf. Zaehlung je Rueckruf-"
                "Detailseite (eindeutige URL). Mechanismus: Rueckrufe globaler Hersteller "
                "langlebiger Gueter (XLY, ff_durbl); Replikation von cpsc_ruckrufe."
            ),
            "quelle_url": "https://www.productsafety.gov.au/recalls",
            "verdichtung": "Anzahl Rueckrufe je Kalendertag (Veroeffentlichungsdatum)",
            "publikation": (
                "taeglich: Rueckrufe erscheinen am Veroeffentlichungstag in der Rueckrufliste "
                "von productsafety.gov.au (beobachtet 19.11.2026: juengster Eintrag 18.11.2026); "
                "australischer Tag liegt vor dem US-Handelstag, 1 Tag Sicherheitsabstand"
            ),
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
