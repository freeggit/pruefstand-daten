#!/usr/bin/env python3
"""Prüfstand-Datenspiegel: holt öffentliche CSV-Reihen und legt sie unter data/ ab.
Läuft als GitHub Action. Nie schätzen, nie reparieren: was nicht sauber ankommt, wird
als Fehler im Manifest vermerkt und die alte Datei bleibt stehen."""
import csv, io, json, os, sys, time, zipfile, urllib.request, urllib.error
from datetime import datetime, timezone

UA = {"User-Agent": "pruefstand-daten/1.0 (GitHub Actions; public research mirror)"}
OUT = "data"
manifest = {"erzeugt_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "reihen": {}}

def lines(path):
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.split("#", 1)[0].strip()
            if ln:
                yield ln

def get(url, tries=3, pause=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa
            last = e
            time.sleep(pause * (i + 1))
    raise last

def check_csv(raw, expect_first_col="Date", min_rows=10):
    txt = raw.decode("utf-8", errors="replace")
    if "<html" in txt[:500].lower():
        return None, "HTML statt CSV (Limit oder Sperre der Quelle)"
    rows = list(csv.reader(io.StringIO(txt)))
    if not rows or not rows[0] or rows[0][0].strip().lower() != expect_first_col.lower():
        return None, f"unerwarteter Kopf: {rows[0][:3] if rows else 'leer'}"
    body = [r for r in rows[1:] if r and r[0].strip()]
    if len(body) < min_rows:
        return None, f"nur {len(body)} Datenzeilen"
    return (rows[0], body), None

def write_if_ok(path, raw, key, expect_first_col, date_col=0):
    parsed, err = check_csv(raw, expect_first_col)
    entry = {"abruf_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if err:
        entry["fehler"] = err
        entry["datei"] = path if os.path.exists(path) else None
        manifest["reihen"][key] = entry
        print(f"FEHLER {key}: {err}", file=sys.stderr)
        return False
    head, body = parsed
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(head); w.writerows(body)
    entry.update({"datei": path, "zeilen": len(body), "erste": body[0][date_col], "letzte": body[-1][date_col], "quelle": key.split(":")[0]})
    manifest["reihen"][key] = entry
    print(f"ok {key}: {len(body)} Zeilen bis {body[-1][date_col]}")
    return True

def stooq():
    for t in lines("tickers.txt"):
        sym = f"{t.lower()}.us"
        url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
        try:
            raw = get(url)
        except Exception as e:
            manifest["reihen"][f"stooq:{sym}"] = {"fehler": f"Abruf: {e}"}; continue
        write_if_ok(f"{OUT}/stooq/{t.lower()}_us_d.csv", raw, f"stooq:{sym}", "Date")
        time.sleep(1.5)  # freundlich zur Quelle

def fred():
    for s in lines("fred_series.txt"):
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}"
        try:
            raw = get(url)
        except Exception as e:
            manifest["reihen"][f"fred:{s}"] = {"fehler": f"Abruf: {e}"}; continue
        # FRED-Kopf ist "observation_date,<ID>" (früher "DATE,<ID>")
        txt = raw.decode("utf-8", errors="replace")
        first = txt.split("\n", 1)[0].split(",")[0].strip().lower()
        write_if_ok(f"{OUT}/fred/{s}.csv", raw, f"fred:{s}", first if first in ("observation_date", "date") else "observation_date")
        time.sleep(1.0)

def french():
    base = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    files = ["F-F_Research_Data_Factors_CSV.zip", "F-F_Research_Data_5_Factors_2x3_CSV.zip", "12_Industry_Portfolios_CSV.zip", "F-F_Momentum_Factor_CSV.zip"]
    os.makedirs(f"{OUT}/french", exist_ok=True)
    for fn in files:
        key = f"french:{fn}"
        try:
            raw = get(base + fn)
            z = zipfile.ZipFile(io.BytesIO(raw))
            names = z.namelist()
            for n in names:
                with open(f"{OUT}/french/{n}", "wb") as f:
                    f.write(z.read(n))
            manifest["reihen"][key] = {"abruf_utc": manifest["erzeugt_utc"], "dateien": names, "bytes": len(raw)}
            print(f"ok {key}: {names}")
        except Exception as e:
            manifest["reihen"][key] = {"fehler": f"{e}"}
            print(f"FEHLER {key}: {e}", file=sys.stderr)
        time.sleep(1.0)

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    stooq(); fred(); french()
    with open(f"{OUT}/manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    n_err = sum(1 for v in manifest["reihen"].values() if "fehler" in v)
    print(f"fertig: {len(manifest['reihen'])} Reihen, {n_err} Fehler")
