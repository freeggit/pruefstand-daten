#!/usr/bin/env python3
"""Prüfstand – eingefrorener Discovery-Stand (Verfassung V3.18, E9 Stufe 2). ENTWURF, Fassung 2 vom 28.10.2026 nach
Astra-Gutachten 23 (M1: nur eingefrorene Fassungen unterliegen der Einfrierprüfung; Soll: Revisionsbericht nach
geändert, hinzugekommen und entfallen). Nicht in Kraft.

Zweck: Die Suche rechnet nur neu, wenn sich eine massgebliche Eingabe wirklich geändert hat. Die täglichen Spiegel
liefern die Daten bis 31.12.2020 aber nicht Zeichen für Zeichen gleich: Angepasste Kurse von Yahoo schwanken in der
letzten Stelle, FRED-SP500 verschiebt seinen Beginn, NTSB-Unfälle wandern um einen Tag, Wetterdaten wechseln die
Fassung. Darum liest die Discovery ihre Daten aus einem eingefrorenen Stand:

1. Jede Datei, die die Suchmaschine über lade() liest (ausser Manifesten *.json), wird bei ihrer ersten Verwendung
   einmal gekürzt (nur Zeilen bis zum Stichtag 31.12.2020) und mit Prüfsumme im Stand abgelegt.
2. Danach liest die Suche nur noch diese Datei. Der Spiegel ändert sie nicht.
3. Weicht der Spiegel bis zum Stichtag vom Stand ab (Revision), wird das berichtet (Revisionsbericht), aber nur
   übernommen, wenn nachfuehrung.json auf main einen Eintrag mit Grund und Freigabe nennt. Jeder Eintrag wirkt je Datei
   genau einmal.
4. Manifeste werden nicht eingefroren: Sie bestimmen weiter, welche Reihen es gibt (neue, ruhende, gesperrte Reihen).
5. Einfrierprüfung (pruefen): Jede eingefrorene Fassung des Stands passt zu ihrer Prüfsumme, ihr Datum ist sicher
   lesbar und sie enthält keine Zeile nach dem Stichtag. Nicht eingefrorene Dateien (nicht sicher kürzbar) stehen nicht
   im Stand; für sie gilt wie bisher die Stichtagskürzung der Suchmaschine (31.12.2020, Familie L 31.12.2000).

Rückweg: AKTIV = False schaltet den Stand ab (suche_lauf.py und vorreg.py fragen diesen Schalter ab). Dann rechnet die
Suche wie bisher direkt auf den Spiegeln.

Ablage: Zweig claude/lernen, Ordner discovery/: stand.json (Verzeichnis), dateien/<Name>@<Prüfsumme> (Name wie im Cache
der Suchmaschine, z. B. kurse__spy_d.csv@1a2b3c4d5e6f7a8b) und revisionen.json (Revisionsbericht des letzten Laufs).
Eine Datei wird nie überschrieben: Eine Nachführung legt eine neue Fassung ab, und erst das neue stand.json (atomar
geschrieben) gilt. Bricht ein Lauf vorher ab, bleibt der bisherige Stand gültig.

Kürzen (die verbleibenden Zeilen bleiben Byte für Byte gleich, nur spätere Zeilen fallen weg):
- Die Datumsspalte ist je Quelle die Spalte, welche die Suchmaschine liest: Kurse «Date», FRED die erste Spalte, Scout
  und SEC «datum», Wetter und Strom «zeit_utc», Wikipedia «datum», Pegel «zeit», Bitcoin «timestamp» (Unix-Sekunden),
  Ken French der erste Wert der Zeile (JJJJMMTT, JJJJMM oder JJJJ).
- Eine Zeile bleibt, wenn ihr Datum (die ersten 10 Zeichen) höchstens «2020-12-31» ist. Der Stand behält so den
  ganzen Stichtag; die Suchmaschine kürzt beim Lesen weiterhin selbst (Siegel durch Bau) und liest genau dieselben
  Zeilen bis zum Stichtag wie aus dem Spiegel.
- Gzip-Dateien werden entpackt, gekürzt und mit mtime=0 neu gepackt; verglichen wird der entpackte Inhalt.
- Sicher kürzbar ist eine Datei nur, wenn die Quelle bekannt ist, die Datumsspalte im Kopf steht, keine
  Anführungszeichen vorkommen und jedes Datum lesbar ist (ISO bzw. Zahl). Sonst wird sie nicht eingefroren: Die
  Suchmaschine liest sie wie bisher ungekürzt aus dem Spiegel, und der Bericht nennt sie mit Grund.
"""
import fnmatch, gzip, hashlib, json, os, re
from collections import Counter
from datetime import datetime, timezone

