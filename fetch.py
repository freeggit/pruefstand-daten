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

def get(url, tries=3, pause=3, timeout=30):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
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
    entry.update({"datei": path, "zeilen": len(body), "erste": body[0][date_col], "letzte": body[-1][date_col]})
    manifest["reihen"][key] = entry
    print(f"ok {key}: {len(body)} Zeilen bis {body[-1][date_col]}")
    return True

def _yahoo_zeilen(ticker, period1):
    """Tagesbalken {Datum: Zeile} aus dem Yahoo-Chart-Endpunkt ab period1 (Unix-Sekunden)."""
    p2 = int(time.time()) + 86400
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker.upper()}"
           f"?period1={period1}&period2={p2}&interval=1d&events=div%2Csplit")
    raw = get(url)
    j = json.loads(raw.decode("utf-8"))
    res = j["chart"]["result"][0]
    gran = res.get("meta", {}).get("dataGranularity")
    if gran != "1d":
        raise RuntimeError(f"Yahoo lieferte Granularitaet {gran} statt 1d")
    ts = res["timestamp"]; q = res["indicators"]["quote"][0]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose", [None] * len(ts))
    # Laufender Handelstag: Balken ist unvollständig (Abruf während der Börsenzeit) -> weglassen
    reg = (res.get("meta", {}).get("currentTradingPeriod") or {}).get("regular") or {}
    offen_ab = reg.get("start") if reg.get("end") and time.time() < reg["end"] else None
    rows = {}
    for i, t in enumerate(ts):
        if offen_ab is not None and t >= offen_ab:
            continue
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c):
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
        rows[d] = [d, f"{o:.4f}", f"{h:.4f}", f"{l:.4f}", f"{c:.4f}", str(int(v or 0)), f"{adj[i]:.4f}" if adj[i] is not None else ""]
    return rows

def yahoo_chart(ticker):
    """Unadjustierte Tageskurse plus Adj Close aus dem Yahoo-Chart-Endpunkt (kein Schluessel)."""
    # period1/period2 statt range=max: mit range=max liefert Yahoo stillschweigend Monatsbalken
    rows = _yahoo_zeilen(ticker, 631152000)
    # Yahoo lässt in der langen Abfrage gelegentlich den vorletzten Handelstag leer (22.9.2026 bei ACWI u.a.).
    # Darum die letzten 40 Tage separat holen und fehlende Tage ergänzen; vorhandene Tage bleiben unverändert.
    try:
        kurz = _yahoo_zeilen(ticker, int(time.time()) - 40 * 86400)
        ergaenzt = sorted(set(kurz) - set(rows))
        for d in ergaenzt:
            rows[d] = kurz[d]
        if ergaenzt:
            print(f"{ticker}: {len(ergaenzt)} Tag(e) aus Kurzabfrage ergaenzt: {', '.join(ergaenzt)}")
    except Exception as e:  # noqa
        print(f"{ticker}: Kurzabfrage fehlgeschlagen ({e}); lange Abfrage bleibt", file=sys.stderr)
    head = ["Date", "Open", "High", "Low", "Close", "Volume", "AdjClose"]
    out = io.StringIO(); w = csv.writer(out); w.writerow(head); w.writerows(rows[d] for d in sorted(rows))
    return out.getvalue().encode("utf-8")

def taeglich_pruefen(path, key):
    """Median-Abstand der letzten 300 Zeilen muss 1 Tag sein, sonst ist die Reihe nicht taeglich."""
    from datetime import date
    with open(path, encoding="utf-8") as f:
        ds = [date.fromisoformat(r[0]) for r in csv.reader(f) if r and r[0][:1].isdigit()]
    ds = ds[-300:]
    gaps = sorted((b - a).days for a, b in zip(ds, ds[1:]))
    med = gaps[len(gaps) // 2] if gaps else None
    manifest["reihen"][key]["median_abstand_tage"] = med
    manifest["reihen"][key]["granularitaet"] = "1d" if med == 1 else f"nicht taeglich ({med} Tage)"
    if med != 1:
        manifest["reihen"][key]["fehler"] = f"Reihe nicht taeglich, Median-Abstand {med} Tage"
        print(f"FEHLER {key}: nicht taeglich ({med} Tage)", file=sys.stderr)

def kurse():
    """Je Ticker: zuerst Stooq (bevorzugt), sonst Yahoo-Chart. Quelle steht im Manifest."""
    for t in lines("tickers.txt"):
        t = t.lower(); path = f"{OUT}/kurse/{t}_d.csv"; key = f"kurse:{t}"
        # 1. Stooq – sperrt Rechenzentrums-IPs (auch GitHub); nur mit STOOQ=1 versuchen, dann kurz
        if os.environ.get("STOOQ") == "1":
            try:
                raw = get(f"https://stooq.com/q/d/l/?s={t}.us&i=d", tries=1, timeout=10)
                parsed, err = check_csv(raw, "Date")
            except Exception as e:
                parsed, err = None, f"Abruf: {e}"
        else:
            parsed, err = None, "übersprungen (Stooq sperrt Rechenzentrums-IPs; STOOQ=1 zum Versuchen)"
        if parsed and write_if_ok(path, raw, key, "Date"):
            manifest["reihen"][key]["quelle"] = "stooq"; taeglich_pruefen(path, key)
            time.sleep(0.5); continue
        stooq_err = err
        # 2. Yahoo-Chart
        try:
            raw = yahoo_chart(t)
            if write_if_ok(path, raw, key, "Date"):
                manifest["reihen"][key]["quelle"] = "yahoo-chart"
                manifest["reihen"][key]["stooq_fehler"] = stooq_err
                taeglich_pruefen(path, key)
        except Exception as e:
            manifest["reihen"][key] = {"fehler": f"stooq: {stooq_err}; yahoo: {e}", "datei": path if os.path.exists(path) else None}
            print(f"FEHLER {key}: {manifest['reihen'][key]['fehler']}", file=sys.stderr)
        print(f"{key}: {manifest['reihen'].get(key, {}).get('quelle', 'fehler')}", flush=True)
        time.sleep(0.5)

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
    kurse(); fred(); french()
    with open(f"{OUT}/manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    n_err = sum(1 for v in manifest["reihen"].values() if "fehler" in v)
    print(f"fertig: {len(manifest['reihen'])} Reihen, {n_err} Fehler")
