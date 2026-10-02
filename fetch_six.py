#!/usr/bin/env python3
"""Prüfstand-Datenspiegel, Schicht «SIX»: Archiv der öffentlichen Pflichtmeldungen von SIX Exchange Regulation.

Freigabe: Reto, 2.10.2026: «Archiv wie vorgeschlagen» (meta/anders_2026-10-02, Schicht 2a).
Zweck: NUR ARCHIV. Die Meldungen sind bei SIX nur befristet abrufbar (Management-Transaktionen: 4 Jahre rollierend,
Art. 56 Abs. 6 KR). Ein tägliches Archiv hält fest, WAS WANN öffentlich sichtbar war. Die Reihen gehören nicht zum
Suchraum (kein Manifest-Eintrag «aktiv»); eine spätere Nutzung braucht eine eigene Freigabe.

Quellen (öffentlich, ohne Anmeldung; dieselben Abfragen wie die Suchmasken auf www.ser-ag.com):
  mt  Management-Transaktionen     https://www.ser-ag.com/sheldon/management_transactions/v1/overview.json
  bt  Offenlegung von Beteiligungen https://www.ser-ag.com/sheldon/significant_shareholders/v1/overview.json
Antwort: {status, totalCount, itemList}; neueste zuerst; Seiten über pageSize/pageNumber.
Bei Beteiligungen liegen Kennung und Daten unter «publication» (Korrektur 2.10.2026 nach dem ersten Lauf: die Kennung
wurde auf oberster Ebene gesucht, deshalb wurde nichts gespeichert und das Blättern fälschlich als defekt gemeldet).

Ablage (nur anhängen, nie überschreiben):
  data/six/<art>/<JJJJ>.jsonl.gz   eine Zeile je Fassung einer Meldung, Jahr nach Transaktions- bzw. Publikationsdatum:
      {"id", "datum", "erstmals_gesehen_utc", "nachgeladen", "fassung", "inhalt_sha", "meldung": {...}}
      erstmals_gesehen_utc  Zeitpunkt des Laufs, der die Fassung zum ersten Mal sah. Das ist der einzige belastbare
                            Beleg dafür, ab wann die Meldung öffentlich war (die Quelle nennt kein Publikationsdatum
                            für Management-Transaktionen).
      nachgeladen           true für alles, was der ERSTE Lauf der Art findet (Bestand von bis zu 4 Jahren): dort ist
                            der wahre Publikationszeitpunkt unbekannt; für Rückblick-Tests nur mit vorsichtiger Frist.
      fassung               1, 2, …: ändert die Quelle eine Meldung, kommt eine neue Zeile dazu; die alte bleibt.
  data/six/stand.json              je Art: letzter Lauf, Anzahl, totalCount der Quelle, ältestes Datum der Quelle, Fehler.
Verschwindet eine Meldung bei der Quelle, bleibt sie im Archiv.

Personendaten: Management-Transaktionen nennen keine Personen (nur Emittent und Funktion). Beteiligungsmeldungen
nennen Aktionäre und Vertreter, darunter natürliche Personen. Das Repo ist öffentlich: die Namensfelder (NAMEN_BT)
samt Adressen und Freitext-Kommentaren werden deshalb NICHT gespeichert, sondern durch Anzahl und einen gekürzten SHA-256 ersetzt (gleicher Name = gleiche
Kennung; so bleiben Meldungen desselben Aktionärs verknüpfbar). Die Namen stehen weiterhin bei der Quelle.

Zugang: höchstens 1 Abruf pro Sekunde, User-Agent mit Repo-Angabe. Bei 403/429: Befund in stand.json, kein Umweg,
kein weiterer Versuch in diesem Lauf. Der Lauf endet immer mit Code 0 (Archiv darf den Datenspiegel nicht stoppen).
"""
import gzip, hashlib, io, json, os, sys, time, urllib.error, urllib.request
from datetime import datetime, timedelta, timezone

OUT = "data/six"
UA = {"User-Agent": "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)",
      "Accept": "application/json"}
BASIS = "https://www.ser-ag.com/sheldon/"
ARTEN = {
    "mt": {"pfad": "management_transactions/v1/overview.json", "datum": "transactionDate"},
    "bt": {"pfad": "significant_shareholders/v1/overview.json", "datum": "publicationDate"},
}
NAMEN_BT = ("beneficialNames", "beneficialAddrs", "shareholderNames", "shareholderAddrs", "groupRepresentative",
            "contactPerson", "beneficialAssocComment", "relationComment", "submitterComment", "triggerComment",
            "furtherConditions")
