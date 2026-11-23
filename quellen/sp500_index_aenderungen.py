#!/usr/bin/env python3
import datetime
import gzip
import io
import json
import os
import re
import html
import urllib.request

ID = "sp500_index_aenderungen"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
EXPORT_URL = "https://en.wikipedia.org/wiki/Special:Export/Historical_components_of_the_S%26P_500"
ARTICLE_URL = "https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500"

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}
DATE_PAT = re.compile(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s*(\d{4})')


RAW_URL = "https://en.wikipedia.org/w/index.php?title=Historical_components_of_the_S%26P_500&action=raw"


def _get(url, versuche=3):
    """Abruf mit Beachtung von HTTP 429 (Retry-After, hoechstens 90 s)."""
    import time
    import urllib.error
    letzter = None
    for i in range(versuche):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            letzter = e
            if e.code != 429 or i == versuche - 1:
                raise
            try:
                warte = int(e.headers.get("Retry-After") or 0)
            except ValueError:
                warte = 0
            time.sleep(min(90, max(15, warte)) * (i + 1))
    raise letzter


def fetch_wikitext():
    # Zuerst Rohtext (action=raw), bei Fehler Special:Export; beide liefern denselben Wikitext.
    try:
        text = _get(RAW_URL)
        if "wikitable" in text:
            return text
    except Exception:
        pass
    data = _get(EXPORT_URL)
    m = re.search(r'<text[^>]*>(.*)</text>', data, re.S)
    return html.unescape(m.group(1))


def bestand_aktuell():
    """True, wenn die Datei schon bis heute reicht (Lauf heute schon erfolgreich)."""
    pfad = os.path.join(OUT_DIR, "anzahl_aenderungen.csv.gz")
    try:
        with gzip.open(pfad, "rt", encoding="utf-8") as f:
            letzte = None
            for zeile in f:
                letzte = zeile
        heute = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        return bool(letzte) and letzte.split(",")[0] >= heute
    except (OSError, EOFError):
        return False


def parse_change_counts(wikitext):
    start = wikitext.find('wikitable')
    end = wikitext.find('|}', start)
    table = wikitext[start:end]
    rows = table.split('\n|-')
    counts = {}
    parsed_rows = 0
    for row in rows:
        lines = [ln.strip() for ln in row.split('\n') if ln.strip().startswith('||')]
        if not lines:
            continue
        date_field = lines[0][2:].strip()
        m = DATE_PAT.search(date_field)
        if not m:
            continue
        month = MONTHS[m.group(1)]
        day = int(m.group(2))
        year = int(m.group(3))
        try:
            d = datetime.date(year, month, day)
        except ValueError:
            continue
        iso = d.isoformat()
        counts[iso] = counts.get(iso, 0) + 1
        parsed_rows += 1
    return counts, parsed_rows


def gzip_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        text = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        text.write("datum,wert\n")
        for iso, v in rows:
            text.write("%s,%s\n" % (iso, v))
        text.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    if bestand_aktuell():
        # Tabelle aendert sich hoechstens taeglich; weitere Abfragen am selben Tag erzeugen nur 429.
        return
    wikitext = fetch_wikitext()
    counts, parsed_rows = parse_change_counts(wikitext)
    if parsed_rows < 300:
        raise RuntimeError("Nur %d Aenderungszeilen geparst, erwartet >=300 (Parser-Regression?)" % parsed_rows)

    first_day = datetime.date.fromisoformat(min(counts))
    today = datetime.datetime.now(datetime.timezone.utc).date()

    rows = []
    d = first_day
    one = datetime.timedelta(days=1)
    while d <= today:
        iso = d.isoformat()
        rows.append((iso, counts.get(iso, 0)))
        d += one

    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "anzahl_aenderungen.csv.gz"), rows)

    meta = {
        "anzahl_aenderungen": {
            "einheit": "Anzahl Indexaenderungs-Paare",
            "beschreibung": (
                "Anzahl der Aufnahme/Entfernung-Paare im S&P 500 je Wirksamkeitsdatum (Effective Date), "
                "gezaehlt aus der von Freiwilligen gepflegten Wikipedia-Tabelle 'Historical components of "
                "the S&P 500' (Tabelle id=changes), die die Pressemitteilungen von S&P Dow Jones Indices "
                "nachtraegt. Index-Effekt (Shleifer 1986, Harris/Gurel 1986): um Wirksamkeitstag entstehen "
                "mechanische Kauf-/Verkaufsfluesse passiver Fonds. Hinweis: die Tabelle ist community-gepflegt; "
                "vereinzelte rueckwirkende Korrekturen von Transkriptionsfehlern (z.B. Ticker-Umbenennungen "
                "faelschlich als Indexwechsel gezaehlt) sind moeglich, keine methodische Revision der "
                "zugrundeliegenden SPDJI-Ereignisse selbst."
            ),
            "quelle_url": ARTICLE_URL,
            "verdichtung": "Anzahl Tabellenzeilen (Aenderungs-Paare) je Kalendertag (Wirksamkeitsdatum), 0 an Tagen ohne Eintrag",
            "publikation": (
                "verzoegert (community-gepflegte Wikipedia-Tabelle, keine feste Frist; Beleg: bei Abruf lag "
                "der juengste Tabelleneintrag rund 5 Kalendertage vor dem Abrufdatum, siehe Fortschrittsnotiz "
                "im Katalog)"
            ),
            "verfuegbar_nach_tagen": 7,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
