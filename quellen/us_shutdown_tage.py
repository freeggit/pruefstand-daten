#!/usr/bin/env python3
"""US-Haushaltssperren (federal government shutdowns mit Beurlaubungen), ab 1980.
Reihen (0/1 je Kalendertag ab 1976-10-01, Beginn des heutigen Fiskaljahrs-Kalenders):
  beginn: 1 am ersten Tag einer Haushaltssperre mit Beurlaubungen
  aktiv:  1 an jedem Kalendertag, an dem eine solche Sperre in Kraft war
Episoden fest hinterlegt nach Wikipedia «Government shutdowns in the United States»
(Liste «Overview of shutdowns involving furloughs») und den Einzelartikeln je Sperre.
Jeder Lauf prueft, ob die Liste neue Zeilen hat; wenn ja, Abbruch mit Fehler
(Nachtrag von Hand, nichts schaetzen)."""
import datetime, gzip, io, json, os, re, urllib.request

ID = "us_shutdown_tage"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
LIST_URL = "https://en.wikipedia.org/w/index.php?title=Government_shutdowns_in_the_United_States&action=raw"
START = datetime.date(1976, 10, 1)
# (erster Tag, letzter Tag, Beleg)
EPISODEN = [
    ("1980-05-01", "1980-05-01", "1980 shutdown: nur FTC, 1 Tag (Wikipedia 1980 United States federal government shutdown)"),
    ("1981-11-23", "1981-11-23", "Beurlaubung am Montag 23.11.1981 (Wikipedia 1981, 1984, and 1986 shutdowns)"),
    ("1984-10-04", "1984-10-04", "Nachmittag 4.10.1984 (ebenda)"),
    ("1986-10-17", "1986-10-17", "Nachmittag 17.10.1986 (ebenda)"),
    ("1990-10-06", "1990-10-08", "Samstag 6.10. bis Montag 8.10.1990 (Wikipedia 1990 shutdown)"),
    ("1995-11-14", "1995-11-19", "14.-19.11.1995 (Wikipedia 1995-1996 shutdowns)"),
    ("1995-12-16", "1996-01-06", "16.12.1995-6.1.1996 (ebenda)"),
    ("2013-10-01", "2013-10-16", "1.-16.10.2013 (Wikipedia 2013 shutdown)"),
    ("2018-01-20", "2018-01-22", "20.-22.1.2018 (Infobox Wikipedia January 2018 shutdown)"),
    ("2018-12-22", "2019-01-25", "22.12.2018-25.1.2019 (Wikipedia 2018-2019 shutdown)"),
    ("2025-10-01", "2025-11-12", "1.10.-12.11.2025 (Infobox Wikipedia 2025 shutdown)"),
    ("2026-01-31", "2026-02-03", "31.1.-3.2.2026 teilweise (Infobox Wikipedia 2026 shutdowns)"),
    ("2026-02-14", "2026-04-30", "14.2.-30.4.2026 nur DHS (Infobox Wikipedia 2026 shutdowns)"),
]


def check_list():
    req = urllib.request.Request(LIST_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        txt = r.read().decode("utf-8")
    i = txt.find("Overview of shutdowns involving furloughs")
    if i < 0:
        raise RuntimeError("Liste nicht gefunden (Seitenaufbau geaendert)")
    tab = txt[i:txt.find("\n|}", i)]
    zeilen = re.findall(r"^\|(?:rowspan=\"\d+\"\|)?\[\[[^\]|#]*shutdowns?\|[^\]]*(?:19|20)\d\d", tab, re.M)
    if len(zeilen) != len(EPISODEN):
        raise RuntimeError("Liste hat %d Episoden, hinterlegt %d: Nachtrag noetig" % (len(zeilen), len(EPISODEN)))


def write(name, rows):
    os.makedirs(OUT, exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("datum,wert\n" + "".join("%s,%d\n" % (d.isoformat(), v) for d, v in rows)).encode())
    with open(os.path.join(OUT, name + ".csv.gz"), "wb") as f:
        f.write(buf.getvalue())


def main():
    check_list()
    end = datetime.datetime.now(datetime.timezone.utc).date()
    beginn, aktiv = set(), set()
    for a, b, _ in EPISODEN:
        a = datetime.date.fromisoformat(a); b = datetime.date.fromisoformat(b)
        beginn.add(a)
        d = a
        while d <= b:
            aktiv.add(d); d += datetime.timedelta(days=1)
    tage = []
    d = START
    while d <= end:
        tage.append(d); d += datetime.timedelta(days=1)
    write("beginn", [(t, int(t in beginn)) for t in tage])
    write("aktiv", [(t, int(t in aktiv)) for t in tage])
    gemein = {
        "einheit": "Indikator (0/1)",
        "quelle_url": "https://en.wikipedia.org/wiki/Government_shutdowns_in_the_United_States",
        "verdichtung": "keine (Ereignisliste auf Kalendertage abgebildet)",
        "verfuegbar_nach_tagen": 0,
        "publikation": "taeglich (Beginn und Dauer einer Haushaltssperre sind am selben Tag oeffentlich: Finanzierung laeuft um Mitternacht aus, OMB weist Behoerden an; Belege je Episode in quellen/us_shutdown_tage.py)",
        "revidiert": False,
    }
    meta = {
        "beginn": dict(gemein, beschreibung="1 am ersten Tag einer US-Haushaltssperre mit Beurlaubungen (13 Episoden 1980-2026, inkl. Teilsperren FTC 1980 und DHS 2026), sonst 0; ab 1976-10-01"),
        "aktiv": dict(gemein, beschreibung="1 an jedem Kalendertag einer laufenden US-Haushaltssperre mit Beurlaubungen, sonst 0; ab 1976-10-01"),
    }
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
