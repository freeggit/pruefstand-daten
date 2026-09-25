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

# "10 Yr" wird als eigene Reihe ausgeschlossen (Dublette zu FRED DGS10, bereits im
# Indikatorraum U2), bleibt aber intern fuer die Berechnung von "niveau"/"steilheit" erhalten.
EXCLUDE_TENORS = {"10 Yr"}

TENOR_TO_ID = {
    "1 Mo": "m1", "1.5 Month": "m1_5", "2 Mo": "m2", "3 Mo": "m3",
    "4 Mo": "m4", "6 Mo": "m6", "1 Yr": "y1", "2 Yr": "y2",
    "3 Yr": "y3", "5 Yr": "y5", "7 Yr": "y7", "10 Yr": "y10",
    "20 Yr": "y20", "30 Yr": "y30",
}

# Zusatz 3 (Redundanz begrenzen): Zinskurve auf 3 Reihen verdichten. Bei der
# US-Kurve liegen "niveau" (10J, DGS10) und "steilheit" (10J-2J, T10Y2Y) schon
# im Spiegel main (K6) -- daher bleibt dort nur "kurz" aktiv, der Rest ruhend.
KURZ_TENOR = "1 Mo"
NIVEAU_TENOR = "10 Yr"
STEIL_KURZ_TENOR = "2 Yr"


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
                # EXCLUDE_TENORS wird erst beim Schreiben einzelner Reihen
                # angewendet; "10 Yr" bleibt hier fuer "niveau" erhalten.
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


def write_csv(reihe_id, series):
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
    return dates[0], dates[-1], len(dates)


def diff_series(a, b):
    common = sorted(set(a) & set(b))
    return {d: a[d] - b[d] for d in common}


def main():
    combined = fetch_all()
    os.makedirs(OUT_DIR, exist_ok=True)
    written = {}
    meta = {}

    for tenor, series in combined.items():
        reihe_id = TENOR_TO_ID.get(tenor)
        if reihe_id is None or tenor in EXCLUDE_TENORS:
            continue
        result = write_csv(reihe_id, series)
        if result is None:
            continue
        first, last, n = result
        written[reihe_id] = (tenor, first, last, n)
        meta[reihe_id] = {
            "einheit": "Prozent p.a.",
            "beschreibung": "US-Treasury Par-Zinsstrukturkurve, Laufzeit %s (CMT, taeglicher Schlusswert)" % tenor,
            "quelle_url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv",
            "verdichtung": "keine (bereits taeglicher Einzelwert)",
            "publikation": 'taeglich (Daily Treasury Par Yield Curve Rates, Veroeffentlichung am selben Geschaeftstagabend)',
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
            "status": "ruhend",
        }

    # Zusatz 3: verdichtete 3 Reihen. "niveau" und "steilheit" sind bei der
    # US-Kurve Dubletten zu main (DGS10, T10Y2Y) -> ruhend; nur "kurz" aktiv.
    niveau = combined.get(NIVEAU_TENOR, {})
    kurz_basis = combined.get(KURZ_TENOR, {})
    steil = diff_series(niveau, combined.get(STEIL_KURZ_TENOR, {}))

    for reihe_id, series, status, beschr in (
        ("niveau", niveau, "ruhend",
         "US-Treasury Zinsniveau, 10 Jahre (Dublette FRED DGS10 in main, hier ruhend)"),
        ("steilheit", steil, "ruhend",
         "US-Treasury Zinskurve Steilheit, 10J minus 2J (Dublette FRED T10Y2Y in main, hier ruhend)"),
        ("kurz", kurz_basis, "aktiv",
         "US-Treasury kurzes Ende der Zinskurve, Laufzeit 1 Mo (CMT, taeglicher Schlusswert)"),
    ):
        result = write_csv(reihe_id, series)
        if result is None:
            continue
        first, last, n = result
        written[reihe_id] = (reihe_id, first, last, n)
        meta[reihe_id] = {
            "einheit": "Prozent p.a." if reihe_id != "steilheit" else "Prozentpunkte",
            "beschreibung": beschr,
            "quelle_url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv",
            "verdichtung": "keine (Differenz zweier taeglicher Einzelwerte)" if reihe_id == "steilheit" else "keine (bereits taeglicher Einzelwert)",
            "publikation": 'taeglich (Daily Treasury Par Yield Curve Rates, Veroeffentlichung am selben Geschaeftstagabend)',
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
            "status": status,
        }

    with open(os.path.join(OUT_DIR, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False, sort_keys=True)
    for reihe_id, (tenor, first, last, n) in sorted(written.items()):
        print("OK %s (%s): %s..%s, %d Werte [%s]" % (reihe_id, tenor, first, last, n, meta[reihe_id]["status"]))


if __name__ == "__main__":
    main()
