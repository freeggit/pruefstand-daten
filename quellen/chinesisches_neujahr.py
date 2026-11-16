#!/usr/bin/env python3
"""Chinesisches Neujahr (1. Tag des 1. Mondmonats) und Laternenfest (15. Tag), berechnet.
Regeln des chinesischen Lunisolarkalenders seit der Reform 1645 (Aslaksen 2010, The Mathematics
of the Chinese Calendar): Monate beginnen am Kalendertag des Neumonds in chinesischer Zeit
(ab 1929 UTC+8, davor Ortszeit Peking 116°25' O); der Monat mit der Wintersonnenwende ist Monat 11;
hat das Jahr von Monat 11 bis Monat 11 dreizehn Monate, ist der erste Monat ohne Hauptsonnenterm
(Sonnenlänge Vielfaches von 30°) ein Schaltmonat. Astronomie nach Meeus, Astronomical Algorithms
(Neumond Kap. 49, Sonnenlänge Kap. 25). Keine Netzabfrage; Datum ist Jahrzehnte im Voraus bekannt."""
import math, gzip, io, json, os, datetime as dt
ID = "chinesisches_neujahr"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
JD_UNIX = 2440587.5

def jde_neumond(k):
    T = k / 1236.85; r = math.radians
    jde = 2451550.09766 + 29.530588861*k + 0.00015437*T*T - 0.00000015*T**3 + 0.00000000073*T**4
    E = 1 - 0.002516*T - 0.0000074*T*T
    M = r(2.5534 + 29.10535670*k - 0.0000014*T*T - 0.00000011*T**3)
    Mp = r(201.5643 + 385.81693528*k + 0.0107582*T*T + 0.00001238*T**3 - 0.000000058*T**4)
    F = r(160.7108 + 390.67050284*k - 0.0016118*T*T - 0.00000227*T**3 + 0.000000011*T**4)
    Om = r(124.7746 - 1.56375588*k + 0.0020672*T*T + 0.00000215*T**3)
    s = (-0.40720*math.sin(Mp) + 0.17241*E*math.sin(M) + 0.01608*math.sin(2*Mp) + 0.01039*math.sin(2*F)
         + 0.00739*E*math.sin(Mp-M) - 0.00514*E*math.sin(Mp+M) + 0.00208*E*E*math.sin(2*M)
         - 0.00111*math.sin(Mp-2*F) - 0.00057*math.sin(Mp+2*F) + 0.00056*E*math.sin(2*Mp+M)
         - 0.00042*math.sin(3*Mp) + 0.00042*E*math.sin(M+2*F) + 0.00038*E*math.sin(M-2*F)
         - 0.00024*E*math.sin(2*Mp-M) - 0.00017*math.sin(Om) - 0.00007*math.sin(Mp+2*M)
         + 0.00004*math.sin(2*Mp-2*F) + 0.00004*math.sin(3*M) + 0.00003*math.sin(Mp+M-2*F)
         + 0.00003*math.sin(2*Mp+2*F) - 0.00003*math.sin(Mp+M+2*F) + 0.00003*math.sin(Mp-M+2*F)
         - 0.00002*math.sin(Mp-M-2*F) - 0.00002*math.sin(3*Mp+M) + 0.00002*math.sin(4*Mp))
    A = [299.77+0.107408*k-0.009173*T*T, 251.88+0.016321*k, 251.83+26.651886*k, 349.42+36.412478*k,
         84.66+18.206239*k, 141.74+53.303771*k, 207.14+2.453732*k, 154.84+7.306860*k, 34.52+27.261239*k,
         207.19+0.121824*k, 291.34+1.844379*k, 161.72+24.198154*k, 239.56+25.513099*k, 331.55+3.592518*k]
    c = [0.000325,0.000165,0.000164,0.000126,0.000110,0.000062,0.000060,0.000056,0.000047,0.000042,0.000040,0.000037,0.000035,0.000023]
    s += sum(ci*math.sin(r(a)) for ci, a in zip(c, A))
    return jde + s

def delta_t_tage(jahr):
    # Espenak/Meeus-Polynome (NASA), Sekunden -> Tage
    y = jahr; 
    if y < 1900: t=y-1860; d=7.62+0.5737*t-0.251754*t*t+0.01680668*t**3-0.0004473624*t**4+t**5/233174
    elif y < 1920: t=y-1900; d=-2.79+1.494119*t-0.0598939*t*t+0.0061966*t**3-0.000197*t**4
    elif y < 1941: t=y-1920; d=21.20+0.84493*t-0.076100*t*t+0.0020936*t**3
    elif y < 1961: t=y-1950; d=29.07+0.407*t-t*t/233+t**3/2547
    elif y < 1986: t=y-1975; d=45.45+1.067*t-t*t/260-t**3/718
    elif y < 2005: t=y-2000; d=63.86+0.3345*t-0.060374*t*t+0.0017275*t**3+0.000651814*t**4+0.00002373599*t**5
    elif y < 2050: t=y-2000; d=62.92+0.32217*t+0.005589*t*t
    else: d=-20+32*((y-1820)/100)**2-0.5628*(2150-y)
    return d/86400.0

