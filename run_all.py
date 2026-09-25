#!/usr/bin/env python3
import datetime
import gzip
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
KATALOG_PATH = os.path.join(ROOT, "katalog.json")
QUELLEN_DIR = os.path.join(ROOT, "quellen")
DATA_DIR = os.path.join(ROOT, "data", "neu")
MANIFEST_PATH = os.path.join(DATA_DIR, "manifest_neu.json")
TIMEOUT_S = 180


def load_katalog():
    with open(KATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_source(eintrag):
    sid = eintrag["id"]
    script = os.path.join(QUELLEN_DIR, sid + ".py")
    if not os.path.isfile(script):
        return "fehler: Skript fehlt: %s" % script
    try:
        result = subprocess.run(
            [sys.executable, script],
            cwd=ROOT,
            timeout=TIMEOUT_S,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return "fehler: Zeitlimit (%ds) ueberschritten" % TIMEOUT_S
    if result.returncode != 0:
        stderr_tail = result.stderr.strip().splitlines()
        msg = stderr_tail[-1] if stderr_tail else "unbekannter Fehler"
        return "fehler: %s" % msg
    return None


def read_csv_gz(path):
    rows = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        next(f)
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            d, _, v = line.partition(",")
            rows.append(d)
    return rows


def median_gap_days(dates):
    if len(dates) < 2:
        return None
    ds = [datetime.date.fromisoformat(d) for d in dates]
    gaps = sorted((ds[i + 1] - ds[i]).days for i in range(len(ds) - 1))
    n = len(gaps)
    mid = n // 2
    if n % 2 == 1:
        return gaps[mid]
    return (gaps[mid - 1] + gaps[mid]) / 2


def build_manifest(katalog, abruf_fehler):
    reihen = {}
    for eintrag in katalog:
        if eintrag["status"] != "aktiv":
            continue
        sid = eintrag["id"]
        sdir = os.path.join(DATA_DIR, sid)
        meta_path = os.path.join(sdir, "meta.json")
        if not os.path.isfile(meta_path):
            continue
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        for reihe, minfo in meta.items():
            csv_path = os.path.join(sdir, reihe + ".csv.gz")
            key = "%s:%s" % (sid, reihe)
            if not os.path.isfile(csv_path):
                entry = {
                    "datei": os.path.relpath(csv_path, ROOT).replace(os.sep, "/"),
                    "status": "fehler",
                    "abruf_utc": utcnow(),
                    "fehler": "Datei fehlt",
                }
                reihen[key] = entry
                continue
            dates = read_csv_gz(csv_path)
            entry = {
                "datei": os.path.relpath(csv_path, ROOT).replace(os.sep, "/"),
                "erste": dates[0] if dates else None,
                "letzte": dates[-1] if dates else None,
                "zeilen": len(dates),
                "median_abstand_tage": median_gap_days(dates),
                "einheit": minfo.get("einheit"),
                "beschreibung": minfo.get("beschreibung"),
                "quelle_url": minfo.get("quelle_url"),
                "verdichtung": minfo.get("verdichtung"),
                "verfuegbar_nach_tagen": minfo.get("verfuegbar_nach_tagen"),
                # Zusatz 5: Publikationsregel je Reihe (taeglich/woechentlich/verzoegert
                # mit Beleg), damit die Suchmaschine den tatsaechlichen
                # Veroeffentlichungstag statt des Beobachtungstags kennt.
                "publikation": minfo.get("publikation"),
                "revidiert": minfo.get("revidiert"),
                # Zusatz 3: je-Reihe-Status aus meta.json uebernehmen (Standard "aktiv"
                # fuer Quellen ohne eigenes Status-Feld). Die Suchmaschine liest nur "aktiv".
                "status": minfo.get("status", "aktiv"),
                "abruf_utc": utcnow(),
            }
            if sid in abruf_fehler:
                entry["fehler"] = abruf_fehler[sid]
            reihen[key] = entry

    manifest = {"erzeugt_utc": utcnow(), "reihen": reihen}
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
    return manifest


def main():
    katalog = load_katalog()
    abruf_fehler = {}
    for eintrag in katalog:
        if eintrag["status"] != "aktiv":
            continue
        fehler = run_source(eintrag)
        if fehler:
            abruf_fehler[eintrag["id"]] = fehler
            print("FEHLER %s: %s" % (eintrag["id"], fehler))
        else:
            print("OK %s" % eintrag["id"])
    manifest = build_manifest(katalog, abruf_fehler)
    print("Manifest: %d Reihen" % len(manifest["reihen"]))


if __name__ == "__main__":
    main()
