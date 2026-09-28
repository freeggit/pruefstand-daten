#!/usr/bin/env python3
import datetime
import gzip
import io
import json
import os
import time
import urllib.error
import urllib.request
import zipfile

ID = "nhtsa_ruckrufe"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)

# NHTSA Office of Defects Investigation (ODI), Flat-File-Export "Recalls"
# (alle Fahrzeug-/Ausruestungs-Rueckrufkampagnen seit 1966), TAB-getrennt,
# keine Kopfzeile. Zwei Dateien decken zusammen die Gesamthistorie ab.
FILES = [
    "https://static.nhtsa.gov/odi/ffdd/rcl/FLAT_RCL_PRE_2010.zip",
    "https://static.nhtsa.gov/odi/ffdd/rcl/FLAT_RCL_POST_2010.zip",
]

# Feldindizes (0-basiert) im Flat File RCL.txt:
# 1 CAMPNO, 11 POTAFF, 15 RCDATE (Part 573 Bericht bei NHTSA eingegangen)
IDX_CAMPNO = 1
IDX_POTAFF = 11
IDX_RCDATE = 15


def fetch_bytes(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


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


def parse_date(s):
    return datetime.date(int(s[0:4]), int(s[4:6]), int(s[6:8]))


def main():
    # CAMPNO -> (datum, potaff); eine Kampagne kann tausende Zeilen (je Modell)
    # haben, RCDATE und POTAFF sind je Kampagne konstant -> je CAMPNO einmal zaehlen.
    campaigns = {}
    for url in FILES:
        raw = fetch_bytes(url)
        z = zipfile.ZipFile(io.BytesIO(raw))
        name = z.namelist()[0]
        with z.open(name) as f:
            for line in f:
                parts = line.rstrip(b"\r\n").split(b"\t")
                if len(parts) <= IDX_RCDATE:
                    continue
                campno = parts[IDX_CAMPNO]
                if campno in campaigns:
                    continue
                rcdate = parts[IDX_RCDATE].decode(errors="replace")
                if len(rcdate) != 8 or not rcdate.isdigit():
                    continue
                try:
                    dt = parse_date(rcdate)
                except ValueError:
                    continue
                pot_raw = parts[IDX_POTAFF].decode(errors="replace").strip()
                try:
                    pot = int(pot_raw) if pot_raw else 0
                except ValueError:
                    pot = 0
                campaigns[campno] = (dt.isoformat(), pot)

    if not campaigns:
        raise RuntimeError("keine Rueckrufkampagnen gefunden")

    anzahl = {}
    einheiten = {}
    for _campno, (iso, pot) in campaigns.items():
        anzahl[iso] = anzahl.get(iso, 0) + 1
        einheiten[iso] = einheiten.get(iso, 0) + pot

    first_day = min(datetime.date.fromisoformat(k) for k in anzahl)
    last_event = max(datetime.date.fromisoformat(k) for k in anzahl)
    today = datetime.datetime.now(datetime.timezone.utc).date()
    last_day = min(max(last_event, today), today)

    rows_anzahl = []
    rows_einheiten = []
    cur = first_day
    while cur <= last_day:
        iso = cur.isoformat()
        rows_anzahl.append((iso, anzahl.get(iso, 0)))
        rows_einheiten.append((iso, einheiten.get(iso, 0)))
        cur += datetime.timedelta(days=1)

    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "anzahl.csv.gz"), rows_anzahl)
    gzip_write(os.path.join(OUT_DIR, "einheiten_betroffen.csv.gz"), rows_einheiten)

    publikation = (
        "taeglich: RCDATE (Eingang des Part-573-Defektberichts bei der NHTSA) "
        "gegen DATEA (Erstellungsdatum des oeffentlichen Datensatzes) auf einer "
        "Stichprobe von rd. 15000 Kampagnen (POST_2010) verglichen: Median 1 Tag, "
        "84% innerhalb 3 Tagen; verfuegbar_nach_tagen konservativ auf 3 gesetzt"
    )
    meta = {
        "anzahl": {
            "einheit": "Anzahl Rueckrufkampagnen",
            "beschreibung": (
                "Taegliche Anzahl neuer NHTSA-Fahrzeug-/Ausruestungsrueckrufkampagnen "
                "(Office of Defects Investigation, Flat File RCL), je Kampagnennummer "
                "(CAMPNO) einmal gezaehlt, Datum = RCDATE (Eingang des Part-573-"
                "Defekt-/Non-Compliance-Berichts bei der NHTSA), 0 an Tagen ohne "
                "neue Kampagne. Mechanismus: gehaeufte Sicherheitsrueckrufe grosser "
                "Autohersteller koennen kurzfristig auf Qualitaets-/Kostenprobleme "
                "im Automobilsektor hindeuten (naeherungsweise XLY/XLI)."
            ),
            "quelle_url": "https://www.nhtsa.gov/nhtsa-datasets-and-apis",
            "verdichtung": "Anzahl Kampagnen je Kalendertag (RCDATE), CAMPNO-dedupliziert",
            "publikation": publikation,
            "verfuegbar_nach_tagen": 3,
            "revidiert": False,
        },
        "einheiten_betroffen": {
            "einheit": "Anzahl potenziell betroffener Einheiten",
            "beschreibung": (
                "Tagessumme der von NHTSA-Rueckrufkampagnen potenziell betroffenen "
                "Einheiten (Feld POTAFF), je Kampagnennummer einmal gezaehlt, "
                "Datum = RCDATE. 0 an Tagen ohne neue Kampagne."
            ),
            "quelle_url": "https://www.nhtsa.gov/nhtsa-datasets-and-apis",
            "verdichtung": "Summe POTAFF je Kalendertag (RCDATE), CAMPNO-dedupliziert",
            "publikation": publikation,
            "verfuegbar_nach_tagen": 3,
            "revidiert": False,
        },
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
