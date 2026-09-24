#!/usr/bin/env python3
import csv
import gzip
import io
import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

ID = "treasury_yield_curve"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
BASE = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/%d/all"

# "10 Yr" wird ausgeschlossen (Dublette zu FRED DGS10, bereits im Indikatorraum U2).
EXCLUDE_TENORS = {"10 Yr"}

TENOR_TO_ID = {
    "1 Mo": "m1", "1.5 Month": "m1_5", "2 Mo": "m2", "3 Mo": "m3",
    "4 Mo": "m4", "6 Mo": "m6", "1 Yr": "y1", "2 Yr": "y2",
    "3 Yr": "y3", "5 Yr": "y5", "7 Yr": "y7", "10 Yr": "y10",
    "20 Yr": "y20", "30 Yr": "y30",
}


def fetch_year(year, attempts=3):
    url = BASE % year + (
        "?type=daily_treasury_yield_curve&field_tdr_date_value=%d&page&_format=csv" % year
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last_exc = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8-sig")
            break
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(2 * (attempt + 1))
    else:
        raise RuntimeError("Jahr %d nach %d Versuchen fehlgeschlagen: %s" % (year, attempts, last_exc))
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {}
    header = [h.strip().strip('"') for h in rows[0]]
    by_tenor = {h: {} for h in header[1:]}
    for r in rows[1:]:
        if not r or not r[0]:
            continue
        m, d, y = r[0].split("/")
        iso = "%04d-%02d-%02d" % (int(y), int(m), int(d))
        for i, tenor in enumerate(header[1:], start=1):
            if i < len(r) and r[i].strip() != "":
                by_tenor[tenor][iso] = float(r[i])
    return by_tenor


def fetch_all():
    combined = {}
    this_year = date.today().year
    years = list(range(1990, this_year + 1))
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(fetch_year, y): y for y in years}
        failed = []
        for fut in as_completed(futures):
            year = futures[fut]
            try:
                by_tenor = fut.result()
            except Exception as exc:
                failed.append((year, exc))
                continue
            for tenor, series in by_tenor.items():
                if tenor in EXCLUDE_TENORS:
                    continue
                combined.setdefault(tenor, {}).update(series)
    if failed:
        # Kein Teilergebnis schreiben: bestehende Dateien sollen bei Fehlern
        # unveraendert stehen bleiben (siehe run_all.py), statt sie durch eine
        # unvollstaendige Historie (z.B. fehlendes laufendes Jahr) zu ersetzen.
        raise RuntimeError(
            "Abruf unvollstaendig, %d Jahr(e) fehlgeschlagen: %s"
            % (len(failed), ", ".join("%d (%s)" % (y, e) for y, e in failed))
        )
    return combined


def write_series(tenor, series):
    reihe_id = TENOR_TO_ID.get(tenor)
    if reihe_id is None:
        return None
    dates = sorted(series.keys())
    if len(dates) < 500 or dates[0] > "2015-12-31":
        return None
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "%s.csv.gz" % reihe_id)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        w = io.TextIOWrapper(gz, encoding="utf-8")
        w.write("datum,wert\n")
        for d in dates:
            w.write("%s,%s\n" % (d, series[d]))
        w.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    return reihe_id, dates[0], dates[-1], len(dates)


def main():
    combined = fetch_all()
    os.makedirs(OUT_DIR, exist_ok=True)
    written = {}
    meta = {}
    for tenor, series in combined.items():
        result = write_series(tenor, series)
        if result is None:
            continue
        reihe_id, first, last, n = result
        written[reihe_id] = (tenor, first, last, n)
        meta[reihe_id] = {
            "einheit": "Prozent p.a.",
            "beschreibung": "US-Treasury Par-Zinsstrukturkurve, Laufzeit %s (CMT, taeglicher Schlusswert)" % tenor,
            "quelle_url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv",
            "verdichtung": "keine (bereits taeglicher Einzelwert)",
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
        }
    with open(os.path.join(OUT_DIR, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False, sort_keys=True)
    for reihe_id, (tenor, first, last, n) in sorted(written.items()):
        print("OK %s (%s): %s..%s, %d Werte" % (reihe_id, tenor, first, last, n))


if __name__ == "__main__":
    main()
