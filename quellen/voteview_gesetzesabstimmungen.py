#!/usr/bin/env python3
"""Voteview: namentliche Abstimmungen (roll calls) im US-Kongress je Tag, Haus und Senat zusammen.

Mechanismus: Viele Abstimmungen an einem Tag buendeln Gesetzesentscheide ueber Steuern, Regulierung und Haushalt;
das betrifft regulierte Sektoren (Finanzen, Gesundheit, Energie) kurzfristig staerker als den Weltindex.

Quelle: https://voteview.com/static/data/out/rollcalls/HSall_rollcalls.csv (UCLA, Lewis/Poole/Rosenthal u.a.),
Spalte date = Abstimmungstag. Tage ohne Abstimmung = 0, aber nur bis zum letzten Tag in der Datei (die Datei
wird mit wenigen Tagen Verzug nachgefuehrt; danach keine Nullen erfinden).
"""
import csv, datetime, gzip, io, json, os, urllib.request

ID = "voteview_gesetzesabstimmungen"
URL = "https://voteview.com/static/data/out/rollcalls/HSall_rollcalls.csv"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8")
    counts, seen = {}, set()
    for row in csv.DictReader(io.StringIO(raw)):
        d = (row.get("date") or "").strip()
        try:
            datetime.date.fromisoformat(d)
        except ValueError:
            continue
        key = (row.get("congress"), row.get("chamber"), row.get("rollnumber"))
        if key in seen:
            continue
        seen.add(key)
        counts[d] = counts.get(d, 0) + 1
    if len(counts) < 1000:
        raise SystemExit("Abruffehler %s: nur %d Tage gelesen; bisherige Datei bleibt" % (ID, len(counts)))
    first = datetime.date.fromisoformat(min(counts))
    last = datetime.date.fromisoformat(max(counts))
    lines, d = ["datum,wert"], first
    while d <= last:
        lines.append("%s,%d" % (d.isoformat(), counts.get(d.isoformat(), 0)))
        d += datetime.timedelta(days=1)
    os.makedirs(OUT_DIR, exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("\n".join(lines) + "\n").encode())
    with open(os.path.join(OUT_DIR, "abstimmungen.csv.gz"), "wb") as f:
        f.write(buf.getvalue())
    meta = {"abstimmungen": {
        "einheit": "Anzahl namentliche Abstimmungen",
        "beschreibung": "Anzahl namentlicher Abstimmungen (roll calls) in Repraesentantenhaus und Senat je Abstimmungstag "
                        "laut Voteview, 0 an Tagen ohne Abstimmung (nur bis zum letzten Tag der Datei).",
        "quelle_url": URL,
        "verdichtung": "Anzahl je Kalendertag (Abstimmungsdatum)",
        "publikation": "taeglich (namentliche Abstimmungen sind live oeffentlich und werden noch am selben Tag auf "
                       "clerk.house.gov bzw. senate.gov/legislative/votes publiziert; Voteview fuehrt sie mit wenigen "
                       "Tagen Verzug nach)",
        "verfuegbar_nach_tagen": 0,
        "revidiert": False}}
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
