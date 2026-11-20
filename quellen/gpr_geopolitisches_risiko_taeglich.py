#!/usr/bin/env python3
"""Caldara-Iacoviello Geopolitical Risk Index (GPR), Tageswerte ab 1985.

Quelle: Stata-Datei data_gpr_daily_recent.dta von matteoiacoviello.com (frei zum Download,
Zitierung erbeten). Die .dta (Format 118) wird mit der Standardbibliothek gelesen.
Reihen: gprd (Gesamtindex), gprd_act (Akte), gprd_threat (Drohungen); Index 1985-2019 = 100.
Gleitende Mittel und Artikelzahl werden nicht abgelegt (abgeleitet bzw. Redundanz, Zusatz 3).
"""
import datetime, gzip, io, json, os, struct, sys, urllib.request

ID = "gpr_geopolitisches_risiko_taeglich"
URL = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.dta"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "neu", ID)
REIHEN = {"GPRD": "gprd", "GPRD_ACT": "gprd_act", "GPRD_THREAT": "gprd_threat"}
NUM = {65526: ("<d", 8), 65527: ("<f", 4), 65528: ("<i", 4), 65529: ("<h", 2), 65530: ("<b", 1)}


def lese_dta(b):
    if b"<release>118</release>" not in b[:200] or b"<byteorder>LSF</byteorder>" not in b[:200]:
        raise RuntimeError("unerwartetes dta-Format")
    i = b.index(b"<K>") + 3; K = struct.unpack("<H", b[i:i + 2])[0]
    i = b.index(b"<N>") + 3; N = struct.unpack("<Q", b[i:i + 8])[0]
    i = b.index(b"<map>") + 5; mp = struct.unpack("<14Q", b[i:i + 112])
    i = mp[2] + len(b"<variable_types>"); ty = struct.unpack("<%dH" % K, b[i:i + 2 * K])
    i = mp[3] + len(b"<varnames>")
    nm = [b[i + 129 * j:i + 129 * (j + 1)].split(b"\0")[0].decode() for j in range(K)]
    lay, off = [], 0
    for t in ty:
        if t in NUM:
            fmt, w = NUM[t]
        elif 1 <= t <= 2045:
            fmt, w = None, t
        else:
            raise RuntimeError("Typ %d nicht unterstuetzt" % t)
        lay.append((fmt, off, w)); off += w
    d0 = mp[9] + len(b"<data>")
    if b[mp[9]:d0] != b"<data>":
        raise RuntimeError("data-Marke fehlt")
    zeilen = []
    for r in range(N):
        base = d0 + r * off; z = {}
        for n, (fmt, o, w) in zip(nm, lay):
            raw = b[base + o:base + o + w]
            if fmt is None:
                z[n] = raw.split(b"\0")[0].decode("latin1").strip()
            else:
                z[n] = struct.unpack(fmt, raw)[0]
        zeilen.append(z)
    return zeilen


def fehlend(v):
    return v is None or v != v or abs(v) > 1.7e38


def gz(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, filename="") as g:
        g.write(("datum,wert\n" + "".join("%s,%s\n" % r for r in rows)).encode())
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(buf.getvalue())
    os.replace(tmp, path)


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        b = r.read()
    zeilen = lese_dta(b)
    os.makedirs(OUT, exist_ok=True)
    # Tag des Datei-Zeitstempels und spaeter weglassen: dieser Tag ist beim Erstellen noch nicht abgeschlossen
    i = b.index(b"<timestamp>") + len(b"<timestamp>")
    ts = b[i + 1:i + 1 + b[i]].decode().strip()
    heute = datetime.datetime.strptime(ts, "%d %b %Y %H:%M").date()
    for var, rid in REIHEN.items():
        werte = {}
        for z in zeilen:
            tag = z["DAY"]
            d = datetime.date(int(tag[:4]), int(tag[4:6]), int(tag[6:8]))
            if d >= heute or fehlend(z[var]):
                continue
            if d.isoformat() in werte:
                raise RuntimeError("Doppel %s" % d)
            werte[d.isoformat()] = "%.4f" % z[var]
        rows = sorted(werte.items())
        alt_pfad = os.path.join(OUT, rid + ".csv.gz")
        if os.path.exists(alt_pfad):  # Kontrolle K4: geaenderte Altwerte melden
            with gzip.open(alt_pfad, "rt") as f:
                alt = dict(l.strip().split(",") for l in f.readlines()[1:])
            diff = sum(1 for k, v in alt.items() if k in werte and abs(float(werte[k]) - float(v)) > 1e-3)
            print("%s: %d Altwerte geaendert, %d entfallen" % (rid, diff, sum(k not in werte for k in alt)), file=sys.stderr)
        if len(rows) < 500:
            raise RuntimeError("zu wenige Werte %s" % var)
        gz(os.path.join(OUT, rid + ".csv.gz"), rows)
    pub = ("woechentlich: die Tagesdatei wird auf matteoiacoviello.com/gpr.htm etwa einmal pro Woche erneuert "
           "(Zeitstempel der dta, z.B. 16 Nov 2026); darum verfuegbar_nach_tagen 8 nach Zusatz 5")
    gem = dict(quelle_url="https://www.matteoiacoviello.com/gpr.htm", verfuegbar_nach_tagen=8,
               revidiert=False, publikation=pub, einheit="Index (1985-2019 = 100)",
               verdichtung="keine (Tageswert der Quelle; Artikel des Kalendertags in 10 Zeitungen)")
    meta = {
        "gprd": dict(gem, beschreibung="Taeglicher Geopolitical Risk Index (Caldara/Iacoviello, AER 2022): Anteil Artikel "
                     "mit geopolitischen Risikobegriffen in 10 US/UK-Zeitungen, normiert 1985-2019 = 100."),
        "gprd_act": dict(gem, beschreibung="Teilindex Geopolitical Acts (eingetretene Ereignisse: Krieg begonnen, Anschlag, Eskalation)."),
        "gprd_threat": dict(gem, beschreibung="Teilindex Geopolitical Threats (Drohungen, Kriegsgefahr, nukleare Drohung)."),
    }
    with open(os.path.join(OUT, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False, sort_keys=True)
    print("geschrieben: %d Zeilen gelesen" % len(zeilen), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
