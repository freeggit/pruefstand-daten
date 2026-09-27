#!/usr/bin/env python3
import datetime
import gzip
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

ID = "fda_ruckrufe"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
MIN_YEAR = 2000  # verwirft vereinzelte fehlerhafte Datumsfelder (z.B. Jahr 0212, 1930)

KATEGORIEN = {
    "arzneimittel": {
        "url": "https://api.fda.gov/drug/enforcement.json",
        "beschreibung": "Taegliche Anzahl von FDA-Arzneimittelrueckrufen (recall_initiation_date), Gesundheitssektor",
    },
    "lebensmittel": {
        "url": "https://api.fda.gov/food/enforcement.json",
        "beschreibung": "Taegliche Anzahl von FDA-Lebensmittelrueckrufen (recall_initiation_date), Basiskonsumsektor",
    },
    "medizinprodukte": {
        "url": "https://api.fda.gov/device/enforcement.json",
        "beschreibung": "Taegliche Anzahl von FDA-Medizinprodukterueckrufen (recall_initiation_date), Gesundheitssektor",
    },
}


def fetch(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"results": []}
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


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    meta = {}
    for reihe, cfg in KATEGORIEN.items():
        url = cfg["url"] + "?" + urllib.parse.urlencode(
            {"count": "recall_initiation_date", "limit": 1000}
        )
        d = fetch(url)
        last_updated = d.get("meta", {}).get("last_updated")
        counts = {}
        for r in d.get("results", []):
            raw = r.get("time", "")
            if len(raw) != 8 or not raw.isdigit():
                continue
            year = int(raw[0:4])
            if year < MIN_YEAR:
                continue
            iso = "%s-%s-%s" % (raw[0:4], raw[4:6], raw[6:8])
            try:
                datetime.date.fromisoformat(iso)
            except ValueError:
                continue
            counts[iso] = counts.get(iso, 0) + int(r.get("count", 0))

        if not counts:
            raise RuntimeError("keine Rueckrufdaten fuer %s" % reihe)

        first_day = min(datetime.date.fromisoformat(x) for x in counts)
        max_seen = max(datetime.date.fromisoformat(x) for x in counts)
        today = datetime.datetime.now(datetime.timezone.utc).date()
        if last_updated:
            try:
                cutoff = datetime.date.fromisoformat(last_updated)
            except ValueError:
                cutoff = max_seen
        else:
            cutoff = max_seen
        # bis zum von der API gemeldeten Aktualisierungsstand zero-fillen (nicht nur
        # bis zum letzten Treffer), sonst waere K5 nicht pruefbar.
        last_day = max(min(cutoff, today), max_seen)
        rows = []
        day = first_day
        while day <= last_day:
            iso = day.isoformat()
            rows.append((iso, counts.get(iso, 0)))
            day += datetime.timedelta(days=1)

        gzip_write(os.path.join(OUT_DIR, "%s.csv.gz" % reihe), rows)

        meta[reihe] = {
            "einheit": "Anzahl Rueckrufe",
            "beschreibung": cfg["beschreibung"],
            "quelle_url": cfg["url"],
            "verdichtung": "Summe der Rueckrufmeldungen je Kalendertag (recall_initiation_date)",
            "publikation": "woechentlich (FDA Enforcement Reports werden wochenweise veroeffentlicht; recall_initiation_date ist das taegliche Ereignisdatum, siehe https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts)",
            "verfuegbar_nach_tagen": 8,
            "revidiert": False,
        }

    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