SEITE, MAX_SEITEN, PAUSE_S = 100, 400, 1.0
RUECKBLICK_TAGE = 45            # jeder Lauf holt die letzten 45 Tage neu (späte Meldungen, Korrekturen)
ANFANG = "20000101"


def jetzt_utc():
    return datetime.now(timezone.utc)


def hole(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def kennung(wert):
    return hashlib.sha256(json.dumps(wert, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def ist_namensfeld(k):
    kl = k.lower()
    if k in ("notificationSubmitter", "issuerName"):      # Emittent, keine Person
        return False
    return k in NAMEN_BT or any(t in kl for t in ("name", "addr", "representative", "person", "comment"))


def ohne_namen(art, m, tief=0):
    """Beteiligungsmeldungen: Namensfelder (auch verschachtelt) durch Anzahl und Kennung ersetzen."""
    if art != "bt":
        return m
    if isinstance(m, list):
        return [ohne_namen(art, x, tief + 1) for x in m]
    if not isinstance(m, dict):
        return m
    out = {}
    for k, v in m.items():
        if ist_namensfeld(k):
            werte = v if isinstance(v, list) else [v]
            werte = [w for w in werte if w not in (None, "")]
            out[k + "_n"] = len(werte)
            out[k + "_kennung"] = [kennung(w) for w in werte]
        else:
            out[k] = ohne_namen(art, v, tief + 1) if isinstance(v, (dict, list)) else v
    return out


def kopf(m):
    """Kennung und Felder der Meldung; bei Beteiligungen liegen sie unter «publication»."""
    p = m.get("publication") if isinstance(m.get("publication"), dict) else {}
    return lambda feld: m.get(feld) if m.get(feld) not in (None, "") else p.get(feld)


def lies_jahr(pfad):
    if not os.path.exists(pfad):
        return []
    with gzip.open(pfad, "rt", encoding="utf-8") as f:
        return [json.loads(z) for z in f if z.strip()]


def schreibe_jahr(pfad, zeilen):
    zeilen = sorted(zeilen, key=lambda z: (str(z["datum"]), str(z["id"]), int(z["fassung"])))
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        for z in zeilen:
            gz.write((json.dumps(z, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    with open(pfad, "wb") as f:
        f.write(buf.getvalue())


def abrufen(art, von, bis, hole_fn=hole, pause=PAUSE_S):
    """Alle Meldungen der Quelle im Zeitraum. Gibt (meldungen, totalCount, fehler) zurück."""
    cfg, alle, total, fehler, gesehen = ARTEN[art], [], None, None, set()
    for seite in range(MAX_SEITEN):
        url = (f"{BASIS}{cfg['pfad']}?pageSize={SEITE}&pageNumber={seite}&sortAttribute=byDate"
               f"&fromDate={von}&toDate={bis}")
        try:
            d = hole_fn(url)
        except urllib.error.HTTPError as e:
            fehler = f"HTTP {e.code} bei Seite {seite}"
            break
        except Exception as e:                       # Netz, Zeitlimit, kein JSON
            fehler = f"{type(e).__name__}: {str(e)[:120]} bei Seite {seite}"
            break
        if str(d.get("status", "")).lower() != "ok":
            fehler = f"Status {d.get('status')!r} bei Seite {seite}"
            break
        total = d.get("totalCount", total)
        teil = d.get("itemList") or []
        frisch = [m for m in teil if kopf(m)("notificationId") not in gesehen]
        if teil and not frisch:
            fehler = f"Seite {seite} wiederholt bekannte Meldungen (Blättern wirkt nicht)"
            break
        gesehen.update(kopf(m)("notificationId") for m in frisch)
        alle.extend(frisch)
        if not teil or (total is not None and len(alle) >= int(total)) or (total is None and len(teil) < SEITE):
            break
        time.sleep(pause)
    else:
        fehler = f"mehr als {MAX_SEITEN} Seiten"
    return alle, total, fehler


def archivieren(art, meldungen, zeit, erster_lauf, out=OUT):
    """Hängt neue Meldungen und neue Fassungen an. Gibt (neu, geaendert) zurück."""
    cfg = ARTEN[art]
    je_jahr = {}
    for m in meldungen:
        m = ohne_namen(art, m)
        mid, datum = str(kopf(m)("notificationId") or ""), str(kopf(m)(cfg["datum"]) or "")
        if not mid or len(datum) < 4:
            continue
        je_jahr.setdefault(datum[:4], []).append((mid, datum, m))
    neu = geaendert = 0
    for jahr, liste in sorted(je_jahr.items()):
        pfad = os.path.join(out, art, f"{jahr}.jsonl.gz")
        zeilen = lies_jahr(pfad)
        letzte = {}
        for z in zeilen:
            if z["id"] not in letzte or z["fassung"] > letzte[z["id"]]["fassung"]:
                letzte[z["id"]] = z
        dazu = []
        for mid, datum, m in liste:
            sha = kennung(m)
            alt = letzte.get(mid)
            if alt is not None and alt["inhalt_sha"] == sha:
                continue
            z = {"id": mid, "datum": datum, "erstmals_gesehen_utc": zeit, "nachgeladen": bool(erster_lauf and alt is None),
                 "fassung": 1 if alt is None else int(alt["fassung"]) + 1, "inhalt_sha": sha, "meldung": m}
            letzte[mid] = z; dazu.append(z)
            if alt is None:
                neu += 1
            else:
                geaendert += 1
        if dazu:
            schreibe_jahr(pfad, zeilen + dazu)
    return neu, geaendert


def lauf(out=OUT, hole_fn=hole, pause=PAUSE_S, zeit=None):
    zeit = zeit or jetzt_utc()
    stempel = zeit.strftime("%Y-%m-%dT%H:%M:%SZ")
    sp = os.path.join(out, "stand.json")
    stand = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
    bis = (zeit + timedelta(days=1)).strftime("%Y%m%d")
    for art in ARTEN:
        s = stand.setdefault(art, {"laeufe": 0, "meldungen": 0, "fassungen_geaendert": 0})
        erster = not s.get("bestand_geladen_utc")
        von = ANFANG if erster else (zeit - timedelta(days=RUECKBLICK_TAGE)).strftime("%Y%m%d")
        meldungen, total, fehler = abrufen(art, von, bis, hole_fn, pause)
        neu = geaendert = 0
        if meldungen:
            # beim ersten Lauf nur dann als vollständiger Bestand werten, wenn ohne Fehler alles kam
            neu, geaendert = archivieren(art, meldungen, stempel, erster, out)
        if erster and fehler is None:
            s["bestand_geladen_utc"] = stempel
            daten = [str(kopf(m)(ARTEN[art]["datum"])) for m in meldungen if kopf(m)(ARTEN[art]["datum"])]
            s["bestand_aeltestes_datum"] = min(daten) if daten else None
            s["bestand_anzahl"] = len(meldungen)
        s.update({"laeufe": s["laeufe"] + 1, "letzter_lauf_utc": stempel, "letzter_zeitraum": [von, bis],
                  "quelle_totalcount": total, "letzter_abruf_n": len(meldungen), "letzter_lauf_neu": neu,
                  "letzter_lauf_geaendert": geaendert, "meldungen": s["meldungen"] + neu,
                  "fassungen_geaendert": s["fassungen_geaendert"] + geaendert, "letzter_fehler": fehler})
        if fehler:
            s["fehler_seit_utc"] = s.get("fehler_seit_utc") or stempel
        else:
            s.pop("fehler_seit_utc", None)
        print(f"SIX {art}: {len(meldungen)} abgerufen ({von}–{bis}), {neu} neu, {geaendert} geändert, "
              f"Quelle meldet {total}; Fehler: {fehler}", file=sys.stderr)
        if fehler and fehler.startswith(("HTTP 403", "HTTP 429")):
            break                                    # Sperre: kein Umweg, kein weiterer Abruf in diesem Lauf
    stand["hinweis"] = ("Nur Archiv, nicht im Suchraum. erstmals_gesehen_utc ist der Beleg der Verfügbarkeit; "
                        "nachgeladen=true heisst: Publikationszeitpunkt unbekannt (Bestand des ersten Laufs).")
    os.makedirs(out, exist_ok=True)
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(stand, f, ensure_ascii=False, indent=1, sort_keys=True)
    return stand


if __name__ == "__main__":
    try:
        lauf()
    except Exception as e:                           # Archiv darf den Datenspiegel nie stoppen
        print(f"SIX-Archiv: unerwarteter Fehler {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(0)
