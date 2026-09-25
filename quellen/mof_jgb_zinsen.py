#!/usr/bin/env python3
import gzip
import io
import json
import os
import urllib.request

ID = "mof_jgb_zinsen"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)

HIST_URL = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv"
CURRENT_URL = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"

TENOR_TO_ID = {
    "1Y": "y1", "2Y": "y2", "3Y": "y3", "4Y": "y4", "5Y": "y5",
    "6Y": "y6", "7Y": "y7", "8Y": "y8", "9Y": "y9", "10Y": "y10",
    "15Y": "y15", "20Y": "y20", "25Y": "y25", "30Y": "y30", "40Y": "y40",
}

# Zusatz 3 (Redundanz begrenzen): Zinskurve auf 3 Reihen verdichten. Keine
# JGB-Laufzeit unter 1Y verfuegbar -> "kurz" = 1 Jahr (Regel "sonst 1 Jahr").
NIVEAU_TENOR = "10Y"
STEIL_KURZ_TENOR = "2Y"
KURZ_TENOR = "1Y"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("shift_jis")


def parse(text):
    lines = [l for l in text.splitlines() if l.strip()]
    header = lines[0].split(",")
    if header[0] != "Date":
        # erste Zeile ist Titel ("Interest Rate,,,,(Unit : %)"), zweite die echte Kopfzeile
        header = lines[1].split(",")
        data_lines = lines[2:]
    else:
        data_lines = lines[1:]
    tenors = header[1:]
    by_tenor = {t: {} for t in tenors}
    for line in data_lines:
        parts = line.split(",")
        if not parts or not parts[0].strip() or "※" in line:
            continue
        y, m, d = parts[0].split("/")
        iso = "%04d-%02d-%02d" % (int(y), int(m), int(d))
        for i, tenor in enumerate(tenors, start=1):
            if i >= len(parts):
                continue
            v = parts[i].strip()
            if v in ("", "-"):
                continue
            try:
                by_tenor[tenor][iso] = float(v)
            except ValueError:
                continue
    return by_tenor


def gzip_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for d, v in rows:
            t.write("%s,%s\n" % (d, v))
        t.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def diff_series(a, b):
    common = sorted(set(a) & set(b))
    return {d: a[d] - b[d] for d in common}


def write_reihe(meta, reihe_id, series, status, einheit, beschreibung, verdichtung):
    dates = sorted(series.keys())
    if len(dates) < 500 or dates[0] > "2015-12-31":
        return None
    rows = [(d, series[d]) for d in dates]
    gzip_write(os.path.join(OUT_DIR, reihe_id + ".csv.gz"), rows)
    meta[reihe_id] = {
        "einheit": einheit,
        "beschreibung": beschreibung,
        "quelle_url": HIST_URL,
        "verdichtung": verdichtung,
        "publikation": 'taeglich (Ministry of Finance Japan veroeffentlicht Referenzsaetze am selben Geschaeftstag)',
        "verfuegbar_nach_tagen": 1,
        "revidiert": False,
        "status": status,
    }
    print("OK %s: %s..%s, %d Werte [%s]" % (reihe_id, dates[0], dates[-1], len(dates), status))
    return True


def main():
    hist = parse(fetch(HIST_URL))
    current = parse(fetch(CURRENT_URL))

    combined = {}
    for tenor in TENOR_TO_ID:
        merged = dict(hist.get(tenor, {}))
        merged.update(current.get(tenor, {}))
        combined[tenor] = merged

    os.makedirs(OUT_DIR, exist_ok=True)
    meta = {}
    for tenor, series in combined.items():
        reihe_id = TENOR_TO_ID[tenor]
        write_reihe(
            meta, reihe_id, series, "ruhend",
            "Prozent p.a.",
            "Japanische Staatsanleihen (JGB), Par-Zinsstrukturkurve Laufzeit %s, taeglicher Referenzsatz (Ministry of Finance Japan)" % tenor,
            "keine (bereits taeglicher Einzelwert)",
        )

    # Zusatz 3: verdichtete 3 Reihen als neue Reihen derselben Quelle.
    niveau = combined.get(NIVEAU_TENOR, {})
    steil = diff_series(niveau, combined.get(STEIL_KURZ_TENOR, {}))
    kurz = combined.get(KURZ_TENOR, {})
    write_reihe(
        meta, "niveau", niveau, "aktiv", "Prozent p.a.",
        "Japanische Staatsanleihen (JGB), Zinsniveau 10 Jahre, taeglicher Referenzsatz (Ministry of Finance Japan)",
        "keine (bereits taeglicher Einzelwert)",
    )
    write_reihe(
        meta, "steilheit", steil, "aktiv", "Prozentpunkte",
        "Japanische Staatsanleihen (JGB), Zinskurve Steilheit 10J minus 2J (Ministry of Finance Japan)",
        "keine (Differenz zweier taeglicher Einzelwerte)",
    )
    write_reihe(
        meta, "kurz", kurz, "aktiv", "Prozent p.a.",
        "Japanische Staatsanleihen (JGB), kurzes Ende der Zinskurve, Laufzeit 1 Jahr (keine kuerzere Laufzeit oeffentlich verfuegbar; Ministry of Finance Japan)",
        "keine (bereits taeglicher Einzelwert)",
    )

    if not meta:
        raise SystemExit("keine verwertbaren Reihen")

    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
