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
        dates = sorted(series.keys())
        if len(dates) < 500 or dates[0] > "2015-12-31":
            continue
        rows = [(d, series[d]) for d in dates]
        gzip_write(os.path.join(OUT_DIR, reihe_id + ".csv.gz"), rows)
        meta[reihe_id] = {
            "einheit": "Prozent p.a.",
            "beschreibung": "Japanische Staatsanleihen (JGB), Par-Zinsstrukturkurve Laufzeit %s, taeglicher Referenzsatz (Ministry of Finance Japan)" % tenor,
            "quelle_url": HIST_URL,
            "verdichtung": "keine (bereits taeglicher Einzelwert)",
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
        }
        print("OK %s (%s): %s..%s, %d Werte" % (reihe_id, tenor, dates[0], dates[-1], len(dates)))

    if not meta:
        raise SystemExit("keine verwertbaren Reihen")

    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
