"""Prüfstand – Vorwärtsregister (Verfassung V3.15, E32; Astra-Gutachten 7 und 8): Handelsbuch, Status und Versionsbindung.

Das Register wird EXPLORATIV geführt (E32g): Ein Strang ergibt ein beschreibendes Papierergebnis, keine Aussage mit 5%
Fehlalarm. Ein Strang ist eine feste Regel oder ein Bündel aus 2 bis 5 Regeln, gleich gewichtet. Er wird als Datei
vorwaerts/<Kennung>.json auf main registriert. Massgebender Beginn ist der Tag, an dem dieses Programm die Datei erstmals
auf main sieht (G8-09); der Commit, mit dem sie auf main kam, wird archiviert.

Zwei Schichten (G8-04):
  A. Festgeschriebener Code des Strangs. Die Registrierung nennt eine vollständige Commit-Kennung (code_commit, 40 Zeichen),
     die beim Eintritt der Registrierung schon auf main lag. Alles, was das Ergebnis eines Strangs bestimmt, rechnet der
     Code dieses Commits in einem eigenen Prozess aus einem eigenen Arbeitsbaum: Prüfung der Registrierung («pruefe»),
     Kalender und Auslöser («finde»), Frist, Sperrfrist und Auftragsentscheid («buche»), Kursaufbereitung, Kosten,
     Gültigkeit der Aufträge und Aggregation («schliesse»).
  B. Dispatcher (dieser Stand). Er transportiert und speichert: Dateien lesen, Zeitstempel setzen, Journale fortschreiben.
     Dazu kommen die Schutzregeln über alle Stränge: Freigabemodus, Stopp bei Änderung, Öffnungssperre (E32f),
     Vorgänger derselben Regel, Kapazität. Ändert sich der Dispatcher, während ein Strang läuft, braucht der neue Stand
     einen Eintrag in vorwaerts/dispatcher_freigaben.json; sonst bricht der Lauf ab (keine stille Übernahme).

Zeit (G8-01): Je Auftrag drei Zeiten. lauf_start_utc, erkannt_utc (Uhr NACH der Signalrechnung des Strangs),
gespeichert_utc (Uhr beim Schreiben ins Handelsbuch). Dazu kommt bei der Schlussauswertung veroeffentlicht_utc (Zeit des
Commits auf claude/lernen, mit dem die Zeile erschien). Ein Auftrag gilt nur, wenn erkannt, gespeichert und veröffentlicht
vor der Frist des Einstiegstags liegen; sonst verfällt er (kein rückwirkender Auftrag).

Kalender (G8-02): Der Auftrag hält die erwarteten Handelssitzungen und den Ausstieg aus dem Kalender des festgeschriebenen
Codes fest. Die Auswertung richtet die Kurse auf genau diese Sitzungen aus. Fehlt eine Zeile (auch im Vergleichsindex)
oder eine ganze Datei, ist der Auftrag «nicht auswertbar»; nichts wird verschoben. Ausserordentliche Schliessungen der
Börse stehen in vorwaerts/sonderschliessungen.json (Tag, Quelle, Freigabe); nur ein solcher Eintrag verschiebt Sitzungen.

Journale (G8-06, G8-07): status.jsonl ist massgebend; der Stand wird bei jedem Lauf daraus neu aufgebaut (stand.json ist
nur eine Ansicht und wird nie gelesen). Jede Zeile wird sofort und dauerhaft angehängt. Reservierung und Ergebnis der
Schlussauswertung werden vollständig in eine Hilfsdatei geschrieben und dann unteilbar veröffentlicht. Ein Lauf gleicht
zuerst ab: Ergebnis vorhanden -> ausgewertet; Reservierung vorhanden -> reserviert.

Siegel (G8-12, genau): Der Signalrechner erhält als Basis eine Kopie, deren Kursdateien nur Zeilen bis zum Stichtag
enthalten. Das ist ein Schutz des Recheninputs, keine vollständige Zugriffssperre des Prozesses. Der Zuschnitt der
Signalquellen auf registrierte Reihen folgt vor dem ersten echten Strang (V3.15, E32i).

Aufruf (in der Action): python vorwaerts.py      Tests: python test_vorwaerts.py
Umgebung: PS_VORWAERTS_DIR (Registrierungen), PS_VORWAERTS_LOG (Journale), PS_VORWAERTS_STAND
(«main=<commit>;neu=<commit>;energie=<commit>», vollständige Kennungen).
"""
import datetime, hashlib, json, math, os, subprocess, sys, tempfile, types
import numpy as np

HIER = os.path.dirname(os.path.abspath(__file__))
PROTOKOLL = 2                # Schnittstelle zwischen Dispatcher und festgeschriebenem Code
MODI = ("gesperrt", "uebung", "offen")   # Freigabemodus aus vorwaerts/freigabe.json; fehlt die Datei: gesperrt (V3.15 E32i)
MAX_STRAENGE = 3             # gleichzeitig belegte Plätze echter Stränge: aktiv oder reserviert (Aufwand, keine Fehlerkontrolle)
MAX_JAHRE = 5.0
MIN_EREIGNISSE = 10
NIVEAU, STAERKE, ALTERNATIVE = 0.05, 0.40, 3.0
HALTEDAUERN = (1, 5, 20)
HALTEDAUERN_K = (60, 120, 250)
FRIST_UTC = datetime.time(13, 30)        # Auftrag nur, wenn vor dieser Uhrzeit des Einstiegstags erkannt, gespeichert und veröffentlicht
RUECKDATIERUNG_TAGE = 3                  # «registriert» und der Commit dürfen höchstens so viele Tage vor dem ersten Sehen liegen
WARTEN_TAGE = 30                         # so lange wartet die Schlussauswertung auf Kurse bis zum letzten Ausstieg
KOSTEN_MAX = 5.0
STICHTAG = "2020-12-31"
PFLICHT = ("kennung", "art", "registriert", "regeln", "kosten_pp", "letzter_einstieg", "schlusstag", "min_ereignisse",
           "vorpruefung", "code_commit", "freigabe", "mechanismus")
ARTEN = ("hoch", "tief", "sprung_auf", "sprung_ab")
N_BIS_ERWARTET = 11                      # Vorkommen von «bis(» in suchmaschine.py samt Definition
UNTERTAEGIG = ("wetter_", "strom_")      # Indikatoren aus Stundenwerten; der letzte Tag kann unvollständig sein
ENDGUELTIG = ("gestoppt", "abgewiesen", "beendet_ohne_urteil", "ausgewertet")
OFFEN = ("aktiv", "reserviert")
OEFFNUNG = "bestaetigung_geoeffnet.json"  # liegt diese Datei neben den Registrierungen, greift E32f
FREIGABE = "freigabe.json"
DISPATCHER = "dispatcher_freigaben.json"
SONDER = "sonderschliessungen.json"
STEUERDATEIEN = (OEFFNUNG, FREIGABE, DISPATCHER, SONDER)
VERMERK = "veroeffentlicht.jsonl"         # je gelungenem Push: Zeit und Länge der Journale (Zeitnachweis der Veröffentlichung, G9-03)
ZWEIG = "claude/lernen"
UMGEBUNG_ERLAUBT = ("PS_BASIS_NEU", "PS_BASIS_ENERGIE")   # nur diese PS_-Variablen erreichen den festgeschriebenen Code (G9-04)


class Abbruch(Exception):
    """Kontrollierter Abbruch: Es wurde nichts Halbes geschrieben; der nächste Lauf setzt sauber fort."""


# ====================================================================================== Kalender (regelbasiert, NYSE)
def ostern(j):
    a = j % 19; b, c = divmod(j, 100); d, e = divmod(b, 4); f = (b + 8) // 25; g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30; i, k = divmod(c, 4); l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    return datetime.date(j, (h + l_ - 7 * m + 114) // 31, (h + l_ - 7 * m + 114) % 31 + 1)


def _n_ter(j, monat, wochentag, n):
    """n-ter Wochentag (0 = Montag) eines Monats; n = -1 ist der letzte."""
    if n > 0:
        t = datetime.date(j, monat, 1); t += datetime.timedelta((wochentag - t.weekday()) % 7)
        return t + datetime.timedelta(7 * (n - 1))
    t = datetime.date(j + (monat == 12), monat % 12 + 1, 1) - datetime.timedelta(1)
    return t - datetime.timedelta((t.weekday() - wochentag) % 7)


def nyse_feiertage(j):
    """Planmässige ganztägige Schliessungen der NYSE nach den festen Regeln (ohne ausserordentliche Schliessungen)."""
    def beob(t):                                   # Samstag -> Freitag, Sonntag -> Montag
        return t - datetime.timedelta(1) if t.weekday() == 5 else t + datetime.timedelta(1) if t.weekday() == 6 else t
    f = {_n_ter(j, 1, 0, 3), _n_ter(j, 2, 0, 3), ostern(j) - datetime.timedelta(2), _n_ter(j, 5, 0, -1),
         beob(datetime.date(j, 7, 4)), _n_ter(j, 9, 0, 1), _n_ter(j, 11, 3, 4), beob(datetime.date(j, 12, 25))}
    n = datetime.date(j, 1, 1)
    if n.weekday() != 5:                           # Neujahr an einem Samstag wird nicht vorgeholt
        f.add(beob(n))
    if j >= 2022:
        f.add(beob(datetime.date(j, 6, 19)))       # Juneteenth, seit 2022
    return f


def nyse_handelstage(von, bis):
    """Handelstage von «von» bis «bis» (je einschliesslich) nach dem regelbasierten Kalender."""
    out, feier, t = [], {}, von
    while t <= bis:
        if t.weekday() < 5:
            if t.year not in feier:
                feier[t.year] = nyse_feiertage(t.year)
            if t not in feier[t.year]:
                out.append(t)
        t += datetime.timedelta(1)
    return out


# ============================================================================================== reine Funktionen
def dauer_jahre(jahresschwankung, alternative=ALTERNATIVE, niveau=NIVEAU, staerke=STAERKE):
    """Planungsdauer in Jahren (Normalnäherung), aufgerundet auf volle Halbjahre. Eine Planung, keine Teststärke."""
    from statistics import NormalDist
    z = NormalDist().inv_cdf(1 - niveau) + NormalDist().inv_cdf(staerke)
    return math.ceil(2 * (jahresschwankung * z / alternative) ** 2 - 1e-9) / 2.0


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tag(s):
    return datetime.date.fromisoformat(str(s)[:10])


