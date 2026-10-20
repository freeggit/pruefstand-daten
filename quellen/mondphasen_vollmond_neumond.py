#!/usr/bin/env python3
"""Tage von Neumond und Vollmond (UTC-Tag des astronomischen Moments), nach
Meeus, Astronomical Algorithms, Kap. 49 (Hauptterme, Genauigkeit wenige
Minuten). Rein deterministisch, kein externer Abruf. Reihen: neumond,
vollmond (0/1 je Kalendertag ab 1950-01-01 bis heute)."""
import datetime, gzip, io, json, math, os

ID = "mondphasen_vollmond_neumond"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
START = datetime.date(1950, 1, 1)
R = math.radians

def phase_jde(k):
    T = k / 1236.85
    jde = (2451550.09766 + 29.530588861 * k + 0.00015437 * T**2
           - 0.000000150 * T**3 + 0.00000000073 * T**4)
    E = 1 - 0.002516 * T - 0.0000074 * T**2
    M = (2.5534 + 29.10535670 * k - 0.0000014 * T**2) % 360
    Mp = (201.5643 + 385.81693528 * k + 0.0107582 * T**2 + 0.00001238 * T**3) % 360
    F = (160.7108 + 390.67050284 * k - 0.0016118 * T**2 - 0.00000227 * T**3) % 360
    Om = (124.7746 - 1.56375588 * k + 0.0020672 * T**2) % 360
    return jde, T, E, M, Mp, F, Om

def terms(k):
    jde, T, E, M, Mp, F, Om = phase_jde(k)
    full = (k % 1) != 0
    # (Koeff, E-Potenz, M, M', F)
    if not full:
        t = [(-0.40720,0,0,1,0),(0.17241,1,1,0,0),(0.01608,0,0,2,0),(0.01039,0,0,0,2),
             (0.00739,1,-1,1,0),(-0.00514,1,1,1,0),(0.00208,2,2,0,0),(-0.00111,0,0,1,-2),
             (-0.00057,0,0,1,2),(0.00056,1,1,2,0),(-0.00042,0,0,3,0),(0.00042,1,1,0,2),
             (0.00038,1,1,0,-2),(-0.00024,1,-1,2,0),(-0.00017,0,0,0,0)]
    else:
        t = [(-0.40614,0,0,1,0),(0.17302,1,1,0,0),(0.01614,0,0,2,0),(0.01043,0,0,0,2),
             (0.00734,1,-1,1,0),(-0.00515,1,1,1,0),(0.00209,2,2,0,0),(-0.00111,0,0,1,-2),
             (-0.00057,0,0,1,2),(0.00056,1,1,2,0),(-0.00042,0,0,3,0),(0.00042,1,1,0,2),
             (0.00038,1,1,0,-2),(-0.00024,1,-1,2,0),(-0.00017,0,0,0,0)]
    s = 0.0
    for a, ep, mm, mp, f in t[:-1]:
        s += a * (E ** ep) * math.sin(R(mm * M + mp * Mp + f * F))
    s += -0.00017 * math.sin(R(Om))
    return jde + s

def to_date(jde):
    return (datetime.datetime(2000, 1, 1, 12) + datetime.timedelta(days=jde - 2451545.0)).date()

def build(end):
    kn, kf = set(), set()
    k0 = int((START.year - 2000) * 12.3685) - 3
    k1 = int((end.year + 1 - 2000) * 12.3685) + 4
    for k in range(k0, k1):
        for kk, tgt in ((float(k), kn), (k + 0.5, kf)):
            d = to_date(terms(kk))
            if START <= d <= end:
                tgt.add(d)
    days = []
    d = START
    while d <= end:
        days.append(d); d += datetime.timedelta(days=1)
    return days, kn, kf

def gz_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("datum,wert\n" + "".join("%s,%d\n" % r for r in rows)).encode())
    open(path, "wb").write(buf.getvalue())

def main():
    end = datetime.datetime.now(datetime.timezone.utc).date()
    days, kn, kf = build(end)
    meta = {}
    for name, s, txt in (("neumond", kn, "Neumond"), ("vollmond", kf, "Vollmond")):
        gz_write(os.path.join(OUT_DIR, name + ".csv.gz"),
                 [(d.isoformat(), 1 if d in s else 0) for d in days])
        meta[name] = {"einheit": "0/1 (1 = Tag des %s, UTC)" % txt,
            "beschreibung": "%s-Tag nach Meeus, Astronomical Algorithms Kap. 49 (Genauigkeit wenige Minuten, UTC-Tag)" % txt,
            "quelle_url": "https://aa.usno.navy.mil/data/MoonPhases",
            "verdichtung": "keine (berechneter Ereignistag)",
            "verfuegbar_nach_tagen": 0, "revidiert": False,
            "publikation": "taeglich: astronomisch im Voraus berechenbar, Termine seit Jahrhunderten oeffentlich (USNO/Meeus)"}
    json.dump(meta, open(os.path.join(OUT_DIR, "meta.json"), "w"), indent=1, ensure_ascii=False)

if __name__ == "__main__":
    main()