AKTIV = True                                  # Rückweg: False = kein Stand, Suche wie bisher auf den Spiegeln
STICHTAG = "2020-12-31"
STICHTAG_EPOCH = 1609459199                   # 2020-12-31T23:59:59Z
REGEL = ("V3.18 E9 (Entwurf): Discovery-Daten bis 31.12.2020, eingefroren bei der ersten Verwendung; "
         "Revisionen nur über nachfuehrung.json mit Grund und Freigabe")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")
_FRENCH_GRENZE = {8: "20201231", 6: "202012", 4: "2020"}
# Datumsspalte je Quelle, wie suchmaschine.py sie liest (Präfix des Cache-Namens -> Art, Spalte; 0 = erste Spalte)
QUELLEN = (("french__", "french", None), ("kurse__", "iso", "Date"), ("fred__", "iso", 0), ("n__neu__", "iso", "datum"),
           ("sec__", "iso", "datum"), ("hr__wetter__", "iso", "zeit_utc"), ("e__hr__energie__", "iso", "zeit_utc"),
           ("hr__wiki__", "iso", "datum"), ("hr__pegel__", "iso", "zeit"), ("btc.csv", "epoch", "timestamp"))


def sha(b):
    return hashlib.sha256(b).hexdigest()


def _jetzt():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _entpacken(roh, name):
    return (gzip.decompress(roh), True) if name.endswith(".gz") else (roh, False)


def _packen(daten, gz):
    return gzip.compress(daten, compresslevel=9, mtime=0) if gz else daten


def inhalt_sha(roh, name):
    """Prüfsumme des entpackten Inhalts (unabhängig von der Gzip-Fassung)."""
    return sha(_entpacken(roh, name)[0])


def _quelle(name):
    for praefix, art, spalte in QUELLEN:
        if name.startswith(praefix):
            return art, spalte
    return None, None


def _pruefen_und_kuerzen(daten, name):
    """Gibt (behaltene Zeilen, Auskunft) zurück. Auskunft: sicher (bool), grund, art, zeilen, weg, spaeter."""
    zeilen = daten.splitlines(keepends=True)
    art, spalte = _quelle(name)
    aus = {"art": art, "spalte": spalte, "sicher": False}
    if art is None:
        return zeilen, dict(aus, grund="Quelle unbekannt")
    if art == "french":
        behalten, spaeter = [], 0
        for z in zeilen:
            f = z.split(b",", 1)[0].strip()
            if f.isdigit() and len(f) in _FRENCH_GRENZE and f.decode() > _FRENCH_GRENZE[len(f)]:
                spaeter += 1
                continue
            behalten.append(z)
        return behalten, dict(aus, sicher=True, zeilen=len(behalten), weg=spaeter, spaeter=spaeter)
    try:
        text = daten.decode("utf-8")
    except UnicodeDecodeError:
        return zeilen, dict(aus, grund="nicht UTF-8")
    if '"' in text:
        return zeilen, dict(aus, grund="Anführungszeichen")
    if not zeilen:
        return zeilen, dict(aus, grund="leer")
    kopf = [f.strip() for f in zeilen[0].decode("utf-8").lstrip("﻿").rstrip("\r\n").split(",")]
    if spalte == 0:
        idx = 0
    elif spalte in kopf:
        idx = kopf.index(spalte)
    else:
        return zeilen, dict(aus, grund=f"Datumsspalte {spalte} fehlt")
    behalten, spaeter = [zeilen[0]], 0
    for z in zeilen[1:]:
        s = z.decode("utf-8").rstrip("\r\n")
        if not s.strip():
            behalten.append(z)
            continue
        felder = s.split(",")
        if idx >= len(felder):
            return zeilen, dict(aus, grund="Zeile ohne Datum")
        w = felder[idx].strip()
        if art == "iso":
            if not _ISO.match(w):
                return zeilen, dict(aus, grund=f"Datum nicht lesbar: {w[:20]!r}")
            nach = w[:10] > STICHTAG
        else:
            try:
                nach = float(w) > STICHTAG_EPOCH
            except ValueError:
                return zeilen, dict(aus, grund=f"Zeitstempel nicht lesbar: {w[:20]!r}")
        if nach:
            spaeter += 1
        else:
            behalten.append(z)
    return behalten, dict(aus, sicher=True, zeilen=len(behalten) - 1, weg=spaeter, spaeter=spaeter)