def _zeit(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def _fmt(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _zahl(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _ganz(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _text(x):
    return isinstance(x, str) and x.strip() != ""


def _hex40(x):
    return isinstance(x, str) and len(x) == 40 and all(c in "0123456789abcdef" for c in x)


def _kennung_ok(x):
    return isinstance(x, str) and 1 <= len(x) <= 40 and all(c.isascii() and (c.isalnum() or c in "_-") for c in x)


def regel_schluessel(r):
    return f"{r['indikator']}|{r['art']}|{r['ziel']}|{int(r['h'])}"


def kanon(k):
    """Kanonischer Regelschlüssel «indikator|art|ziel|h» (G8-08). Nimmt auch die Kennungen der Auswahl:
    «S|indikator|art|ziel|h» und «V|<Hypothesen-ID>|indikator|art|ziel|h». Alles andere ist ein Fehler."""
    if not isinstance(k, str):
        raise ValueError(f"Regelschlüssel ist kein Text: {k!r}")
    t = k.split("|")
    if len(t) == 5 and t[0] == "S":
        t = t[1:]
    elif len(t) == 6 and t[0] == "V":
        t = t[2:]
    if len(t) != 4 or not t[0] or not t[2] or t[1] not in ARTEN or not t[3].isdigit() or int(t[3]) not in HALTEDAUERN + HALTEDAUERN_K:
        raise ValueError(f"Regelschlüssel nicht lesbar: {k!r}")
    return f"{t[0]}|{t[1]}|{t[2]}|{int(t[3])}"


def stand_lesen(text):
    """Datenstand «main=<commit>;neu=<commit>;energie=<commit>» als dict mit vollständigen Kennungen; sonst None (G8-05)."""
    if not isinstance(text, str):
        return None
    d = dict(t.split("=", 1) for t in text.split(";") if "=" in t)
    d = {k: v.strip().lower() for k, v in d.items()}
    return {k: d[k] for k in ("main", "neu", "energie")} if set(d) == {"main", "neu", "energie"} and all(_hex40(v) for v in d.values()) else None


def oeffnungsmarker(auswahl_ergebnis, geoeffnet_utc, freigabe):
    """Inhalt von vorwaerts/bestaetigung_geoeffnet.json aus dem Ergebnis von auswahl.py (finalist.regeln), kanonisch."""
    regeln = sorted({kanon(k) for k in auswahl_ergebnis["finalist"]["regeln"]})
    _zeit(geoeffnet_utc)
    if not regeln or not _text(freigabe):
        raise ValueError("Öffnungsmarker braucht mindestens eine Regel und den Wortlaut der Freigabe")
    return dict(geoeffnet_utc=geoeffnet_utc, regeln=regeln, freigabe=freigabe)


def marker_lesen(text):
    """Regeln des Öffnungsmarkers, kanonisch. Jeder Mangel ist ein Abbruch: Ein unklarer Marker blockiert (G8-08)."""
    try:
        d = json.loads(text)
        if not isinstance(d, dict) or not isinstance(d.get("regeln"), list) or not d["regeln"] or not _text(d.get("freigabe")):
            raise ValueError("Pflichtfelder geoeffnet_utc, regeln (nicht leer), freigabe")
        _zeit(d.get("geoeffnet_utc") if isinstance(d.get("geoeffnet_utc"), str) else "")                 # Zeit muss lesbar sein (JJJJ-MM-TTThh:mm:ssZ)
        return sorted({kanon(k) for k in d["regeln"]})
    except ValueError as e:
        raise Abbruch(f"Öffnungsmarker {OEFFNUNG} ist ungültig ({e}); das Register rechnet nicht weiter, bis er berichtigt ist.")


def pruefe_registrierung(d, beginn):
    """Gibt eine Liste von Fehlern zurück (leer = gültig). beginn: Tag, an dem das Register die Datei erstmals auf main sah."""
    if not isinstance(d, dict):
        return ["Die Registrierung muss ein JSON-Objekt sein"]
    f = [f"Feld fehlt: {k}" for k in PFLICHT if k not in d]
    if f:
        return f
    if not _kennung_ok(d["kennung"]):
        f.append("kennung: 1 bis 40 Zeichen aus Buchstaben, Ziffern, _ und -")
    if d["art"] not in ("strang", "uebung", "typ_k"):
        f.append("art muss strang, uebung oder typ_k sein"); return f
    r = d["regeln"]
    if not isinstance(r, list) or not 1 <= len(r) <= 5:
        f.append("1 bis 5 Regeln"); return f
    erlaubt = HALTEDAUERN_K if d["art"] == "typ_k" else HALTEDAUERN
    for x in r:
        if not isinstance(x, dict) or set(x) != {"indikator", "art", "ziel", "h"}:
            f.append(f"Regel braucht genau indikator, art, ziel, h: {x}"); continue
        if not _text(x["indikator"]) or not _text(x["ziel"]) or "|" in x["indikator"] or "|" in x["ziel"]:
            f.append(f"indikator und ziel: Text ohne das Zeichen |: {x}")
        if x["art"] not in ARTEN:
            f.append(f"Extremtyp unbekannt: {x['art']}")
        if not _ganz(x["h"]) or x["h"] not in erlaubt:
            f.append(f"Haltedauer {x['h']} nicht zulässig für art {d['art']}")
    if f:
        return f
    if len({x["ziel"] for x in r}) != len(r):
        f.append("je Ziel höchstens eine Regel")
    if not _hex40(d["code_commit"]):
        f.append("code_commit: vollständige Commit-Kennung (40 Zeichen, klein), kein Zweigname und kein Kürzel")
    if not (_zahl(d["kosten_pp"]) and 0 < d["kosten_pp"] <= KOSTEN_MAX):
        f.append(f"kosten_pp: endliche Zahl über 0 und höchstens {KOSTEN_MAX}")
    if not _ganz(d["min_ereignisse"]) or d["min_ereignisse"] < MIN_EREIGNISSE:
        f.append(f"min_ereignisse: ganze Zahl, mindestens {MIN_EREIGNISSE}")
    fr = d["freigabe"]
    if not (isinstance(fr, dict) and set(fr) == {"wortlaut", "datum", "kennung"} and _text(fr["wortlaut"]) and isinstance(fr["datum"], str) and len(fr["datum"]) == 10):
        f.append("freigabe: {wortlaut, datum (JJJJ-MM-TT), kennung}")
    elif fr["kennung"] != d["kennung"]:
        f.append("freigabe.kennung muss genau die Kennung dieses Strangs sein (G9-07)")
    else:
        try:
            if _tag(fr["datum"]) > beginn:
                f.append("freigabe.datum liegt nach dem Beginn")
        except ValueError:
            f.append("freigabe.datum nicht lesbar (JJJJ-MM-TT)")
    if not _text(d["mechanismus"]):
        f.append("mechanismus: ökonomische Begründung in einem Satz")
    vg = d.get("vorgaenger", [])
    if not isinstance(vg, list) or not all(_kennung_ok(x) for x in vg):
        f.append("vorgaenger: Liste von Kennungen (oder weglassen)")
    try:
        if not all(isinstance(d[k], str) for k in ("registriert", "letzter_einstieg", "schlusstag")):
            raise ValueError
        reg, le, st = _tag(d["registriert"]), _tag(d["letzter_einstieg"]), _tag(d["schlusstag"])
    except (ValueError, TypeError):
        f.append("Datum nicht lesbar (JJJJ-MM-TT)"); return f
    if not (0 <= (beginn - reg).days <= RUECKDATIERUNG_TAGE):
        f.append(f"registriert ({reg}) passt nicht zum Beginn ({beginn}): höchstens {RUECKDATIERUNG_TAGE} Tage davor, nie danach")
    if not beginn < le < st:
        f.append("Reihenfolge: Beginn < letzter_einstieg < schlusstag")
        return f
    hmax = max(int(x["h"]) for x in r)
    tage = nyse_handelstage(le, st)                       # Haltefenster des letzten Einstiegs nach dem Handelskalender
    if not tage or tage[0] != le:
        f.append("letzter_einstieg ist kein Handelstag")
    elif len(tage) < hmax + 1:
        f.append(f"das Haltefenster des letzten Einstiegs ({hmax} Handelstage) läuft nicht vor dem Schlusstag aus")
    if d["art"] != "uebung":
        tage_dauer = (st - beginn).days
        if tage_dauer > math.ceil(MAX_JAHRE * 365.25):
            f.append(f"Dauer über {MAX_JAHRE} Jahre")
        vp = d["vorpruefung"] if isinstance(d["vorpruefung"], dict) else {}
        s = vp.get("jahresschwankung_pp")
        if not _zahl(s) or s <= 0:
            f.append("vorpruefung.jahresschwankung_pp fehlt (endliche Jahresschwankung des Strangs in der Discovery)")
        elif not _text(vp.get("beleg")):
            f.append("vorpruefung.beleg fehlt (Verweis auf die Rechnung der Jahresschwankung, z. B. Lauf-ID und Datei)")
        else:
            soll = dauer_jahre(float(s))
            if soll > MAX_JAHRE:
                f.append(f"Jahresschwankung {s} pp braucht {soll} Jahre: mehr als {MAX_JAHRE}, keine Registrierung")
            elif tage_dauer < math.ceil(soll * 365.25) - RUECKDATIERUNG_TAGE:      # Tagesregel: die Toleranz ist genau der zulässige Vorlauf der Registrierung
                f.append(f"Dauer {tage_dauer} Tage ist kürzer als die Planungsdauer {soll} Jahre zur Jahresschwankung {s} pp")
    return f


def pruefe_sicher(d, beginn):
    """Wie pruefe_registrierung, aber ausfallsicher: Jede unerwartete Form ergibt eine Ablehnung, keinen Abbruch (G8-10)."""
    try:
        return pruefe_registrierung(d, _tag(beginn))
    except Exception as e:                                # noqa: BLE001 – bewusst breit: eine kaputte Datei darf den Lauf nicht stoppen
        return [f"Registrierung nicht prüfbar ({type(e).__name__}: {e})"]


def entscheid(beobachtung, einstieg, erkannt_utc, vorige_einstiege, regel, letzter_einstieg, kal):
    """Der eine Entscheid je Auslöser. Gibt (ereignis, grund) zurück. kal: Liste der Handelstage (date), aufsteigend.
    Reihenfolge der Gründe: kein Einstiegstag bekannt, nach dem letzten Einstieg, verspätet, kein Handelstag, Sperrfrist."""
    if einstieg is None:
        return "kein_auftrag", "kein Einstiegstag im Handelskalender"
    e = _tag(einstieg)
    if e > _tag(letzter_einstieg):
        return "kein_auftrag", "nach dem letzten zulässigen Einstieg"
    if not _zeit(erkannt_utc) < datetime.datetime.combine(e, FRIST_UTC):
        return "kein_auftrag", "verspätet erkannt"
    abstand = max(10, int(regel["h"]))
    pos = {t: i for i, t in enumerate(kal)}
    if e not in pos:
        return "kein_auftrag", "Einstiegstag ist kein Handelstag"
    if pos[e] + int(regel["h"]) > len(kal):
        return "kein_auftrag", "Haltefenster liegt nicht ganz im Handelskalender"
    for v in vorige_einstiege:
        pv = pos.get(_tag(v))
        if pv is not None and abs(pos[e] - pv) < abstand:
            return "kein_auftrag", "Sperrfrist (weniger als max(10, h) Handelstage zum vorigen Auftrag)"
    return "auftrag", None


def fortschreiben(alt, gefunden, regel, letzter_einstieg, kal, reihe_bis_vorher, jetzt_utc):
    """Schreibt das Handelsbuch einer Regel fort. alt: bisherige Zeilen dieser Regel; gefunden: {beobachtung: (wert, einstieg)}.
    Jede Beobachtung erhält beim ersten Erkennen genau einen Entscheid. Spätere Abweichungen werden als Revision vermerkt."""
    erst, zuletzt = {}, {}
    for z in alt:
        b = z.get("beobachtung")
        if z["ereignis"] in ("auftrag", "kein_auftrag") and b not in erst:
            erst[b] = z; zuletzt[b] = dict(wert=z.get("wert"), einstieg=z.get("einstieg"), da=True)
        elif z["ereignis"] == "revision" and b in zuletzt:
            zuletzt[b] = dict(wert=z.get("wert", zuletzt[b]["wert"]), einstieg=z.get("einstieg", zuletzt[b]["einstieg"]), da=z.get("grund") != "entfallen")
    auftraege = [z["einstieg"] for z in alt if z["ereignis"] == "auftrag"]
    neu = []
    for b in sorted(gefunden):
        wert, ein = gefunden[b]
        if b not in erst:
            ereignis, grund = entscheid(b, ein, jetzt_utc, auftraege, regel, letzter_einstieg, kal)
            z = dict(ereignis=ereignis, grund=grund, beobachtung=b, wert=wert, einstieg=ein, erkannt_utc=jetzt_utc,
                     nachlieferung=bool(reihe_bis_vorher is not None and b <= reihe_bis_vorher))
            neu.append(z); erst[b] = z; zuletzt[b] = dict(wert=wert, einstieg=ein, da=True)
            if ereignis == "auftrag":
                auftraege.append(ein)
            continue
        l_ = zuletzt[b]
        if not l_["da"]:
            neu.append(dict(ereignis="revision", grund="wieder da", beobachtung=b, wert=wert, einstieg=ein, erkannt_utc=jetzt_utc))
        elif l_["wert"] is None or abs(float(l_["wert"]) - float(wert)) > 1e-9:
            neu.append(dict(ereignis="revision", grund="Wert geändert", beobachtung=b, wert=wert, wert_vorher=l_["wert"], einstieg=ein, erkannt_utc=jetzt_utc))
        elif l_["einstieg"] != ein:
            neu.append(dict(ereignis="revision", grund="Einstiegstag nach heutigem Stand anders", beobachtung=b, wert=wert, einstieg=ein,
                            einstieg_vorher=l_["einstieg"], erkannt_utc=jetzt_utc))
        zuletzt[b] = dict(wert=wert, einstieg=ein, da=True)
    for b in sorted(zuletzt):
        if zuletzt[b]["da"] and b not in gefunden:
            neu.append(dict(ereignis="revision", grund="entfallen", beobachtung=b, erkannt_utc=jetzt_utc))
    return neu


def buche(reg, alt, gefunden, kalender, reihe_bis_vorher, erkannt_utc):
    """Modus «buche» (festgeschriebener Code): neue Zeilen des Handelsbuchs für alle Regeln eines Strangs.
    alt: bisherige Zeilen des Strangs; gefunden: je Regel {gefunden: {beobachtung: [wert, einstieg]} | None, reihe_bis};
    kalender: Handelstage als Text; erkannt_utc: Uhr des Dispatchers NACH der Signalrechnung (G8-01).
    Ein Auftrag ist vollständig: Regel, Ziel, Haltedauer, Kosten, Frist, erwartete Sitzungen und Ausstieg (G8-02)."""
    kal = [_tag(t) for t in kalender]; pos = {t: i for i, t in enumerate(kal)}; out = []
    for i, (r, e) in enumerate(zip(reg["regeln"], gefunden)):
        if e["gefunden"] is None:
            out.append(dict(regel=i, ereignis="ausfall", grund="Indikator heute nicht im Suchraum", erkannt_utc=erkannt_utc)); continue
        a = [z for z in alt if z.get("regel") == i and z["ereignis"] != "ausfall"]
        gef = {b: tuple(v) for b, v in e["gefunden"].items()}
        for z in fortschreiben(a, gef, r, reg["letzter_einstieg"], kal, (reihe_bis_vorher or [None] * len(reg["regeln"]))[i], erkannt_utc):
            z["regel"] = i
            if z["ereignis"] == "auftrag":
                p = pos[_tag(z["einstieg"])]; sitz = [str(t) for t in kal[p:p + int(r["h"])]]
                z.update(indikator=r["indikator"], art=r["art"], ziel=r["ziel"], h=int(r["h"]), kosten_pp=reg["kosten_pp"],
                         frist_utc=f"{z['einstieg']}T{FRIST_UTC.strftime('%H:%M:%S')}Z", sitzungen=sitz, ausstieg=sitz[-1])
            out.append(z)
    return dict(zeilen=out, protokoll=PROTOKOLL)


def gueltig(o):
    """Ein Auftrag gilt nur mit lückenlosem Zeitnachweis vor der Frist: erkannt, gespeichert, veröffentlicht (G8-01)."""
    try:
        frist = _zeit(o["frist_utc"])
        fehlt = [n for n in ("erkannt_utc", "gespeichert_utc", "veroeffentlicht_utc") if not o.get(n)]
        if fehlt:
            return False, "Zeitnachweis fehlt: " + ", ".join(fehlt)
        spaet = [n for n in ("erkannt_utc", "gespeichert_utc", "veroeffentlicht_utc") if not _zeit(o[n]) < frist]
        return (False, "nicht vor der Frist: " + ", ".join(spaet)) if spaet else (True, None)
    except (KeyError, ValueError, TypeError) as e:
        return False, f"Zeitnachweis nicht lesbar ({e})"


# ============================================================================================== Motor (festgeschriebener Code)
def kurse_kuerzen(daten_dir, ziel_dir, stichtag=STICHTAG):
    """Legt eine Kopie des Datenordners an, in der die Kursdateien nur Zeilen bis zum Stichtag enthalten. Der Filter
    vergleicht den Datumstext am Zeilenanfang und liest keine Kurswerte. Alles andere wird verlinkt."""
    os.makedirs(ziel_dir, exist_ok=True)
    for n in os.listdir(daten_dir):
        q, z = os.path.join(daten_dir, n), os.path.join(ziel_dir, n)
        if n != "kurse":
            if not os.path.lexists(z):
                os.symlink(q, z)
            continue
        os.makedirs(z, exist_ok=True)
        for k in os.listdir(q):
            with open(os.path.join(q, k), encoding="utf-8") as fq, open(os.path.join(z, k), "w", encoding="utf-8") as fz:
                kopf = fq.readline(); fz.write(kopf)
                if not kopf.startswith("Date"):
                    continue                               # unbekannte Form: nur die Kopfzeile, also keine Werte
                for zeile in fq:
                    if zeile[:10] <= stichtag:
                        fz.write(zeile)
    return ziel_dir


def motor_laden(signal_bis, code_dir=HIER):
    """Baut die Indikatoren mit dem Code der Suche aus code_dir; Signalreihen bis signal_bis, Kurse am Stichtag abgeschnitten."""
    pfad = os.path.join(code_dir, "suchmaschine.py")
    src = open(pfad, encoding="utf-8").read()
    a = "def bis(x, tag=STICHTAG):"
    b = 'd = bis(pd.read_csv(lade(f"kurse/{t}_d.csv")'
    if src.count(a) != 1 or src.count(b) != 1 or src.count("bis(") != N_BIS_ERWARTET:
        raise SystemExit("ABBRUCH: suchmaschine.py hat sich an den Stellen des Stichtags geändert; vorwaerts.py zuerst prüfen.")
    src = src.replace(a, f'SIGNAL_BIS = pd.Timestamp("{signal_bis}")\n'
                         "def bis_kurs(x):\n    return x[x.index <= STICHTAG]\n\n"
                         "def bis(x, tag=SIGNAL_BIS):")
    src = src.replace(b, 'd = bis_kurs(pd.read_csv(lade(f"kurse/{t}_d.csv")')
    m = types.ModuleType("motor_vorwaerts"); m.__file__ = pfad
    exec(compile(src, pfad, "exec"), m.__dict__)
    spaet = [t for t, d in list(m.kurse.items()) + [("acwi", m.acwi)] if len(d) and d.index.max() > m.STICHTAG]
    if spaet:
        raise SystemExit(f"ABBRUCH: Kurse nach dem Stichtag geladen ({spaet[:3]}); Siegel verletzt.")
    return m


def kalender(m, heute, sonder=(), vorlauf_tage=420):
    """Handelskalender: Kalender der Suche bis zum Stichtag, danach regelbasierte NYSE-Handelstage bis heute + Vorlauf,
    ohne die eingetragenen Sonderschliessungen. Damit stehen Einstieg und Sitzungen eines Auftrags beim Erkennen fest."""
    import pandas as pd
    weg = {_tag(t) for t in sonder}
    nach = [t for t in nyse_handelstage(m.STICHTAG.date() + datetime.timedelta(1), heute + datetime.timedelta(vorlauf_tage)) if t not in weg]
    return m.KAL.append(pd.DatetimeIndex([pd.Timestamp(t) for t in nach]))


def ausloeser(m, kal, regel, nach):
    """Auslöser einer Regel mit Beobachtungstag nach «nach» und vor dem laufenden Tag. ({beobachtung: (wert, einstieg)}, reihe_bis)."""
    import pandas as pd
    ind = regel["indikator"]
    if ind not in m.ind:
        return None, None
    x, fristen = m.ind[ind]
    tage = m.ereignisse(x, regel["art"], ind in m.EREIGNIS)
    tage = tage[(tage > pd.Timestamp(nach)) & (tage < m.SIGNAL_BIS)]
    xs = x.dropna()
    reihe_bis = str(xs.index[-1].date()) if len(xs) else None
    if ind.startswith(UNTERTAEGIG) and len(xs):
        tage = tage[tage < xs.index[-1]]
    out = {}
    if len(tage):
        pos = m.einstieg(kal, tage, fristen)
        for t, p in zip(tage, pos):
            out[str(t.date())] = (float(x.loc[t]), str(kal[p].date()) if 0 <= p < len(kal) else None)
    return out, reihe_bis


def struktur_pruefen(m, regeln):
    """Mängel der Regeln gegenüber dem Suchraum des festgeschriebenen Codes: unbekannter Indikator, Ziel ausserhalb der
    Familie S, 0/1-Reihe mit anderem Extremtyp als «hoch», zwei Regeln auf derselben Grundreihe."""
    struktur = []
    da = [r for r in regeln if r["indikator"] in m.ind]
    struktur += [f"Indikator nicht im Suchraum: {r['indikator']}" for r in regeln if r["indikator"] not in m.ind]
    struktur += [f"Ziel gehört nicht zur Familie S: {r['ziel']}" for r in regeln if r["ziel"] not in m.ZIELE]
    struktur += [f"0/1-Reihe {r['indikator']}: nur Extremtyp «hoch» (wie in der Suche; die anderen Typen ergäben dieselben Ereignisse, G9-01)"
                 for r in da if r["indikator"] in m.EREIGNIS and r["art"] != "hoch"]
    if len({m.quelle_von(r["indikator"]) for r in da}) != len(da):
        struktur.append("je Grundreihe höchstens eine Regel")
    return struktur


def finde(reg, beginn, heute, sonder=()):
    """Modus «finde» (festgeschriebener Code): Auslöser aller Regeln eines Strangs. Erwartet gekürzte Kurse als BASIS."""
    m = motor_laden(str(heute)); kal = kalender(m, heute, sonder)
    struktur = struktur_pruefen(m, reg["regeln"])              # Mängel der Registrierung selbst (G9-07); der Dispatcher weist damit vor «aktiv» ab
    out = []
    for r in reg["regeln"]:
        g, rb = ausloeser(m, kal, r, beginn)
        out.append(dict(gefunden=g, reihe_bis=rb))
    import pandas as pd
    return dict(regeln=out, struktur=struktur, kalender=[str(t.date()) for t in kal[kal >= pd.Timestamp(beginn)]], protokoll=PROTOKOLL)


def sitzungen_gueltig(o, sonder):
    """Sitzungen eines Auftrags. Ohne Sonderschliessung im Fenster gelten die im Auftrag festgehaltenen. Liegt eine
    eingetragene Sonderschliessung darin, rücken die Sitzungen nach dem regelbasierten Kalender nach (dokumentierte Regel)."""
    sitz = list(o.get("sitzungen") or [])
    weg = {str(_tag(t)) for t in sonder}
    if not sitz or not (weg & set(sitz)):
        return sitz
    e = _tag(o["einstieg"])
    neu = [str(t) for t in nyse_handelstage(e, e + datetime.timedelta(2 * int(o["h"]) + 40)) if str(t) not in weg]
    return neu[:int(o["h"])]


def werte(reg, beginn, auftraege, daten_dir, sonder=()):
    """Netto-Mehrertrag je Auftrag. Liest nur Kurszeilen im Fenster (Beginn, Schlusstag]; die Aufbereitung entscheidet
    allein aus diesem Fenster. Die Kurse werden auf die Sitzungen des Auftrags ausgerichtet: Fehlt eine Zeile im Ziel
    ODER im Vergleichsindex, oder fehlt eine Datei, ist der Auftrag «nicht auswertbar»; nichts wird verschoben (G8-02)."""
    import io
    import pandas as pd
    lo, hi = str(beginn), str(_tag(reg["schlusstag"]))

    def kurs(t):
        p = os.path.join(daten_dir, "kurse", f"{t}_d.csv")
        if not os.path.exists(p):
            return None
        zeilen = []
        with open(p, encoding="utf-8") as f:
            kopf = f.readline()
            for z in f:
                if lo < z[:10] <= hi:
                    zeilen.append(z)
        try:
            k = pd.read_csv(io.StringIO(kopf + "".join(zeilen)), parse_dates=["Date"]).drop_duplicates("Date").set_index("Date").sort_index()
            if "AdjClose" in k and len(k) and k.AdjClose.notna().mean() > 0.99:
                roh_o, roh_c, adj = k.Open.astype(float), k.Close.astype(float), k.AdjClose.astype(float)
                fa = (adj / roh_c).where((roh_c > 0) & (adj > 0))                  # ungültiger Anpassungsfaktor: Zeile gilt als fehlend (G9-06)
                k = pd.DataFrame({"Open": roh_o * fa, "Close": adj.where(fa.notna())}).astype(float)
            else:
                k = k[["Open", "Close"]].astype(float)
        except (ValueError, KeyError, AttributeError):
            return None
        return {str(t.date()): (float(o), float(c)) for t, o, c in zip(k.index, k.Open, k.Close)}
    cache, out = {}, []

    def hole(t):
        if t not in cache:
            cache[t] = kurs(t)
        return cache[t]
    for o in auftraege:
        z, h, e = o["ziel"], int(o["h"]), o["einstieg"]
        r = dict(strang=o.get("strang"), regel=o["regel"], beobachtung=o["beobachtung"], einstieg=e, h=h, ziel=z)
        sitz = sitzungen_gueltig(o, sonder)

        def raus(grund):
            out.append(dict(r, status="nicht auswertbar", grund=grund))
        if len(sitz) != h or sitz[0] != e:
            raus("Sitzungen des Auftrags fehlen oder passen nicht zu Einstieg und Haltedauer"); continue
        if sitz[-1] > hi:
            raus("Haltefenster reicht über den Schlusstag"); continue
        kz, ka = hole(z), hole("acwi")
        if kz is None or ka is None:
            raus("Kursdatei fehlt oder ist nicht lesbar: " + ", ".join(n for n, k in ((z, kz), ("acwi", ka)) if k is None)); continue
        gut = lambda x: math.isfinite(x) and x > 0                      # noqa: E731 – Preise müssen endlich und positiv sein (G9-06)
        fehlt = [f"{n} {t}" for t in sitz for n, k in ((z, kz), ("acwi", ka)) if t not in k or not gut(k[t][1])]
        fehlt += [f"{n} {e} (Eröffnung)" for n, k in ((z, kz), ("acwi", ka)) if e in k and not gut(k[e][0])]
        if fehlt:
            raus("Kurs im Haltefenster fehlt oder ist ungültig: " + "; ".join(fehlt[:6])); continue
        brutto = 100.0 * (kz[sitz[-1]][1] / kz[e][0] - ka[sitz[-1]][1] / ka[e][0])
        if not math.isfinite(brutto):
            raus("Ertrag nicht endlich"); continue
        out.append(dict(r, status="ausgewertet", ausstieg=sitz[-1], brutto_pp=float(brutto), netto_pp=float(brutto - float(reg["kosten_pp"]))))
    return out


def bedarf(auftraege, sonder=()):
    """Modus «bedarf» (festgeschriebener Code): je Kursdatei der letzte Tag, den die Auswertung braucht (nach Sonderschliessungen)."""
    out = {}
    for o in auftraege:
        sitz = sitzungen_gueltig(o, sonder)
        if sitz:
            for n in (o["ziel"], "acwi"):
                out[n] = max(out.get(n, ""), sitz[-1])
    return dict(bedarf=out, protokoll=PROTOKOLL)


def schliesse(reg, beginn, auftraege, daten_dir, sonder=()):
    """Modus «schliesse» (festgeschriebener Code): Gültigkeit der Aufträge, Erträge und Aggregation des Papierergebnisses."""
    ok, verfallen = [], []
    for o in auftraege:
        g, grund = gueltig(o)
        if g:
            ok.append(o)
        else:
            verfallen.append(dict(regel=o["regel"], beobachtung=o["beobachtung"], einstieg=o["einstieg"], ziel=o["ziel"], h=o["h"], grund=grund))
    a = werte(reg, beginn, ok, daten_dir, sonder)
    gut = [x for x in a if x["status"] == "ausgewertet"]; offen = [x for x in a if x["status"] != "ausgewertet"]
    jahre = max((_tag(reg["schlusstag"]) - _tag(beginn)).days / 365.25, 1e-9)
    je_regel = [sum(x["netto_pp"] for x in gut if x["regel"] == i) for i in range(len(reg["regeln"]))]
    return dict(protokoll=PROTOKOLL, auftraege_n=len(auftraege), verfallen_n=len(verfallen), verfallen=verfallen, gueltig_n=len(ok),
                auswertbar_n=len(gut), nicht_auswertbar=offen, vollstaendig=not offen,
                genug_ereignisse=len({x["einstieg"] for x in gut}) >= int(reg["min_ereignisse"]),
                mittel_netto_pp_je_auftrag=float(np.mean([x["netto_pp"] for x in gut])) if gut else None,
                jahresertrag_netto_pp=float(np.mean(je_regel) / jahre) if not offen else None,
                hinweis_unvollstaendig=None if not offen else "Mindestens ein Auftrag ist nicht auswertbar; kein Jahresertrag, bis die Lücke geklärt ist.",
                einzeln=a)


# ============================================================================================== Umgebung (Git, Prozesse, Uhr)
def _git(*a, cwd=HIER, code=False, roh=False):
    r = subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=not roh)
    if code:
        return r.returncode
    if r.returncode != 0:
        return None
    return r.stdout if roh else r.stdout.strip()


def _iso_utc(t):
    return datetime.datetime.fromisoformat(t).astimezone(datetime.timezone.utc).replace(tzinfo=None)


def datei_sha(p):
    if not os.path.exists(p):
        return None
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _git_ort(pfad):
    """(Wurzel des Arbeitsbaums, Pfad relativ dazu) für eine Datei oder einen Ordner, der noch nicht existieren muss."""
    pfad = os.path.abspath(pfad); a = pfad
    while not os.path.isdir(a):
        a = os.path.dirname(a)
    oben = _git("rev-parse", "--show-toplevel", cwd=a)
    return (os.path.realpath(oben), os.path.relpath(os.path.realpath(pfad), os.path.realpath(oben))) if oben else (None, None)


class Umgebung:
    """Alle Zugriffe auf Uhr, Git, Prozesse und Kursdateien. Tests ersetzen einzelne davon; die Produktion nutzt diese."""
    def __init__(self, daten_dir=None, arbeit=None, repo=HIER):
        self.repo = os.path.realpath(repo)
        self.daten_dir = daten_dir or os.path.join(repo, "data")
        self.arbeit = arbeit or tempfile.mkdtemp(prefix="vorwaerts_")

    def uhr(self):
        return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)

    def _rel(self, pfad):
        return os.path.relpath(os.path.realpath(pfad), self.repo)

    def aufnahme(self, pfad):
        """(Commit, Zeit UTC) des jüngsten Commits der Hauptlinie, mit dem die Datei hinzukam (G8-09). Ohne Verfolgung von
        Umbenennungen; ein Zusammenführungs-Commit zählt als Aufnahme, nicht der ältere Commit des Seitenzweigs."""
        t = _git("log", "--first-parent", "--diff-merges=first-parent", "-s", "--diff-filter=A", "--format=%H%x09%cI", "--", self._rel(pfad), cwd=self.repo)
        if not t:
            return None
        c, z = t.split("\n")[0].split("\t")
        return c, _iso_utc(z)

    def geaendert_seit(self, pfad, commit):
        """Commits der Hauptlinie nach «commit», die die Datei berühren (G8-07 D). None: nicht feststellbar."""
        if not _hex40(commit) or _git("merge-base", "--is-ancestor", commit, "HEAD", cwd=self.repo, code=True) != 0:
            return None
        t = _git("log", "--first-parent", "--diff-merges=first-parent", "-s", "--format=%H", f"{commit}..HEAD", "--", self._rel(pfad), cwd=self.repo)
        return None if t is None else [x for x in t.split("\n") if _hex40(x)]

    def marker_historie(self, ordner):
        """Alle Fassungen des Öffnungsmarkers in der Hauptlinie, älteste zuerst: [(Commit, Text)]. So geht keine Öffnung
        verloren, die zwischen zwei Läufen hinzukam und wieder verschwand (G9-01 A). None: nicht feststellbar."""
        rel = self._rel(os.path.join(ordner, OEFFNUNG))
        t = _git("log", "--first-parent", "--diff-merges=first-parent", "-s", "--diff-filter=AM", "--reverse", "--format=%H", "--", rel, cwd=self.repo)
        if t is None:
            return None
        out = []
        for c in [x for x in t.split("\n") if _hex40(x)]:
            text = _git("show", f"{c}:{rel}", cwd=self.repo, roh=True)
            out.append((c, text.decode("utf-8", "replace") if text is not None else ""))
        return out

    def journal_bekannt(self, pfad):
        """Kennt die Historie des Zweigs diese Journaldatei? True/False; None, wenn kein Git-Arbeitsbaum (G9-02)."""
        oben, rel = _git_ort(pfad)
        if not oben:
            return None
        return bool(_git("log", "-1", "--format=%H", "--", rel, cwd=oben))

    def veroeffentlicht_stand(self, logdir):
        """True, wenn der Journalordner beim Start unverändert dem ausgecheckten (also veröffentlichten) Stand entspricht."""
        if not os.path.isdir(logdir):
            return False
        oben, rel = _git_ort(logdir)
        return bool(oben) and _git("status", "--porcelain", "--", rel, cwd=oben) == ""

    def ist_vorfahr(self, a, b):
        return _hex40(a) and _hex40(b) and _git("merge-base", "--is-ancestor", a, b, cwd=self.repo, code=True) == 0

    def code_dir(self, commit):
        """Eigener Arbeitsbaum genau dieses Commits (G8-03). Nur vollständige Kennungen; nie der laufende Arbeitsordner."""
        if not _hex40(commit):
            return None
        if _git("cat-file", "-e", commit + "^{commit}", cwd=self.repo, code=True) != 0:
            _git("fetch", "-q", "origin", commit, cwd=self.repo)
            if _git("cat-file", "-e", commit + "^{commit}", cwd=self.repo, code=True) != 0:
                return None
        ziel = os.path.join(self.arbeit, "code_" + commit)
        if not os.path.isdir(ziel) and _git("worktree", "add", "-q", "--detach", ziel, commit, cwd=self.repo) is None:
            return None
        if _git("rev-parse", "HEAD", cwd=ziel) != commit or _git("status", "--porcelain", "--untracked-files=no", cwd=ziel) != "":
            return None
        return ziel if os.path.exists(os.path.join(ziel, "vorwaerts.py")) else None

    def gekuerzt(self):
        z = os.path.join(self.arbeit, "basis")
        if not os.path.isdir(z):
            kurse_kuerzen(self.daten_dir, z)
        return z

    def prozess_umgebung(self):
        """Umgebung für den festgeschriebenen Code: keine PS_-Variablen ausser den Datenbasen (G9-04). Damit können
        PS_PAARE, PS_MECHANISMEN und ähnliche Schalter keine Datei ausserhalb des registrierten Arbeitsbaums bestimmen."""
        return {k: w for k, w in os.environ.items() if not k.startswith("PS_") or k in UMGEBUNG_ERLAUBT}

    def rufe(self, code_dir, modus, eingabe):
        """Ruft vorwaerts.py aus code_dir in einem eigenen Prozess; gibt das Ergebnis oder {fehler} zurück."""
        ein = os.path.join(self.arbeit, f"ein_{modus}.json"); aus = os.path.join(self.arbeit, f"aus_{modus}.json")
        with open(ein, "w", encoding="utf-8") as f:
            json.dump(eingabe, f, ensure_ascii=False)
        if os.path.exists(aus):
            os.remove(aus)
        basis = self.gekuerzt() if modus == "finde" else self.daten_dir
        env = dict(self.prozess_umgebung(), PS_VORWAERTS_MODUS=modus, PS_VORWAERTS_EIN=ein, PS_VORWAERTS_AUS=aus,
                   PS_CACHE=os.path.join(self.arbeit, "cache_" + modus))
        r = subprocess.run([sys.executable, os.path.join(code_dir, "vorwaerts.py"), "file://" + basis], env=env,
                           capture_output=True, text=True, cwd=self.arbeit)
        if r.returncode != 0 or not os.path.exists(aus):
            return dict(fehler=f"festgeschriebener Code ({modus}) fehlgeschlagen: {(r.stderr or r.stdout)[-300:]}")
        try:
            e = json.load(open(aus, encoding="utf-8"))
        except ValueError:
            return dict(fehler=f"festgeschriebener Code ({modus}): Ausgabe nicht lesbar")
        if not isinstance(e, dict) or (not e.get("fehler") and e.get("protokoll") != PROTOKOLL):
            return dict(fehler=f"festgeschriebener Code ({modus}): andere Schnittstelle als Protokoll {PROTOKOLL}")
        return e

    def daten_pruefen(self, ds):
        """Stimmen die Kursdateien mit dem genannten main-Commit überein? Liste von Fehlern (G8-05)."""
        d = os.path.join(self.daten_dir, "kurse")
        oben = _git("rev-parse", "--show-toplevel", cwd=self.daten_dir) if os.path.isdir(self.daten_dir) else None
        if not oben:
            return ["Kursordner liegt nicht in einem Git-Arbeitsbaum; Datenstand nicht belegbar"]
        f = []
        if _git("rev-parse", "HEAD", cwd=oben) != ds["main"]:
            f.append("ausgecheckter Commit der Kurse ist nicht der genannte Datenstand main")
        if _git("status", "--porcelain", "--", d, cwd=oben) != "":
            f.append("Kursdateien weichen vom ausgecheckten Commit ab")
        return f

    def manifest(self, namen):
        return {n: datei_sha(os.path.join(self.daten_dir, "kurse", f"{n}_d.csv")) for n in sorted(set(namen))}

    def kurse_bis(self, name="acwi"):
        """Letztes Datum einer Kursdatei (nur der Datumstext wird gelesen); None, wenn die Datei fehlt."""
        p = os.path.join(self.daten_dir, "kurse", f"{name}_d.csv"); m = None
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                f.readline()
                for z in f:
                    if len(z) >= 10 and z[:4].isdigit() and (m is None or z[:10] > m):
                        m = z[:10]
        return m

    def versionen(self):
        from importlib import metadata
        out = dict(python=sys.version.split()[0])
        for p in ("numpy", "pandas"):
            try:
                out[p] = metadata.version(p)
            except metadata.PackageNotFoundError:
                out[p] = None
        return out


def umgebung_gleich(a, b):
    """Gleiche Rechenumgebung: numpy und pandas genau, Python bis zur zweiten Stelle (G9-04)."""
    a, b = a or {}, b or {}
    kurz = lambda x: ".".join(str(x.get("python") or "").split(".")[:2])     # noqa: E731
    return a.get("numpy") == b.get("numpy") and a.get("pandas") == b.get("pandas") and kurz(a) == kurz(b)


# ============================================================================================== Dateien und Journale
def registrierungen(ordner):
    """(Dateiname, SHA-256 der Bytes, Inhalt). Unlesbare Dateien kommen als Inhalt None zurück."""
    out = []
    if os.path.isdir(ordner):
        for n in sorted(os.listdir(ordner)):
            if n.endswith(".json") and n not in STEUERDATEIEN:
                roh = open(os.path.join(ordner, n), "rb").read(); h = hashlib.sha256(roh).hexdigest()
                try:
                    out.append((n, h, json.loads(roh.decode("utf-8"))))
                except ValueError:
                    out.append((n, h, None))
    return out


def steuerdatei(ordner, name):
    p = os.path.join(ordner, name)
    return open(p, encoding="utf-8", errors="replace").read() if os.path.exists(p) else None


def freigabemodus(ordner):
    """Modus aus vorwaerts/freigabe.json: {modus, freigabe (Wortlaut), seit}. Fehlt die Datei oder ist sie unklar: gesperrt.
    «uebung» lässt nur Übungsstränge zu; echte Stränge bleiben gesperrt (G8-11)."""
    try:
        d = json.loads(steuerdatei(ordner, FREIGABE) or "null")
        return d["modus"] if isinstance(d, dict) and d.get("modus") in MODI and _text(d.get("freigabe")) else "gesperrt"
    except (ValueError, TypeError):
        return "gesperrt"


def sonderschliessungen(ordner):
    t = steuerdatei(ordner, SONDER)
    if t is None:
        return []
    try:
        d = json.loads(t)
        tage = d["tage"]
        if not isinstance(tage, list) or not all(isinstance(x, dict) and _text(x.get("quelle")) and _text(x.get("freigabe")) for x in tage):
            raise ValueError("je Eintrag tag, quelle, freigabe")
        return sorted({str(_tag(x["tag"])) for x in tage})
    except (ValueError, KeyError, TypeError) as e:
        raise Abbruch(f"{SONDER} ist ungültig ({e}); das Register rechnet nicht weiter, bis die Datei berichtigt ist.")


def dispatcher_freigaben(ordner):
    try:
        d = json.loads(steuerdatei(ordner, DISPATCHER) or "null")
        return {x["sha256"] for x in d["freigaben"] if isinstance(x, dict) and _text(x.get("freigabe")) and isinstance(x.get("sha256"), str)} if isinstance(d, dict) else set()
    except (ValueError, KeyError, TypeError):
        return set()


def journal_lesen(p):
    """Liest ein Journal (eine JSON-Zeile je Eintrag). Gibt (Einträge, Auskunft) zurück. Auskunft: da (Datei vorhanden),
    zeilen (vollständige physische Zeilen), nummern (physische Zeile je Eintrag), abgerissen (Bytes ohne Zeilenende am
    Schluss). Journale werden nie gekürzt: Eine unlesbare Zeile gilt nur, wenn ein späterer Eintrag «ungueltig» sie
    ausdrücklich nennt (siehe journal_abschliessen); sonst ist das Journal beschädigt und der Lauf bricht ab (G9-02)."""
    if not os.path.exists(p):
        return [], dict(da=False, zeilen=0, nummern=[], abgerissen=0)
    roh = open(p, "rb").read(); ende = roh.rfind(b"\n") + 1
    teile = roh[:ende].split(b"\n")[:-1] if ende else []
    gelesen, nichtig = [], set()
    for z in teile:
        try:
            e = json.loads(z.decode("utf-8")) if z.strip() else None
        except ValueError:
            e = ValueError
        gelesen.append(e)
        if isinstance(e, dict) and e.get("ereignis") == "ungueltig":
            nichtig.add(e.get("zeile"))
    out, nummern = [], []
    for i, e in enumerate(gelesen):
        if e is None or i in nichtig or (isinstance(e, dict) and e.get("ereignis") == "ungueltig"):
            continue
        if not isinstance(e, dict):
            raise Abbruch(f"Journal {os.path.basename(p)} ist in Zeile {i + 1} beschädigt; kein Lauf, bis das geklärt ist.")
        out.append(e); nummern.append(i)
    return out, dict(da=True, zeilen=len(teile), nummern=nummern, abgerissen=len(roh) - ende)


def journal_abschliessen(p, auskunft):
    """Schliesst ein abgerissenes Ende (Schreibabbruch) ab, ohne etwas zu löschen: Zeilenende anfügen und die Zeile als
    ungültig vermerken. Gibt True zurück, wenn etwas zu tun war."""
    if not auskunft["abgerissen"]:
        return False
    text = "\n" + json.dumps(dict(ereignis="ungueltig", zeile=auskunft["zeilen"], grund="abgerissenes Ende nach Schreibabbruch"), ensure_ascii=False) + "\n"
    with open(p, "ab") as f:
        f.write(text.encode("utf-8")); f.flush(); os.fsync(f.fileno())
    return True


def praefix_sha(p, zeilen):
    """SHA-256 der ersten «zeilen» physischen Zeilen; None, wenn die Datei kürzer ist oder fehlt."""
    if not os.path.exists(p):
        return None if zeilen else hashlib.sha256(b"").hexdigest()
    roh = open(p, "rb").read(); pos = 0
    for _ in range(zeilen):
        pos = roh.find(b"\n", pos) + 1
        if pos == 0:
            return None
    return hashlib.sha256(roh[:pos]).hexdigest()


def anhaengen(p, zeilen):
    """Hängt Zeilen dauerhaft an (ein Schreibvorgang, danach auf die Platte)."""
    if zeilen:
        text = "".join(json.dumps(z, ensure_ascii=False, allow_nan=False) + "\n" for z in zeilen)
        with open(p, "ab") as f:
            f.write(text.encode("utf-8")); f.flush(); os.fsync(f.fileno())


def schreibe_einmal(p, obj):
    """Schreibt eine Datei vollständig in eine Hilfsdatei und veröffentlicht sie unteilbar und genau einmal.
    Gibt False zurück, wenn es die Datei schon gibt (dann gilt die vorhandene)."""
    tmp = f"{p}.teil.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, allow_nan=False); f.flush(); os.fsync(f.fileno())
    try:
        os.link(tmp, p)
        return True
    except FileExistsError:
        return False
    finally:
        os.remove(tmp)


def schreibe_ansicht(p, obj):
    tmp = f"{p}.teil.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, p)


def zustand(journal):
    """Baut den Stand aus dem Statusjournal auf (G8-07). Endzustände werden nie verlassen."""
    st = dict(straenge={}, oeffnungen={}, dispatcher=None, marker_commits=[])
    for z in journal:
        e = z.get("ereignis", "status")
        if e == "status":
            alt = st["straenge"].get(z["strang"], {})
            if alt.get("status") in ENDGUELTIG:
                continue
            st["straenge"][z["strang"]] = dict(alt, **(z.get("daten") or {}), status=z["nach"], grund=z["grund"], seit_utc=z["zeit_utc"])
        elif e in ("oeffnung", "oeffnung_unlesbar"):
            for r in z.get("regeln", []):
                st["oeffnungen"].setdefault(r, z["zeit_utc"])
            if z.get("commit"):
                st["marker_commits"].append(z["commit"])
        elif e == "dispatcher":
            st["dispatcher"] = z["sha256"]
    return st


def zaehler(st):
    """Getrennte Zahlen: echte Stränge, belegte Plätze (aktiv oder reserviert), Übungen, Endzustände."""
    s = list(st["straenge"].values())
    echt = [x for x in s if x.get("art") != "uebung" and x["status"] != "abgewiesen"]
    return dict(echte_straenge_je=len(echt), aktiv=sum(x["status"] == "aktiv" for x in echt), reserviert=sum(x["status"] == "reserviert" for x in echt),
                plaetze_belegt=sum(x["status"] in OFFEN for x in echt), uebungen=sum(x.get("art") == "uebung" for x in s),
                abgewiesen=sum(x["status"] == "abgewiesen" for x in s), gestoppt=sum(x["status"] == "gestoppt" for x in s),
                beendet_ohne_urteil=sum(x["status"] == "beendet_ohne_urteil" for x in s), ausgewertet=sum(x["status"] == "ausgewertet" for x in echt))


def vermerken(logdir, gepusht_utc, kopf=None, art="push"):
    """Vermerk einer Veröffentlichung: Zeit NACH gelungenem Push und Länge der Journale zu diesem Zeitpunkt (G9-03).
    Daraus folgt je Zeile des Handelsbuchs, wann sie spätestens auf GitHub lag."""
    z = {n: journal_lesen(os.path.join(logdir, f"{n}.jsonl"))[1]["zeilen"] for n in ("handelsbuch", "status")}
    anhaengen(os.path.join(logdir, VERMERK), [dict(gepusht_utc=gepusht_utc, zeilen=z, kopf=kopf, art=art)])


def veroeffentlicht_utc(vermerke, nummer):
    """Früheste vermerkte Veröffentlichung, die die physische Zeile «nummer» des Handelsbuchs schon enthielt; sonst None."""
    t = [v["gepusht_utc"] for v in vermerke if isinstance(v.get("zeilen"), dict) and v["zeilen"].get("handelsbuch", 0) > nummer]
    return min(t) if t else None


# ============================================================================================== Dispatcher
def lauf(ordner, logdir, datenstand="", umgebung=None, nur_schluss=None):
    """Ein Lauf. Reihenfolge: Journale lesen und gegen das letzte Laufprotokoll prüfen, Öffnungen sichern (auch im
    leeren und gesperrten Register), Dispatcher-Freigabe, Abgleich, Registrierungen (Stopp bei Änderung, Aufnahme neuer),
    dann je Strang: fällige Schlussauswertung oder Handelsbuch fortschreiben.
    nur_schluss=<Kennung>: nur die Schutzprüfungen und die Schlussauswertung dieses Strangs (löst Abbruch aus, wenn sie
    nicht möglich ist). Gibt die Zusammenfassung zurück."""
    u = umgebung or Umgebung()
    start = u.uhr(); jz = _fmt(start); heute = start.date()
    regs = registrierungen(ordner); modus = freigabemodus(ordner)
    pfade = {n: os.path.join(logdir, d) for n, d in (("status", "status.jsonl"), ("handelsbuch", "handelsbuch.jsonl"), ("laeufe", "laeufe.jsonl"), ("veroeffentlicht", VERMERK))}
    p_status, p_buch, p_laeufe, p_stand = pfade["status"], pfade["handelsbuch"], pfade["laeufe"], os.path.join(logdir, "stand.json")
    kopf_zus = dict(zeit_utc=jz, heute=str(heute), modus=modus, registrierungen=len(regs))
    gelesen = {n: journal_lesen(p) for n, p in pfade.items()}
    # Vollständigkeit (G9-02): Ein fehlendes oder geleertes Journal mit bekannter Vorgeschichte ist kein leerer Anfang
    for n, p in pfade.items():
        if not gelesen[n][1]["da"] and u.journal_bekannt(p):
            raise Abbruch(f"Journal {os.path.basename(p)} fehlt, obwohl die Historie des Zweigs es kennt; kein Neubeginn (G9-02).")
    journal = gelesen["status"][0]
    andere = os.path.isdir(logdir) and any(n.startswith("schluss_") for n in os.listdir(logdir))
    if not journal and (gelesen["handelsbuch"][0] or gelesen["laeufe"][0] or andere):
        raise Abbruch("Statusjournal fehlt oder ist leer, obwohl Handelsbuch, Laufprotokoll oder Schlussdateien vorhanden sind; kein Neubeginn (G9-02).")
    siegel = next((z["siegel"] for z in reversed(gelesen["laeufe"][0]) if z.get("siegel")), {})
    for n, (zeilen, h) in siegel.items():
        if praefix_sha(pfade[n], zeilen) != h:
            raise Abbruch(f"Journal {n} stimmt nicht mehr mit dem letzten Laufprotokoll überein (verloren, gekürzt oder verändert); kein Lauf (G9-02).")
    t_oe = steuerdatei(ordner, OEFFNUNG); historie = u.marker_historie(ordner)
    if not journal and t_oe is None and not historie and (modus == "gesperrt" or not regs):
        return dict(kopf_zus, aktiv=[], neue_zeilen=0, statuswechsel=[], regeln=[], zaehler=zaehler(zustand([])),
                    fehler=[dict(kennung=n[:-5], fehler=["Register gesperrt (V3.15 E32i): keine Registrierung, bis die Sperre aufgehoben ist"]) for n, _, _ in regs])
    os.makedirs(logdir, exist_ok=True)
    repariert = [n for n, p in pfade.items() if journal_abschliessen(p, gelesen[n][1])]
    if repariert:
        gelesen = {n: journal_lesen(p) for n, p in pfade.items()}; journal = gelesen["status"][0]
    buch, buch_nr = gelesen["handelsbuch"][0], list(gelesen["handelsbuch"][1]["nummern"]); buch_zeilen = gelesen["handelsbuch"][1]["zeilen"]
    laeufe = gelesen["laeufe"][0]
    st = zustand(journal); status_neu, fehler, bericht, neue_zeilen = [], [], [], 0

    def notiere(z):
        anhaengen(p_status, [z]); journal.append(z); st.update(zustand(journal))

    def setze(k, status, grund, **daten):
        von = st["straenge"].get(k, {}).get("status", "frei")
        z = dict(ereignis="status", strang=k, von=von, nach=status, grund=grund, zeit_utc=jz, daten=daten)
        notiere(z); status_neu.append({x: z[x] for x in ("strang", "von", "nach", "grund", "zeit_utc")})
    for n in repariert:
        notiere(dict(ereignis="reparatur", datei=os.path.basename(pfade[n]), grund="abgerissenes Ende nach Schreibabbruch als ungültig vermerkt (nichts gelöscht)", zeit_utc=jz))
    # Öffnungen (E32f, G8-08, G9-01 A): dauerhaftes Ereignis, in jedem Anfangszustand und aus der ganzen Historie von main
    if historie is None:
        fehler.append(dict(kennung="-", fehler=["Historie des Öffnungsmarkers nicht prüfbar; es gilt nur die heutige Datei"]))
    for c, text in historie or []:
        if c in st["marker_commits"]:
            continue
        try:
            neu_oe = [r for r in marker_lesen(text) if r not in st["oeffnungen"]]
            notiere(dict(ereignis="oeffnung", regeln=neu_oe, commit=c, zeit_utc=jz))
        except Abbruch as e:
            notiere(dict(ereignis="oeffnung_unlesbar", commit=c, grund=str(e), zeit_utc=jz))
    if t_oe is not None:
        neu_oe = [r for r in marker_lesen(t_oe) if r not in st["oeffnungen"]]             # ungültige heutige Datei: Abbruch, blockiert alles
        if neu_oe:
            notiere(dict(ereignis="oeffnung", regeln=neu_oe, zeit_utc=jz))
    offen = lambda: {k: s for k, s in st["straenge"].items() if s["status"] in OFFEN}    # noqa: E731
    for k, s in list(offen().items()):
        if set(s.get("regeln", [])) & set(st["oeffnungen"]):
            setze(k, "beendet_ohne_urteil", "Bestätigung geöffnet; Strang teilt eine Regel mit dem Finalisten (E32f)")
    ds = stand_lesen(datenstand)
    if ds is None and (offen() or (modus != "gesperrt" and regs)):
        raise Abbruch("Datenstand fehlt oder ist unvollständig (main, neu, energie mit vollständigen Commit-Kennungen).")
    # Dispatcher-Freigabe (G8-04): kein stiller Wechsel der Schutzregeln, solange ein Strang läuft
    sha_d = datei_sha(os.path.abspath(__file__))
    if st["dispatcher"] != sha_d:
        if st["dispatcher"] is not None and offen() and sha_d not in dispatcher_freigaben(ordner):
            raise Abbruch(f"Der Dispatcher hat sich geändert ({sha_d[:16]}), während Stränge laufen, und steht nicht in {DISPATCHER}; kein Lauf ohne freigegebene Migration.")
        notiere(dict(ereignis="dispatcher", sha256=sha_d, vorher=st["dispatcher"], zeit_utc=jz))
    sonder = sonderschliessungen(ordner)
    # Nachtrag zum Zeitnachweis: Zeilen, die beim Start schon im veröffentlichten Stand liegen, aber keinen Vermerk haben
    vermerkt = max([v["zeilen"].get("handelsbuch", 0) for v in gelesen["veroeffentlicht"][0] if isinstance(v.get("zeilen"), dict)] or [0])
    if buch_zeilen > vermerkt and u.veroeffentlicht_stand(logdir):
        vermerken(logdir, jz, art="nachtrag: beim Start im veröffentlichten Stand gesehen (Vermerk nach dem Push fehlte)")
    # Abgleich nach Schreibabbruch (G8-06): Dateien der Schlussauswertung sind massgebend für den Status
    for k, s in list(offen().items()):
        if os.path.exists(os.path.join(logdir, f"schluss_{k}.json")):
            setze(k, "ausgewertet", "Schlussauswertung gespeichert (Abgleich nach Abbruch)")
        elif s["status"] == "aktiv" and os.path.exists(os.path.join(logdir, f"schluss_{k}.reserviert.json")):
            setze(k, "reserviert", "Schlussauswertung reserviert (Abgleich nach Abbruch)")
    # Registrierungen
    gesehen, ruht, inhalt, erst_finde = set(), set(), {}, {}
    for name, h, d in regs:
        k = name[:-5]; gesehen.add(k); s = st["straenge"].get(k); pfad = os.path.join(ordner, name); inhalt[k] = d
        if s is not None:
            if s["status"] in OFFEN:
                if s["sha256"] != h:
                    setze(k, "gestoppt", "Registrierung nachträglich verändert (endgültig, auch wenn die alte Datei zurückkehrt)"); continue
                g = u.geaendert_seit(pfad, s["aufnahme_commit"])
                if g is None:
                    ruht.add(k); fehler.append(dict(kennung=k, fehler=["Historie der Registrierung auf main nicht prüfbar; der Strang ruht in diesem Lauf"]))
                elif g:
                    setze(k, "gestoppt", f"Registrierung in der Historie von main verändert (Commit {g[0][:12]}); endgültig")
            continue                                             # endgültige Zustände bleiben; nichts wird wiederbelebt
        art = d.get("art") if isinstance(d, dict) else None
        if modus == "gesperrt" or (modus == "uebung" and art != "uebung"):
            fehler.append(dict(kennung=k, fehler=["Register gesperrt (V3.15 E32i)" if modus == "gesperrt" else "nur Übungsstränge freigegeben; echte Stränge bleiben gesperrt"]))
            continue                                             # nicht aufgenommen und nicht abgewiesen: bei späterer Freigabe zählt das erste Sehen dann
        f, auf, cd, erg = [], None, None, None
        if not isinstance(d, dict):
            f.append("Datei nicht lesbar oder kein JSON-Objekt")
        elif d.get("kennung") != k or not _kennung_ok(k):
            f.append("Dateiname muss <kennung>.json sein (Buchstaben, Ziffern, _ und -)")
        if not f:
            auf = u.aufnahme(pfad)
            if auf is None:
                f.append("Aufnahme der Registrierung auf main nicht feststellbar")
            elif not (0 <= (heute - auf[1].date()).days <= RUECKDATIERUNG_TAGE) or auf[1] > start + datetime.timedelta(minutes=10):
                f.append(f"Commit der Aufnahme ({auf[1].date()}) liegt nicht höchstens {RUECKDATIERUNG_TAGE} Tage vor dem ersten Sehen ({heute})")
        if not f:
            if not _hex40(d.get("code_commit")):
                f.append("code_commit: vollständige Commit-Kennung (40 Zeichen, klein), kein Zweigname und kein Kürzel")
            elif not u.ist_vorfahr(d["code_commit"], auf[0]):
                f.append("code_commit lag bei der Aufnahme der Registrierung nicht auf main")
            else:
                cd = u.code_dir(d["code_commit"])
                if cd is None:
                    f.append("code_commit nicht auffindbar, nicht sauber oder ohne vorwaerts.py")
        if not f:
            e = u.rufe(cd, "pruefe", dict(reg=d, beginn=str(heute)))
            f = [e["fehler"]] if e.get("fehler") else list(e.get("fehler_liste") or [])
        if not f:
            regeln = [regel_schluessel(r) for r in d["regeln"]]
            if set(regeln) & set(st["oeffnungen"]):
                f.append("Bestätigung geöffnet; eine Regel dieses Strangs gehört zum Finalisten (E32f)")
            vor = sorted(k2 for k2, s2 in st["straenge"].items() if s2["status"] != "abgewiesen" and set(s2.get("regeln", [])) & set(regeln))
            if any(st["straenge"][k2]["status"] in OFFEN for k2 in vor):
                f.append(f"dieselbe Regel läuft schon in {[k2 for k2 in vor if st['straenge'][k2]['status'] in OFFEN]}")
            elif sorted(d.get("vorgaenger", [])) != vor:
                f.append(f"vorgaenger muss genau die früheren Stränge mit derselben Regel nennen: {vor} (G8-09)")
            if d["art"] != "uebung" and zaehler(st)["plaetze_belegt"] >= MAX_STRAENGE:
                f.append(f"schon {MAX_STRAENGE} Plätze belegt (aktiv oder reserviert): abgewiesen; kein späteres Nachrücken, neue Registrierung nötig")
        if not f:                                                # semantische Prüfung VOR «aktiv» (G9-07): der Signalrechner des Strangs läuft einmal zur Probe
            erg = u.rufe(cd, "finde", dict(reg=d, beginn=str(heute), heute=str(heute), sonder=sonder))
            if erg.get("fehler"):
                fehler.append(dict(kennung=k, fehler=[f"Signalrechner zurzeit nicht verfügbar ({erg['fehler']}); die Aufnahme wird im nächsten Lauf wieder versucht"]))
                continue                                         # vorübergehend: weder aufgenommen noch abgewiesen
            f = list(erg.get("struktur") or [])
        if f:
            setze(k, "abgewiesen", "; ".join(f), sha256=h, art=art if isinstance(art, str) else None, erstmals_gesehen_utc=jz)
            fehler.append(dict(kennung=k, fehler=f)); continue
        setze(k, "aktiv", "registriert und geprüft", sha256=h, art=d["art"], beginn=str(heute), aufnahme_commit=auf[0], aufnahme_zeit_utc=_fmt(auf[1]),
              erstmals_gesehen_utc=jz, code_commit=d["code_commit"], schlusstag=d["schlusstag"], regeln=regeln, vorgaenger=vor, umgebung=u.versionen())
        erst_finde[k] = erg
    for k in list(offen()):
        if k not in gesehen:
            setze(k, "gestoppt", "Registrierungsdatei fehlt (endgültig)")
    # je Strang: Schlussauswertung oder Handelsbuch
    reihe_bis = {}
    for z in laeufe:
        for r in z.get("regeln", []):
            reihe_bis[(r["strang"], r["regel"])] = r.get("reihe_bis")
    if nur_schluss is not None:
        if nur_schluss not in offen() or nur_schluss in ruht:
            s = st["straenge"].get(nur_schluss)
            p_erg = os.path.join(logdir, f"schluss_{nur_schluss}.json")
            if s and s["status"] == "ausgewertet" and os.path.exists(p_erg):
                return json.load(open(p_erg, encoding="utf-8"))
            raise Abbruch(f"Strang {nur_schluss}: Status «{s['status'] if s else 'unbekannt'}» lässt keine Schlussauswertung zu" + (f" ({s['grund']})" if s else ""))
        return _schluss(nur_schluss, inhalt[nur_schluss], st, buch, buch_nr, ordner, logdir, ds, sonder, u, setze)
    versionen = u.versionen(); abweichend = []
    for k, s in list(offen().items()):
        if k in ruht:
            continue
        d = inhalt[k]
        if not umgebung_gleich(s.get("umgebung"), versionen):
            abweichend.append(k)                                 # vermerkt; vor echten Strängen wird daraus eine Sperre mit Freigabe (G9-04)
        if s["status"] == "reserviert" or heute > _tag(s["schlusstag"]):
            if s.get("art") == "uebung":
                setze(k, "beendet_ohne_urteil", "Übung beendet (Übungsstränge werden nie ausgewertet)"); continue
            try:
                _schluss(k, d, st, buch, buch_nr, ordner, logdir, ds, sonder, u, setze)
            except Abbruch as e:
                fehler.append(dict(kennung=k, fehler=[f"Schlussauswertung: {e}"]))
            continue
        cd = u.code_dir(s["code_commit"])
        erg = erst_finde.get(k) or (u.rufe(cd, "finde", dict(reg=d, beginn=s["beginn"], heute=str(heute), sonder=sonder)) if cd else dict(fehler="festgeschriebener Code nicht verfügbar"))
        ent = None
        if not erg.get("fehler"):
            erkannt = _fmt(u.uhr())                              # G8-01: Uhr NACH der Signalrechnung dieses Strangs
            ent = u.rufe(cd, "buche", dict(reg=d, alt=[z for z in buch if z["strang"] == k], gefunden=erg["regeln"], kalender=erg["kalender"],
                                           reihe_bis_vorher=[reihe_bis.get((k, i)) for i in range(len(d["regeln"]))], erkannt_utc=erkannt))
        if erg.get("fehler") or ent.get("fehler"):
            grund = erg.get("fehler") or ent["fehler"]
            zeilen = [dict(regel=None, ereignis="ausfall", grund=grund, erkannt_utc=_fmt(u.uhr()))]
            fehler.append(dict(kennung=k, fehler=[grund]))
        else:
            zeilen = ent["zeilen"]
            for i, e in enumerate(erg["regeln"]):
                rb = e["reihe_bis"]; alt_rb = reihe_bis.get((k, i))
                b = dict(strang=k, regel=i, reihe_bis=rb, neu=sum(1 for z in zeilen if z.get("regel") == i))
                if rb is not None and alt_rb == rb and (heute - _tag(rb)).days > 10:
                    b["veraltet"] = True                         # alte Datei ist kein neuer Nullwert
                bericht.append(b)
        gespeichert = _fmt(u.uhr())
        for z in zeilen:
            z.update(strang=k, lauf_start_utc=jz, gespeichert_utc=gespeichert, datenstand=ds, code_commit=s["code_commit"])
        anhaengen(p_buch, zeilen); buch += zeilen; buch_nr += list(range(buch_zeilen, buch_zeilen + len(zeilen))); buch_zeilen += len(zeilen); neue_zeilen += len(zeilen)
    zus = dict(kopf_zus, datenstand=ds, sha_dispatcher=sha_d, umgebung=versionen, umgebung_abweichend=abweichend,
               basen={n: os.environ.get(n) for n in UMGEBUNG_ERLAUBT}, aktiv=sorted(k for k, s in st["straenge"].items() if s["status"] == "aktiv"),
               zaehler=zaehler(st), neue_zeilen=neue_zeilen, statuswechsel=status_neu, regeln=bericht, fehler=fehler)
    zus["siegel"] = {n: [journal_lesen(pfade[n])[1]["zeilen"], None] for n in ("status", "handelsbuch", "veroeffentlicht")}
    for n in zus["siegel"]:
        zus["siegel"][n][1] = praefix_sha(pfade[n], zus["siegel"][n][0])
    anhaengen(p_laeufe, [zus])
    schreibe_ansicht(p_stand, dict(hinweis="Ansicht; massgebend ist status.jsonl", **st))
    return zus


def _schluss(k, d, st, buch, buch_nr, ordner, logdir, ds, sonder, u, setze):
    """Einmalige Schlussauswertung als beschreibendes Papierergebnis (E32g). Erst reservieren (Aufträge, Zeitnachweise,
    Datenstand und Prüfsummen der Kursdateien einfrieren), dann rechnet der festgeschriebene Code. Ein Wiederanlauf
    setzt genau die reservierte Instanz fort; weichen Daten oder Aufträge ab, bricht er mit Integritätsfehler ab."""
    s = st["straenge"][k]; jetzt = u.uhr(); jz = _fmt(jetzt); heute = jetzt.date()
    p_res, p_erg = os.path.join(logdir, f"schluss_{k}.reserviert.json"), os.path.join(logdir, f"schluss_{k}.json")
    if s.get("art") == "uebung":
        raise Abbruch("Übungsstränge werden nicht ausgewertet.")
    if not heute > _tag(s["schlusstag"]):
        raise Abbruch("vor Ablauf des Schlusstags gibt es keine Auswertung (keine Zwischenstände).")
    if ds is None:
        raise Abbruch("Datenstand fehlt oder ist unvollständig.")
    dateien = ["acwi"] + [r["ziel"] for r in d["regeln"]]
    cd = u.code_dir(s["code_commit"])
    if cd is None:
        raise Abbruch("festgeschriebener Code nicht verfügbar")
    if not os.path.exists(p_res):
        vermerke = journal_lesen(os.path.join(logdir, VERMERK))[0]
        mein = [(z, n) for z, n in zip(buch, buch_nr) if z["strang"] == k]
        auftraege = [dict(z, veroeffentlicht_utc=veroeffentlicht_utc(vermerke, n)) for z, n in mein if z["ereignis"] == "auftrag"]
        f = u.daten_pruefen(ds)
        if f:
            raise Abbruch("Datenstand nicht belegt: " + "; ".join(f))
        bed = u.rufe(cd, "bedarf", dict(auftraege=auftraege, sonder=sonder))
        if bed.get("fehler"):
            raise Abbruch(bed["fehler"])
        fehlt = sorted(n for n, t in bed["bedarf"].items() if (u.kurse_bis(n) or "") < t)   # G9-05: jede benötigte Kursdatei, nach Sonderschliessungen
        if fehlt and (heute - _tag(s["schlusstag"])).days <= WARTEN_TAGE:
            raise Abbruch(f"Kurse reichen noch nicht bis zum letzten Ausstieg ({', '.join(fehlt)}); die Auswertung wartet (höchstens {WARTEN_TAGE} Tage nach dem Schlusstag).")
        zeilen = [z for z, _ in mein]
        res = dict(kennung=k, reserviert_utc=jz, datenstand=ds, code_commit=s["code_commit"], beginn=s["beginn"], registrierung_sha256=s["sha256"],
                   auftraege=auftraege, auftraege_sha256=sha(json.dumps(auftraege, sort_keys=True, ensure_ascii=False)),
                   manifest=u.manifest(dateien), sonderschliessungen=sonder, umgebung=u.versionen(), sha_dispatcher=datei_sha(os.path.abspath(__file__)),
                   kurse_unvollstaendig_nach_wartefrist=fehlt,
                   kein_auftrag={g: sum(1 for z in zeilen if z["ereignis"] == "kein_auftrag" and z.get("grund") == g)
                                 for g in sorted({z.get("grund") for z in zeilen if z["ereignis"] == "kein_auftrag"})},
                   revisionen=sum(1 for z in zeilen if z["ereignis"] == "revision"), ausfaelle=sum(1 for z in zeilen if z["ereignis"] == "ausfall"))
        schreibe_einmal(p_res, res)
    if s["status"] == "aktiv":
        setze(k, "reserviert", "Schlussauswertung reserviert")
    res = json.load(open(p_res, encoding="utf-8"))
    if os.path.exists(p_erg):                                      # vollständiges Ergebnis vorhanden: nur noch den Status nachführen
        setze(k, "ausgewertet", "Schlussauswertung gespeichert")
        return json.load(open(p_erg, encoding="utf-8"))
    if res["auftraege_sha256"] != sha(json.dumps(res["auftraege"], sort_keys=True, ensure_ascii=False)) or res["registrierung_sha256"] != s["sha256"]:
        raise Abbruch("Integritätsfehler: Die Reservierung passt nicht zu ihrer Prüfsumme oder zur Registrierung.")
    if res["datenstand"] != ds:
        raise Abbruch(f"Fortsetzung nur mit dem reservierten Datenstand (main {res['datenstand']['main'][:12]}).")
    if u.manifest(dateien) != res["manifest"]:
        raise Abbruch("Integritätsfehler: Die Kursdateien weichen vom reservierten Stand ab; zuerst den reservierten Datenstand wiederherstellen.")
    f = u.daten_pruefen(ds)
    if f:
        raise Abbruch("Datenstand nicht belegt: " + "; ".join(f))
    if not umgebung_gleich(u.versionen(), res.get("umgebung")):
        rv = res.get("umgebung") or {}
        raise Abbruch(f"Fortsetzung nur mit der reservierten Rechenumgebung (Python {rv.get('python')}, numpy {rv.get('numpy')}, pandas {rv.get('pandas')}).")
    w = u.rufe(cd, "schliesse", dict(reg=d, beginn=res["beginn"], auftraege=res["auftraege"], daten_dir=u.daten_dir, sonder=res["sonderschliessungen"]))
    if w.get("fehler"):
        raise Abbruch(w["fehler"])
    erg = dict(kennung=k, art="Papierergebnis, beschreibend (V3.15 E32g); keine Aussage mit 5% Fehlalarm; kein Auftrag zu handeln",
               ausgewertet_utc=jz, reserviert_utc=res["reserviert_utc"], beginn=res["beginn"], schlusstag=d["schlusstag"], datenstand=res["datenstand"],
               code_commit=res["code_commit"], registrierung_sha256=res["registrierung_sha256"], auftraege_sha256=res["auftraege_sha256"],
               manifest=res["manifest"], kein_auftrag=res["kein_auftrag"], revisionen=res["revisionen"], ausfaelle=res["ausfaelle"],
               **{x: w[x] for x in w if x != "protokoll"})
    schreibe_einmal(p_erg, erg)                                    # gibt es die Datei schon, gilt die vorhandene
    setze(k, "ausgewertet", "Schlussauswertung gespeichert")
    return json.load(open(p_erg, encoding="utf-8"))


def schluss(ordner, logdir, kennung, datenstand="", umgebung=None):
    """Direkter Aufruf der Schlussauswertung: durchläuft dieselben Schutzprüfungen wie jeder Lauf (G8-07, G8-08)."""
    return lauf(ordner, logdir, datenstand, umgebung, nur_schluss=kennung)


# ============================================================================================== Veröffentlichen (nur vorwaerts/, streng anhängend)
def anhaenge_verstoesse(oben, rel, ref):
    """Vergleicht den lokalen Journalordner mit dem entfernten Stand «ref» (G9-02 B). Journale dürfen nur länger werden
    (der entfernte Inhalt ist ein Anfangsstück des lokalen), Schlussdateien bleiben bytegleich. Gibt die Verstösse zurück."""
    liste = _git("ls-tree", "-r", "--name-only", ref, "--", rel, cwd=oben)
    out = []
    for f in [x for x in (liste or "").split("\n") if x]:
        n = os.path.basename(f); fern = _git("show", f"{ref}:{f}", cwd=oben, roh=True); p = os.path.join(oben, f)
        lokal = open(p, "rb").read() if os.path.exists(p) else None
        if n.endswith(".jsonl"):
            if lokal is None or not lokal.startswith(fern or b""):
                out.append(f"{n}: der veröffentlichte Inhalt ist kein Anfangsstück des eigenen Stands")
        elif n.startswith("schluss_") and ".teil." not in n:
            if lokal != fern:
                out.append(f"{n}: veröffentlichte Schlussdatei fehlt lokal oder weicht ab")
    return out


def veroeffentlichen(logdir, uhr, zweig=ZWEIG, botschaft="Vorwärtsregister", versuche=4):
    """Checkt den Journalordner ein und schiebt ihn auf den Zweig. Vor jedem Push wird der entfernte Stand geholt und die
    Anhängeregel geprüft; ein Verstoss bricht ab, statt eine Seite gewinnen zu lassen. Gibt {gepusht, zeit, kopf} zurück;
    «zeit» ist die Uhr NACH dem gelungenen Push."""
    if not os.path.isdir(logdir):
        return dict(gepusht=False, grund="kein Journalordner")
    oben, rel = _git_ort(logdir)
    if not oben:
        raise Abbruch("Journalordner liegt in keinem Git-Arbeitsbaum.")
    for n in os.listdir(logdir):
        if ".teil." in n:
            os.remove(os.path.join(logdir, n))                   # liegengebliebene Hilfsdateien werden nie veröffentlicht
    wer = ("-c", "user.name=Prüfstand Vorwärtsregister", "-c", "user.email=actions@users.noreply.github.com")
    ref = f"refs/remotes/origin/{zweig}"
    _git("add", "-A", "--", rel, cwd=oben)
    if _git("diff", "--cached", "--quiet", "--", rel, cwd=oben, code=True) != 0:
        if _git(*wer, "commit", "-q", "-m", f"{botschaft} {_fmt(uhr())}", "--", rel, cwd=oben, code=True) != 0:
            raise Abbruch("Commit des Journalordners gescheitert.")
    for _ in range(versuche):
        if _git("fetch", "-q", "origin", f"+refs/heads/{zweig}:{ref}", cwd=oben, code=True) != 0:
            continue
        if _git("rev-parse", ref, cwd=oben) == _git("rev-parse", "HEAD", cwd=oben):
            return dict(gepusht=False, grund="nichts Neues")
        v_ = anhaenge_verstoesse(oben, rel, ref)
        if v_:
            raise Abbruch("Veröffentlichen abgebrochen, Anhängeregel verletzt: " + "; ".join(v_) + ". Die lokale Ausgabe bleibt für die Bergung liegen.")
        if _git("merge-base", "--is-ancestor", ref, "HEAD", cwd=oben, code=True) != 0:
            if _git(*wer, "rebase", "-q", ref, cwd=oben, code=True) != 0:
                _git("rebase", "--abort", cwd=oben)
                raise Abbruch("Veröffentlichen abgebrochen: Der eigene Stand lässt sich nicht hinter den entfernten setzen. Die lokale Ausgabe bleibt für die Bergung liegen.")
            v_ = anhaenge_verstoesse(oben, rel, ref)
            if v_:
                raise Abbruch("Veröffentlichen abgebrochen nach dem Umsetzen: " + "; ".join(v_))
        if _git("push", "-q", "origin", f"HEAD:refs/heads/{zweig}", cwd=oben, code=True) == 0:
            return dict(gepusht=True, zeit=uhr(), kopf=_git("rev-parse", "HEAD", cwd=oben))
    raise Abbruch(f"Push nach {versuche} Versuchen gescheitert. Die lokale Ausgabe bleibt für die Bergung liegen.")


def veroeffentliche_mit_vermerk(logdir, uhr, zweig=ZWEIG):
    """Betriebsweg nach jedem Lauf: veröffentlichen, die Zeit nach dem gelungenen Push vermerken, den Vermerk veröffentlichen."""
    e = veroeffentlichen(logdir, uhr, zweig)
    if e["gepusht"]:
        vermerken(logdir, _fmt(e["zeit"]), e["kopf"])
        e["vermerk"] = veroeffentlichen(logdir, uhr, zweig, botschaft="Vorwärtsregister: Vermerk der Veröffentlichung")
    return e


if __name__ == "__main__":
    modus_ = os.environ.get("PS_VORWAERTS_MODUS")
    if modus_ in ("pruefe", "finde", "buche", "bedarf", "schliesse"):   # festgeschriebener Code, vom Dispatcher in einem eigenen Prozess gerufen
        e = json.load(open(os.environ["PS_VORWAERTS_EIN"], encoding="utf-8"))
        if modus_ == "pruefe":
            a = dict(fehler_liste=pruefe_sicher(e["reg"], e["beginn"]), protokoll=PROTOKOLL)
        elif modus_ == "finde":
            sys.path.insert(0, HIER)
            a = finde(e["reg"], e["beginn"], _tag(e["heute"]), e.get("sonder") or ())
        elif modus_ == "buche":
            a = buche(e["reg"], e["alt"], e["gefunden"], e["kalender"], e["reihe_bis_vorher"], e["erkannt_utc"])
        elif modus_ == "bedarf":
            a = bedarf(e["auftraege"], e.get("sonder") or ())
        else:
            a = schliesse(e["reg"], e["beginn"], e["auftraege"], e["daten_dir"], e.get("sonder") or ())
        with open(os.environ["PS_VORWAERTS_AUS"], "w", encoding="utf-8") as f_:
            json.dump(a, f_, ensure_ascii=False, allow_nan=False)
        sys.exit(0)
    for pfad_, var_ in (("_daten-energie", "PS_BASIS_ENERGIE"), ("_daten-neu", "PS_BASIS_NEU")):
        if var_ not in os.environ and os.path.isdir(os.path.join(HIER, pfad_, "data")):
            os.environ[var_] = "file://" + os.path.join(HIER, pfad_, "data")
    ordner_ = os.environ.get("PS_VORWAERTS_DIR", os.path.join(HIER, "vorwaerts"))
    logdir_ = os.environ.get("PS_VORWAERTS_LOG", os.path.join(HIER, "_lernen", "vorwaerts"))
    try:
        if sys.argv[1:] == ["veroeffentliche"]:
            e_ = veroeffentliche_mit_vermerk(logdir_, Umgebung().uhr)
            print("Veröffentlichung:", json.dumps(e_, ensure_ascii=False, default=str)); sys.exit(0)
        z_ = lauf(ordner_, logdir_, os.environ.get("PS_VORWAERTS_STAND", ""))
    except Abbruch as e_:
        print("ABBRUCH:", e_); sys.exit(1)
    print(f"Vorwärtsregister {z_['heute']} (Modus {z_['modus']}): Registrierungen {z_['registrierungen']}, aktiv {len(z_['aktiv'])}, neue Zeilen {z_['neue_zeilen']}, Fehler {len(z_['fehler'])}")
    for f_ in z_["fehler"]:
        print("  HINWEIS" if "gesperrt" in " ".join(f_["fehler"]) else "  FEHLER", f_["kennung"], "; ".join(f_["fehler"]))
    if any("gesperrt" not in " ".join(f_["fehler"]) for f_ in z_["fehler"]):
        sys.exit(1)
