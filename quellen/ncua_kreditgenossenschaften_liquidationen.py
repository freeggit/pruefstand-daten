#!/usr/bin/env python3
"""NCUA: Liquidationen, Zwangsverwaltungen und unterstuetzte Fusionen von US-Kreditgenossenschaften je Tag.
Quelle: Tabelle https://ncua.gov/support-services/conservatorships-liquidations (paginiert, ab 2009).
Datum = Datum der Massnahme laut NCUA (am selben Tag Pressemitteilung)."""
import datetime, gzip, io, json, os, re, time, urllib.request

ID = "ncua_kreditgenossenschaften_liquidationen"
BASE = "https://ncua.gov/support-services/conservatorships-liquidations?page=%d"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)


def fetch(url):
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if i == 3:
                raise
            time.sleep(2 * (i + 1))


def write(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("datum,wert\n" + "".join("%s,%d\n" % r for r in rows)).encode())
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    faelle = set()
    for p in range(60):
        t = fetch(BASE % p)
        neu = 0
        for tr in re.findall(r"<tr>(.*?)</tr>", t, re.S):
            td = [re.sub(r"<[^>]+>", "", x).strip() for x in re.findall(r"<td>(.*?)</td>", tr, re.S)]
            if len(td) == 7 and re.match(r"\d\d/\d\d/\d{4}$", td[1]):
                key = tuple(td)
                if key not in faelle:
                    faelle.add(key)
                    neu += 1
        if neu == 0:
            break
        time.sleep(0.5)
    if len(faelle) < 200:
        raise RuntimeError("zu wenige Faelle: %d" % len(faelle))
    zaehl = {"schliessungen": {}, "zwangsverwaltungen": {}}
    for f in faelle:
        m, d, y = f[1].split("/")
        dt = datetime.date(int(y), int(m), int(d))
        typ = f[2].lower()
        reihe = "zwangsverwaltungen" if "conservatorship" in typ else "schliessungen"
        zaehl[reihe][dt] = zaehl[reihe].get(dt, 0) + 1
    heute = datetime.datetime.now(datetime.timezone.utc).date()
    alle = [d for z in zaehl.values() for d in z]
    start = min(alle)
    os.makedirs(OUT, exist_ok=True)
    for reihe, z in zaehl.items():
        rows, cur = [], start
        while cur <= heute:
            rows.append((cur.isoformat(), z.get(cur, 0)))
            cur += datetime.timedelta(days=1)
        write(os.path.join(OUT, reihe + ".csv.gz"), rows)
    pub = ("taeglich: die NCUA gibt Liquidationen, Zwangsverwaltungen und unterstuetzte Fusionen am Tag der "
           "Massnahme per Pressemitteilung bekannt (Tabelle verlinkt je Fall die Pressemitteilung, ncua.gov/newsroom); "
           "konservativ 1 Tag angesetzt")
    meta = {
        "schliessungen": {
            "einheit": "Anzahl Faelle",
            "beschreibung": "Taegliche Anzahl Liquidationen (unfreiwillig und freiwillig) und Fusionen mit NCUA-Unterstuetzung "
                            "von US-Kreditgenossenschaften, Datum = Datum der Massnahme laut NCUA, 0 an Tagen ohne Fall; ab 2009",
            "quelle_url": "https://ncua.gov/support-services/conservatorships-liquidations",
            "verdichtung": "Anzahl Faelle je Kalendertag",
            "verfuegbar_nach_tagen": 1, "revidiert": False, "publikation": pub},
        "zwangsverwaltungen": {
            "einheit": "Anzahl Faelle",
            "beschreibung": "Taegliche Anzahl Unterstellungen von US-Kreditgenossenschaften unter Zwangsverwaltung "
                            "(Conservatorship) durch die NCUA, Datum = Datum der Massnahme, 0 an Tagen ohne Fall; ab 2009",
            "quelle_url": "https://ncua.gov/support-services/conservatorships-liquidations",
            "verdichtung": "Anzahl Faelle je Kalendertag",
            "verfuegbar_nach_tagen": 1, "revidiert": False, "publikation": pub},
    }
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