def kuerzen(roh, name):
    """(Bytes für die Suchmaschine, Auskunft). Sicher kürzbar: nur Zeilen bis zum Stichtag. Sonst die Originalbytes."""
    daten, gz = _entpacken(roh, name)
    behalten, info = _pruefen_und_kuerzen(daten, name)
    if not info["sicher"]:
        return roh, info
    return _packen(b"".join(behalten), gz), info


def pruefe_inhalt(inhalt, name):
    """Einfrierprüfung einer abgelegten Datei: (in Ordnung, Grund)."""
    daten, _ = _entpacken(inhalt, name)
    _, info = _pruefen_und_kuerzen(daten, name)
    if not info["sicher"]:
        return False, f"nicht sicher lesbar: {info.get('grund')}"
    if info["spaeter"]:
        return False, f"{info['spaeter']} Zeile(n) nach dem Stichtag"
    return True, None


def _zahl(b):
    try:
        return float(b)
    except ValueError:
        return None


_FEHLT = {b"", b".", b"nan", b"NaN", b"NA", b"null", b"None"}   # fehlender Wert (FRED: «.»)


def unterschied(alt, neu, name):
    """Revisionsbericht für eine Datei, je Datum der abweichenden Zeilen (Gutachten 23, Soll): an gleichem Datum
    geändert, nur im Spiegel (hinzugekommen), nur im Stand (entfallen); fehlende Werte gesondert; grösste Abweichung einer
    Zahl absolut und relativ zum Wert im Stand (zeigt, ob es eine Rundung oder eine echte Revision ist). Ist der Wert im
    Stand null, ist die relative Abweichung nicht definiert: gezählt und nur absolut ausgewiesen."""
    a, _ = _entpacken(alt, name)
    b, _ = _entpacken(neu, name)
    za, zb = a.splitlines(), b.splitlines()
    art, spalte = _quelle(name)
    k = 0 if art == "french" else 1
    if art == "french":
        idx = None
    elif spalte == 0:
        idx = 0
    else:
        kopf = [f.strip() for f in (za or zb or [b""])[0].decode("utf-8", "replace").lstrip("﻿").split(",")]
        idx = kopf.index(spalte) if spalte in kopf else None
    if art == "french":   # Ken French: Textzeilen (Titel, «created using …») sind Kopf, nicht Daten (Gutachten 23, Soll)
        def _teilen(zz):
            dd, tt = [], []
            for z in zz:
                (dd if z.split(b",", 1)[0].strip().isdigit() else tt).append(z)
            return dd, tt
        (daten_a, text_a), (daten_b, text_b) = _teilen(za), _teilen(zb)
        kopf_anders = [z.strip() for z in text_a] != [z.strip() for z in text_b]
    else:
        daten_a, daten_b, kopf_anders = za[k:], zb[k:], za[:k] != zb[:k]
    ca, cb = Counter(daten_a), Counter(daten_b)
    nur_a, nur_b = ca - cb, cb - ca

    def schluessel(z):
        if art == "french" or idx is None:
            return z.split(b",", 1)[0].strip()
        f = z.split(b",")
        return f[idx].strip() if idx < len(f) else b""

    ka = {schluessel(z): z for z in nur_a}
    kb = {schluessel(z): z for z in nur_b}
    beide = set(ka) & set(kb)
    max_rel = max_abs = max_abs_null = 0.0
    rel_undef = fehlt_im_spiegel = neu_im_spiegel = 0
    for s in beide:
        for x, y in zip(ka[s].split(b","), kb[s].split(b",")):
            x, y = x.strip(), y.strip()
            if x == y:
                continue
            fx, fy = x in _FEHLT, y in _FEHLT
            if fx or fy:                                    # fehlender Wert: gesondert, keine Abweichung
                neu_im_spiegel += int(fx and not fy)
                fehlt_im_spiegel += int(fy and not fx)
                continue
            u, v = _zahl(x), _zahl(y)
            if u is None or v is None:
                continue
            d = abs(v - u)
            max_abs = max(max_abs, d)
            if u == 0:                                      # Bezugswert null: relativ nicht definiert
                rel_undef += 1
                max_abs_null = max(max_abs_null, d)
            else:
                max_rel = max(max_rel, d / abs(u))
    daten_ = sorted(s.decode("utf-8", "replace")[:10] for s in set(ka) | set(kb))
    return {"geaendert": len(beide), "hinzugekommen": len(set(kb) - set(ka)), "entfallen": len(set(ka) - set(kb)),
            "werte_fehlen_im_spiegel": fehlt_im_spiegel, "werte_neu_im_spiegel": neu_im_spiegel,
            "max_rel_abweichung": float(f"{max_rel:.3g}"), "max_abs_abweichung": float(f"{max_abs:.3g}"),
            "relativ_nicht_definiert": rel_undef, "max_abs_abweichung_bei_null": float(f"{max_abs_null:.3g}"),
            "zeilen_nur_stand": sum(nur_a.values()), "zeilen_nur_spiegel": sum(nur_b.values()),
            "kopf_geaendert": kopf_anders, "erstes_datum": daten_[0] if daten_ else None,
            "letztes_datum": daten_[-1] if daten_ else None}