def sonnenlaenge(jde):
    T = (jde - 2451545.0)/36525; r = math.radians
    L0 = 280.46646 + 36000.76983*T + 0.0003032*T*T
    M = r(357.52911 + 35999.05029*T - 0.0001537*T*T)
    C = (1.914602 - 0.004817*T - 0.000014*T*T)*math.sin(M) + (0.019993 - 0.000101*T)*math.sin(2*M) + 0.000289*math.sin(3*M)
    Om = r(125.04 - 1934.136*T)
    return ((L0 + C) - 0.00569 - 0.00478*math.sin(Om)) % 360.0

def zonen_offset(jahr):
    return 8/24.0 if jahr >= 1929 else (116+25/60)/360.0

def lokaltag(jde):
    jahr = 1900 + (jde - 2415020.5)/365.2425
    jd_ut = jde - delta_t_tage(jahr) + zonen_offset(int(jahr))
    return dt.date(1970,1,1) + dt.timedelta(days=math.floor(jd_ut - JD_UNIX))

def neumonde(jahr_von, jahr_bis):
    k = math.floor((jahr_von - 2000)*12.3685) - 2
    out = []
    while True:
        d = lokaltag(jde_neumond(k))
        if d.year > jahr_bis: break
        if d.year >= jahr_von: out.append((d, jde_neumond(k)))
        k += 1
    return out

def wende_tag(jahr):
    j0 = 2451545.0 + (jahr - 2000)*365.2422 + (355 - 1)  # nahe 21.12.
    j = j0 - 20
    for _ in range(50):
        d = ((270 - sonnenlaenge(j) + 180) % 360) - 180
        j += d/360*365.2422
        if abs(d) < 1e-7: break
    return lokaltag(j), j

def termtage(jahr_von, jahr_bis):
    tage = set()
    for y in range(jahr_von, jahr_bis+1):
        j = 2451545.0 + (y-2000)*365.2422 - 80
        for z in range(0, 360, 30):
            jj = j + ((z - sonnenlaenge(j)) % 360)/360*365.2422
            for _ in range(30):
                d = ((z - sonnenlaenge(jj) + 180) % 360) - 180
                jj += d/360*365.2422
                if abs(d) < 1e-8: break
            tage.add(lokaltag(jj))
    return tage

def neujahre(jahr_von, jahr_bis):
    nm = [d for d, _ in neumonde(jahr_von-2, jahr_bis+1)]
    terme = termtage(jahr_von-2, jahr_bis+1)
    res = {}
    for y in range(jahr_von, jahr_bis+1):
        w1, _ = wende_tag(y-1); w2, _ = wende_tag(y)
        m11a = max(d for d in nm if d <= w1)
        m11b = max(d for d in nm if d <= w2)
        monate = [d for d in nm if m11a <= d <= m11b]
        i = 0
        if len(monate) == 14:  # 13 Monate zwischen den beiden Monaten 11
            for idx in range(len(monate)-1):
                a, b = monate[idx], monate[idx+1]
                if not any(a <= t < b for t in terme):
                    if idx in (1, 2):  # Schaltmonat 11 oder 12 vor Neujahr
                        i = 1
                    break
        res[y] = (monate[2+i], monate[3+i] if len(monate) > 3+i else None)
    return res

def schreibe(name, tage, erste, letzte):
    buf = io.StringIO(); buf.write("datum,wert\n")
    d = erste
    while d <= letzte:
        buf.write("%s,%d\n" % (d.isoformat(), 1 if d in tage else 0)); d += dt.timedelta(days=1)
    raw = buf.getvalue().encode()
    with open(os.path.join(OUT, name + ".csv.gz"), "wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as g: g.write(raw)

def main():
    os.makedirs(OUT, exist_ok=True)
    heute = dt.datetime.now(dt.timezone.utc).date()
    ny = neujahre(1901, heute.year)
    tag1 = {v[0] for v in ny.values()}
    tag15 = {v[0] + dt.timedelta(days=14) for v in ny.values()}
    erste = dt.date(1901, 1, 1)
    schreibe("neujahrstag", tag1, erste, heute)
    schreibe("laternenfest", tag15, erste, heute)
    beleg = ("Regeln nach Aslaksen (2010), Astronomie nach Meeus; Daten im Voraus bekannt "
             "(amtliche Kalender werden Jahre vorher publiziert).")
    meta = {
      "neujahrstag": {"einheit": "0/1", "beschreibung": "1 am 1. Tag des 1. chinesischen Mondmonats (Chinesisches Neujahr, Frühlingsfest), sonst 0; berechnet ab 1901", "quelle_url": "https://www.math.nus.edu.sg/~mathelmr/calendar/cal.pdf (Regeln) / Meeus, Astronomical Algorithms", "verdichtung": "keine (Kalendertag in chinesischer Zeit)", "verfuegbar_nach_tagen": 0, "revidiert": False, "publikation": "taeglich: " + beleg},
      "laternenfest": {"einheit": "0/1", "beschreibung": "1 am 15. Tag des 1. chinesischen Mondmonats (Laternenfest, Ende der Neujahrszeit), sonst 0; berechnet ab 1901", "quelle_url": "https://www.math.nus.edu.sg/~mathelmr/calendar/cal.pdf (Regeln) / Meeus, Astronomical Algorithms", "verdichtung": "keine (Kalendertag in chinesischer Zeit)", "verfuegbar_nach_tagen": 0, "revidiert": False, "publikation": "taeglich: " + beleg},
    }
    with open(os.path.join(OUT, "meta.json"), "w") as f: json.dump(meta, f, ensure_ascii=False, indent=1)
    for y in sorted(ny): print(y, ny[y][0])

if __name__ == "__main__": main()
