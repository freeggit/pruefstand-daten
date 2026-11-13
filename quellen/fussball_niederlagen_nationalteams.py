#!/usr/bin/env python3
"""Niederlagen der Nationalteams DEU, CHE, JPN an Endrunden (WM, EM, Asienmeisterschaft).

Quelle: martj42/international_results (CC0), Ergebnisliste aller Laenderspiele ab 1872.
Reihe = 1 am Spieltag (Ortsdatum) einer Niederlage (inkl. Penaltyschiessen), sonst 0.
Nullen ausserhalb von Endrunden sind deterministisch (Spielplaene im Voraus bekannt);
liegt zwischen letztem Quelltag und heute der Beginn einer Endrunde, endet die Reihe am
Tag davor (nichts wird aufgefuellt).
"""
import csv, datetime, gzip, io, json, os, urllib.request

ID = "fussball_niederlagen_nationalteams"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
BASE = "https://raw.githubusercontent.com/martj42/international_results/master/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
START = datetime.date(1930, 7, 13)  # erstes WM-Spiel
TEAMS = {
    "deu": ("Germany", {"FIFA World Cup", "UEFA Euro"}),
    "che": ("Switzerland", {"FIFA World Cup", "UEFA Euro"}),
    "jpn": ("Japan", {"FIFA World Cup", "AFC Asian Cup"}),
}
# bekannte kuenftige Endrunden (Beginn): Asian Cup 2027 Saudi-Arabien, EM 2028 GB/IRL, WM 2030
KUENFTIG = [datetime.date(2027, 1, 7), datetime.date(2028, 6, 9), datetime.date(2030, 6, 8)]


def get(name):
    req = urllib.request.Request(BASE + name, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return list(csv.DictReader(io.StringIO(r.read().decode("utf-8"))))


def main():
    res = get("results.csv")
    sho = {(r["date"], r["home_team"], r["away_team"]): r["winner"] for r in get("shootouts.csv")}
    letzte = max(datetime.date.fromisoformat(r["date"]) for r in res if r["home_score"] not in ("", "NA"))
    heute = datetime.datetime.now(datetime.timezone.utc).date() - datetime.timedelta(days=1)
    ende = heute
    for k in KUENFTIG:
        if letzte < k <= heute:
            ende = min(ende, k - datetime.timedelta(days=1))
    os.makedirs(OUT, exist_ok=True)
    meta = {}
    for key, (team, turniere) in TEAMS.items():
        tage = set()
        for r in res:
            if r["tournament"] not in turniere or team not in (r["home_team"], r["away_team"]):
                continue
            if r["home_score"] in ("", "NA"):
                continue
            hs, as_ = int(r["home_score"]), int(r["away_score"])
            eigen, gegner = (hs, as_) if r["home_team"] == team else (as_, hs)
            verloren = eigen < gegner
            if eigen == gegner:
                w = sho.get((r["date"], r["home_team"], r["away_team"]))
                verloren = w is not None and w != team
            if verloren:
                tage.add(datetime.date.fromisoformat(r["date"]))
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
            gz.write(b"datum,wert\n")
            d = START
            while d <= ende:
                gz.write(f"{d.isoformat()},{1 if d in tage else 0}\n".encode())
                d += datetime.timedelta(days=1)
        with open(os.path.join(OUT, f"niederlage_{key}.csv.gz"), "wb") as f:
            f.write(buf.getvalue())
        meta[f"niederlage_{key}"] = {
            "einheit": "0/1 (1 = Niederlage am Spieltag)",
            "beschreibung": f"1 an Tagen, an denen {team} an einer Endrunde ({', '.join(sorted(turniere))}) verlor (inkl. Penaltyschiessen), sonst 0; Datum = Ortsdatum des Spiels.",
            "quelle_url": BASE + "results.csv",
            "verdichtung": "keine (Ereignistag)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
            "publikation": "taeglich (Ergebnis ist mit Spielende oeffentlich; Spieltermine im Voraus durch FIFA/UEFA/AFC publiziert)",
            "status": "aktiv",
        }
    with open(os.path.join(OUT, "meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("letzter Quelltag", letzte, "Ende", ende)


if __name__ == "__main__":
    main()
