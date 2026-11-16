#!/usr/bin/env python3
"""Ramadan nach dem Umm-al-Qura-Kalender (Saudi-Arabien), ab 1356 AH (1937).
Quelle: Aladhan-API (api.aladhan.com, frei, ohne Schluessel), hToG mit calendarMethod=UAQ.
Reihen (0/1 je Kalendertag, ab 1937-01-01):
  beginn: 1 am 1. Ramadan
  aktiv:  1 an jedem Tag des Ramadan (1. Ramadan bis Vortag 1. Schawwal)
  eid:    1 am 1. Schawwal (Eid al-Fitr, Ende des Ramadan)
Der Umm-al-Qura-Kalender wird im Voraus berechnet und veroeffentlicht; die
tatsaechliche Ausrufung nach Mondsichtung kann um einen Tag abweichen."""
import datetime, gzip, io, json, os, time, urllib.request

ID = "ramadan_beginn_ende"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
API = "https://api.aladhan.com/v1/hToG/01-%02d-%d?calendarMethod=UAQ"
H_START = 1356
START = datetime.date(1937, 1, 1)


def hto_g(monat, jahr):
    for versuch in range(3):
        try:
            req = urllib.request.Request(API % (monat, jahr), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise
            if versuch == 2:
                raise
            time.sleep(2)
        except Exception:
            if versuch == 2:
                raise
            time.sleep(2)
    if d.get("code") != 200:
        raise RuntimeError("Antwort %r" % d.get("status"))
    m = d["data"]["hijri"].get("method")
    if m != "UAQ":
        raise RuntimeError("Methode %s statt UAQ fuer %d/%d" % (m, monat, jahr))
    g = d["data"]["gregorian"]["date"]
    return datetime.datetime.strptime(g, "%d-%m-%Y").date()


def write(name, rows):
    os.makedirs(OUT, exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("datum,wert\n" + "".join("%s,%d\n" % (d.isoformat(), v) for d, v in rows)).encode())
    with open(os.path.join(OUT, name + ".csv.gz"), "wb") as f:
        f.write(buf.getvalue())


def main():
    end = datetime.datetime.now(datetime.timezone.utc).date()
    beginn, eid, aktiv = set(), set(), set()
    jahr = H_START
    while True:
        b = hto_g(9, jahr)
        if b > end:
            break
        e = hto_g(10, jahr)
        if not (28 <= (e - b).days <= 31):
            raise RuntimeError("unplausible Ramadanlaenge %d/%s/%s" % (jahr, b, e))
        beginn.add(b)
        eid.add(e)
        d = b
        while d < e:
            aktiv.add(d)
            d += datetime.timedelta(days=1)
        jahr += 1
        time.sleep(0.15)
    tage = []
    d = START
    while d <= end:
        tage.append(d)
        d += datetime.timedelta(days=1)
    for name, s in (("beginn", beginn), ("aktiv", aktiv), ("eid", eid)):
        write(name, [(t, int(t in s)) for t in tage])
    gemein = {
        "einheit": "Indikator (0/1)",
        "quelle_url": "https://api.aladhan.com/v1/hToG (calendarMethod=UAQ, Umm-al-Qura-Kalender)",
        "verdichtung": "keine (Kalenderdaten auf Kalendertage abgebildet)",
        "verfuegbar_nach_tagen": 0,
        "publikation": "taeglich (Umm-al-Qura-Kalender wird jaehrlich im Voraus von der King Abdulaziz City for Science and Technology veroeffentlicht; Abweichung der tatsaechlichen Mondsichtung um einen Tag moeglich)",
        "revidiert": False,
    }
    meta = {
        "beginn": dict(gemein, beschreibung="1 am 1. Ramadan nach Umm-al-Qura-Kalender, sonst 0; ab 1937-01-01"),
        "aktiv": dict(gemein, beschreibung="1 an jedem Tag des Ramadan nach Umm-al-Qura-Kalender, sonst 0; ab 1937-01-01"),
        "eid": dict(gemein, beschreibung="1 am 1. Schawwal (Eid al-Fitr) nach Umm-al-Qura-Kalender, sonst 0; ab 1937-01-01"),
    }
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