class Stand:
    """Eingefrorener Discovery-Stand. schreiben=True nur in suche_lauf.py (Suche); Familie V liest nur."""

    def __init__(self, ordner, schreiben=False, bericht=False, nachfuehrung=None, lauf_id=None):
        self.ordner, self.dordner = ordner, os.path.join(ordner, "dateien")
        self.pfad = os.path.join(ordner, "stand.json")
        if os.path.exists(self.pfad):
            self.verz = json.load(open(self.pfad, encoding="utf-8"))   # ein beschädigtes Verzeichnis bricht ab
        else:
            self.verz = {"regel": REGEL, "stichtag": STICHTAG, "dateien": {}, "nachfuehrungen": {}}
        self.schreiben, self.bericht, self.lauf_id = schreiben, bericht, lauf_id
        self.aufrufe = 0
        self.neu, self.nachgefuehrt, self.revisionen, self.nicht_eingefroren, self.nur_gelesen = [], [], [], [], []
        self.nachfuehrung_fehler, self.eintraege, self.offen, self._ablage = [], [], {}, {}
        self.gelesen, self.gemeint = set(), {}           # in diesem Lauf bereitgestellte Dateien; je Eintrag gemeinte Dateien
        if nachfuehrung and os.path.exists(nachfuehrung):
            for e in json.load(open(nachfuehrung, encoding="utf-8")).get("eintraege", []):
                if not isinstance(e, dict) or not e.get("id"):
                    self.nachfuehrung_fehler.append({"id": None, "grund": "Eintrag ohne id: nicht angewandt"})
                    continue
                alt = self.verz["nachfuehrungen"].get(e["id"]) or {}
                if alt.get("vollstaendig"):
                    continue
                muster = e.get("dateien")
                if (not e.get("grund") or not e.get("freigabe") or not isinstance(muster, list) or not muster
                        or not all(isinstance(m, str) and m for m in muster)):
                    self.nachfuehrung_fehler.append({"id": e["id"], "grund": "ohne Grund, Freigabe oder Liste von Dateimustern: nicht angewandt"})
                    continue
                self.eintraege.append(e)
                erledigt = set(alt.get("dateien", []))
                # gemeint sind die Dateien, die beim ersten Anwenden des Eintrags schon eingefroren waren; später
                # aufgenommene Dateien gehören nicht dazu (sie brauchen einen eigenen Eintrag)
                self.gemeint[e["id"]] = (list(alt["gemeint"]) if "gemeint" in alt else
                                         sorted(n for n in self.verz["dateien"] if any(fnmatch.fnmatchcase(n, m) for m in muster)))
                for name in self.gemeint[e["id"]]:
                    if name not in erledigt and name in self.verz["dateien"]:
                        self.offen.setdefault(name, e["id"])

    def _gespeichert(self, name):
        """Inhalt der abgelegten Fassung oder RuntimeError (fehlt, Prüfsumme falsch)."""
        e = self.verz["dateien"][name]
        q = os.path.join(self.dordner, e["datei"])
        if not os.path.exists(q):
            raise RuntimeError(f"Discovery-Stand beschädigt: {name} fehlt (Behebung über nachfuehrung.json)")
        inhalt = open(q, "rb").read()
        if sha(inhalt) != e["sha"]:
            raise RuntimeError(f"Discovery-Stand beschädigt: {name} passt nicht zur Prüfsumme (Behebung über nachfuehrung.json)")
        return inhalt

    def _ablegen(self, name, schnitt, info, nachfuehrung=None, vorher=None):
        s = sha(schnitt)
        eintrag = {"datei": f"{name}@{s[:16]}", "sha": s, "sha_inhalt": inhalt_sha(schnitt, name), "zeilen": info["zeilen"],
                   "datum": f"{info['art']}:{info['spalte']}", "aufgenommen_utc": _jetzt(), "lauf_id": self.lauf_id}
        if nachfuehrung:
            eintrag.update({"nachfuehrung": nachfuehrung, "vorher_sha": vorher["sha"],
                            "erstmals_aufgenommen_utc": vorher.get("erstmals_aufgenommen_utc", vorher.get("aufgenommen_utc"))})
        self._ablage[name] = (schnitt, eintrag)

    def bereitstellen(self, name, holen, ziel):
        """Schreibt den Inhalt für die Suchmaschine nach ziel: eingefroren, falls vorhanden; sonst aus dem Spiegel,
        gekürzt, wenn sicher kürzbar (und bei schreiben=True zum Einfrieren vorgemerkt; abgelegt erst in abschliessen).
        holen() liefert die Bytes aus dem Spiegel."""
        self.aufrufe += 1
        self.gelesen.add(name)
        e = self.verz["dateien"].get(name)
        if name in self.offen:                              # Nachführung: auch eine beschädigte Fassung wird ersetzt
            eid = self.offen[name]
            try:
                schnitt, info = kuerzen(holen(), name)
                if not info["sicher"]:
                    raise ValueError(f"Spiegel nicht sicher kürzbar: {info.get('grund')}")
            except Exception as ex:
                self.nachfuehrung_fehler.append({"id": eid, "datei": name, "grund": f"nicht angewandt, Stand bleibt: {str(ex)[:100]}"})
                self.offen.pop(name)
                inhalt = self._gespeichert(name)            # bricht ab, wenn auch die alte Fassung fehlt
                with open(ziel, "wb") as f:
                    f.write(inhalt)
                return
            with open(ziel, "wb") as f:
                f.write(schnitt)
            if self.schreiben:
                self._ablegen(name, schnitt, info, nachfuehrung=eid, vorher=e)
                self.nachgefuehrt.append({"datei": name, "id": eid, "vorher_sha": e["sha"][:16], "neu_sha": sha(schnitt)[:16],
                                          "inhalt_gleich": e.get("sha_inhalt") == inhalt_sha(schnitt, name)})
            return
        if e is not None:
            inhalt = self._gespeichert(name)
            with open(ziel, "wb") as f:
                f.write(inhalt)
            if self.bericht:
                try:
                    live, info = kuerzen(holen(), name)
                except Exception as ex:
                    self.revisionen.append({"datei": name, "spiegel": f"nicht lesbar: {str(ex)[:80]}"})
                    return
                if not info["sicher"]:
                    self.revisionen.append({"datei": name, "spiegel": f"nicht sicher kürzbar: {info.get('grund')}"})
                elif inhalt_sha(live, name) != e.get("sha_inhalt"):
                    self.revisionen.append(dict({"datei": name}, **unterschied(inhalt, live, name)))
            return
        roh = holen()                                       # neue Datei; nicht lesbar: wie bisher (Suchmaschine entscheidet)
        schnitt, info = kuerzen(roh, name)
        with open(ziel, "wb") as f:
            f.write(schnitt)
        if not info["sicher"]:
            self.nicht_eingefroren.append({"datei": name, "grund": info.get("grund")})   # wie bisher ungekürzt gelesen
            return
        if not self.schreiben:
            self.nur_gelesen.append(name)                   # nur gelesen, nicht eingefroren (Familie V)
            return
        self._ablegen(name, schnitt, info)
        self.neu.append(name)

    def abschliessen(self):
        """Legt vorgemerkte Dateien ab, schreibt stand.json atomar (nur bei schreiben=True und Änderung), räumt ersetzte
        Fassungen weg und gibt den Bericht für den Laufeintrag zurück."""
        angewandt, ersetzt, vermerkt = [], [], False
        if self.schreiben:
            if self._ablage:
                os.makedirs(self.dordner, exist_ok=True)
                for name, (schnitt, eintrag) in self._ablage.items():
                    q = os.path.join(self.dordner, eintrag["datei"])
                    if not (os.path.exists(q) and sha(open(q, "rb").read()) == eintrag["sha"]):
                        with open(q + ".tmp", "wb") as f:
                            f.write(schnitt)
                        os.replace(q + ".tmp", q)
                    alt = self.verz["dateien"].get(name)
                    if alt and alt.get("datei") != eintrag["datei"]:
                        ersetzt.append(alt["datei"])
                    self.verz["dateien"][name] = eintrag
            for e in self.eintraege:
                alt = self.verz["nachfuehrungen"].get(e["id"]) or {}
                gemeint = self.gemeint[e["id"]]
                jetzt_erledigt = {x["datei"] for x in self.nachgefuehrt if x["id"] == e["id"]}
                erledigt = sorted(set(alt.get("dateien", [])) | jetzt_erledigt)
                rest = sorted(set(gemeint) - set(erledigt))
                if not gemeint:
                    self.nachfuehrung_fehler.append({"id": e["id"], "grund": "Muster trifft keine Datei im Stand"})
                if jetzt_erledigt:
                    angewandt.append(e["id"])
                vermerkt = vermerkt or bool(jetzt_erledigt) or not alt
                self.verz["nachfuehrungen"][e["id"]] = {"grund": e["grund"], "freigabe": e["freigabe"], "muster": e["dateien"],
                                                        "gemeint": gemeint, "dateien": erledigt, "offen": rest,
                                                        "vollstaendig": bool(gemeint) and not rest,
                                                        "erstmals_angewandt_utc": alt.get("erstmals_angewandt_utc") or (_jetzt() if erledigt else None),
                                                        "zuletzt_utc": _jetzt(), "lauf_id": self.lauf_id}
            if self._ablage or vermerkt:
                self.verz["dateien"] = dict(sorted(self.verz["dateien"].items()))
                self.verz.update({"stand_utc": _jetzt(), "dateien_n": len(self.verz["dateien"])})
                os.makedirs(self.ordner, exist_ok=True)
                with open(self.pfad + ".tmp", "w", encoding="utf-8") as f:
                    json.dump(self.verz, f, ensure_ascii=False, indent=1)
                os.replace(self.pfad + ".tmp", self.pfad)    # erst jetzt gilt der neue Stand
                for d in ersetzt:                            # ersetzte Fassungen (Geschichte bleibt im Git-Verlauf)
                    try:
                        os.remove(os.path.join(self.dordner, d))
                    except OSError:
                        pass
        gruppen = Counter(r["datei"].split("__")[0] if not r["datei"].startswith(("n__", "e__")) else
                          "__".join(r["datei"].split("__")[:2]) for r in self.revisionen)
        summe = Counter()                                    # Gutachten 23 (Soll): Summen über alle Dateien
        for r in self.revisionen:
            for f in ("geaendert", "hinzugekommen", "entfallen", "werte_fehlen_im_spiegel", "werte_neu_im_spiegel",
                      "relativ_nicht_definiert"):
                summe[f] += int(r.get(f) or 0)
        return {"regel": REGEL, "dateien_n": len(self.verz["dateien"]), "neu_eingefroren_n": len(self.neu),
                "neu_eingefroren": self.neu, "nachgefuehrt": self.nachgefuehrt, "nachfuehrung_angewandt": angewandt,
                "nachfuehrung_fehler": self.nachfuehrung_fehler, "nicht_eingefroren": self.nicht_eingefroren,
                "nur_gelesen_nicht_eingefroren": self.nur_gelesen, "gelesen": sorted(self.gelesen),
                "revisionen_n": len(self.revisionen), "revisionen_je_gruppe": dict(sorted(gruppen.items())),
                "revisionen_summe": dict(summe), "revisionen": self.revisionen}


