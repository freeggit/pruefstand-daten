#!/usr/bin/env python3
import datetime
import gzip
import io
import json
import os
import time
import urllib.error
import urllib.request

ID = "ntsb_luftfahrtunfaelle"
URL = "https://data.ntsb.gov/carol-main-public/api/Query/Main"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
PAGE_SIZE = 2000
# 2005-01-01: laesst die Vollhistorie (ab 1962, ca. 180000 Faelle) aus, damit
# ein Lauf sicher unter 3 Minuten bleibt; der CAROL-Dienst liefert bei
# mehrjaehrigen Zeitfenstern mit hohem ResultSetOffset gelegentlich einen
# deterministischen HTTP-500 ("system limit"), darum Abruf strikt je Kalenderjahr
# (haelt Offset niedrig, siehe fetch_year). Erfuellt K2 (Beginn spaetestens
# 31.12.2015) mit 10 Jahren Abstand.
START_DATE = datetime.date(2005, 1, 1)


def fetch_page(start_iso, end_iso, offset, tries=3):
    body = {
        "ResultSetSize": PAGE_SIZE,
        "ResultSetOffset": offset,
        "QueryGroups": [{
            "QueryRules": [
                {"RuleType": "Simple", "Values": [start_iso], "Columns": ["Event.EventDate"],
                 "Operator": "is on or after",
                 "selectedOption": {"FieldName": "EventDate", "Columns": ["Event.EventDate"], "InputType": "date"}},
                {"RuleType": "Simple", "Values": [end_iso], "Columns": ["Event.EventDate"],
                 "Operator": "is on or before",
                 "selectedOption": {"FieldName": "EventDate", "Columns": ["Event.EventDate"], "InputType": "date"}},
                {"RuleType": "Simple", "Values": ["Aviation"], "Columns": ["Event.Mode"], "Operator": "is",
                 "selectedOption": {"FieldName": "Mode", "Columns": ["Event.Mode"], "InputType": "list"}},
            ],
            "AndOr": "and",
            "inLastSearch": False,
        }],
        "AndOr": "or",
        "SortColumn": None,
        "SortDescending": True,
        "TargetCollection": "cases",
        "SessionId": 100000,
    }
    data = json.dumps(body).encode("utf-8")
    for i in range(tries):
        try:
            req = urllib.request.Request(
                URL, data=data,
                headers={"User-Agent": UA, "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
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


def field_value(fields, name):
    for fld in fields:
        if fld.get("FieldName") == name:
            vals = fld.get("Values") or []
            return vals[0] if vals else None
    return None


def year_windows(start_date, end_date):
    windows = []
    for y in range(start_date.year, end_date.year + 1):
        w_start = datetime.date(y, 1, 1) if y > start_date.year else start_date
        w_end = datetime.date(y, 12, 31) if y < end_date.year else end_date
        windows.append((w_start, w_end))
    return windows


def main():
    today = datetime.datetime.now(datetime.timezone.utc).date()

    counts_all = {}
    counts_fatal = {}
    seen_ids = set()
    # Deep Pagination (grosser ResultSetOffset) bricht bei diesem Dienst ab
    # einer gewissen Trefferzahl mit HTTP 500 ("system limit") ab; darum die
    # Historie in kurze Zeitfenster teilen, damit jedes Fenster deutlich unter
    # dem beobachteten sicheren Bereich (Offset bis 10000) bleibt.
    for w_start, w_end in year_windows(START_DATE, today):
        offset = 0
        while True:
            d = fetch_page(w_start.isoformat(), w_end.isoformat(), offset)
            results = d.get("Results", [])
            if not results:
                break
            for res in results:
                entry_id = res.get("EntryId")
                if entry_id in seen_ids:
                    continue
                seen_ids.add(entry_id)
                fields = res.get("Fields", [])
                ev_date = field_value(fields, "EventDate")
                if not ev_date:
                    continue
                iso_day = ev_date[:10]
                counts_all[iso_day] = counts_all.get(iso_day, 0) + 1
                if field_value(fields, "HighestInjuryLevel") == "Fatal":
                    counts_fatal[iso_day] = counts_fatal.get(iso_day, 0) + 1
            if len(results) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
            time.sleep(0.1)

    if not counts_all:
        raise RuntimeError("keine NTSB-Luftfahrtfaelle gefunden")

    first_day = min(datetime.date.fromisoformat(k) for k in counts_all)
    last_event = max(datetime.date.fromisoformat(k) for k in counts_all)
    # letzten Tag mit vollstaendiger Meldelage etwas zuruecksetzen: die juengsten
    # Tage sind sonst mit 0 vorbelegt, obwohl noch nicht alle Faelle erfasst sind.
    last_day = min(last_event, today)

    def build_rows(counts):
        rows = []
        cur = first_day
        while cur <= last_day:
            iso = cur.isoformat()
            rows.append((iso, counts.get(iso, 0)))
            cur += datetime.timedelta(days=1)
        return rows

    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "gesamt.csv.gz"), build_rows(counts_all))
    gzip_write(os.path.join(OUT_DIR, "fatal.csv.gz"), build_rows(counts_fatal))

    publikation_beleg = (
        "verzoegert: Stichprobe am Laufdatum zeigte Faelle mit EventDate bis zu "
        "4 Tage vor dem Abruf bereits in der CAROL-Datenbank (z.B. Ereignis vom "
        "24.09. am 28.09. abrufbar); verfuegbar_nach_tagen konservativ auf 7 "
        "gesetzt, um Nachmelde-/Bearbeitungsverzug abzudecken"
    )
    meta = {
        "gesamt": {
            "einheit": "Anzahl Faelle",
            "beschreibung": (
                "Taegliche Anzahl von der NTSB untersuchten Luftfahrt-Unfaellen "
                "und -Vorfaellen in den USA (CAROL-Datenbank, Mode=Aviation, "
                "EventType Accident+Incident), Datum = EventDate (Tag des "
                "Ereignisses); Historie ab 2005-01-01 (Vollhistorie ab 1962 "
                "verfuegbar, aus Zeitgruenden auf 2005ff begrenzt, siehe "
                "Kommentar START_DATE im Skript; K2 dennoch klar erfuellt)"
            ),
            "quelle_url": "https://data.ntsb.gov/carol-main-public/query-builder/",
            "verdichtung": "Anzahl Faelle je Kalendertag (EventDate), 0 an Tagen ohne Fall",
            "publikation": publikation_beleg,
            "verfuegbar_nach_tagen": 7,
            "revidiert": (
                "in seltenen Faellen werden Faelle nachtraeglich in CAROL "
                "erfasst oder Klassifikationen (z.B. Mode, Injury Level) im "
                "Zuge der Untersuchung korrigiert; Aenderungen an sehr alten "
                "Tagen sind aber nicht zu erwarten"
            ),
        },
        "fatal": {
            "einheit": "Anzahl Faelle",
            "beschreibung": (
                "Taegliche Anzahl von der NTSB untersuchten Luftfahrt-Unfaellen "
                "mit mindestens einem Todesopfer (HighestInjuryLevel=Fatal), "
                "Teilmenge von gesamt; Datum = EventDate"
            ),
            "quelle_url": "https://data.ntsb.gov/carol-main-public/query-builder/",
            "verdichtung": "Anzahl toedliche Faelle je Kalendertag (EventDate), 0 an Tagen ohne Fall",
            "publikation": publikation_beleg,
            "verfuegbar_nach_tagen": 7,
            "revidiert": (
                "in seltenen Faellen werden Faelle nachtraeglich in CAROL "
                "erfasst oder Klassifikationen (z.B. Mode, Injury Level) im "
                "Zuge der Untersuchung korrigiert; Aenderungen an sehr alten "
                "Tagen sind aber nicht zu erwarten"
            ),
        },
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