def pruefen(ordner, gelesen=None):
    """Einfrierprüfung: Jede Datei des Verzeichnisses ist vorhanden, passt zur Prüfsumme, ist sicher lesbar und hat
    keine Zeile nach dem Stichtag. gelesen: Namen der Dateien, welche die Suche in diesem Lauf liest. Ein Mangel an einer
    gelesenen Datei ist ein Verstoss (es wird nicht gerechnet); an einer nicht gelesenen Datei ein Befund (sie wirkt nicht
    auf die Discovery). Ohne gelesen zählt jeder Mangel als Verstoss. verstoesse leer heisst bestanden."""
    pfad = os.path.join(ordner, "stand.json")
    if not os.path.exists(pfad):
        return {"dateien_n": 0, "verstoesse": [], "befunde_nicht_gelesen": [], "ohne_eintrag": []}
    verz = json.load(open(pfad, encoding="utf-8"))
    dordner = os.path.join(ordner, "dateien")
    verstoesse, befunde = [], []
    for name, e in verz.get("dateien", {}).items():
        liste = verstoesse if gelesen is None or name in gelesen else befunde
        q = os.path.join(dordner, e.get("datei", ""))
        if not e.get("datei") or not os.path.exists(q):
            liste.append({"datei": name, "grund": "fehlt"})
            continue
        b = open(q, "rb").read()
        if sha(b) != e.get("sha") or inhalt_sha(b, name) != e.get("sha_inhalt"):
            liste.append({"datei": name, "grund": "Prüfsumme passt nicht"})
            continue
        gut, grund = pruefe_inhalt(b, name)
        if not gut:
            liste.append({"datei": name, "grund": grund})
    genutzt = {e.get("datei") for e in verz.get("dateien", {}).values()}
    extra = sorted(set(os.listdir(dordner)) - genutzt) if os.path.isdir(dordner) else []
    return {"dateien_n": len(verz.get("dateien", {})), "verstoesse": verstoesse, "befunde_nicht_gelesen": befunde,
            "ohne_eintrag": extra}
