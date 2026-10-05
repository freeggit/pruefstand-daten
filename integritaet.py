"""Prüfstand – Integrität der Bewertungen (Verfassung V3.11, E28; Reto am 4.10.2026: «ok, gerne freigeben»).

Anlass: Astra-Gutachten 4 (meta/astra_2026-10-04), Befunde N02 bis N05. Reine Funktionen ohne Daten und ohne Netz,
genutzt von vorreg.py (Registrierung einfrieren, ungerundete Entscheidgrössen) und einchecken.py (ein veröffentlichtes
Endurteil darf sich nicht ändern). Tests: python test_integritaet.py
"""
import hashlib, json

ENDGUELTIG = ("bewertet", "kontaminiert", "ungueltig", "verfallen")
# Felder einer endgültigen Zeile, die sich nach der Veröffentlichung nie mehr ändern dürfen. p_holm und v_baustein
# gehören bewusst nicht dazu: Holm läuft über die registrierte Familie und wird neu gebildet, wenn eine wartende
# Hypothese bewertet wird.
FEST = ("status", "n", "mu", "mu0", "t", "t1", "t2", "p_f5", "p_f5_zaehler", "p_f5_nenner", "n_verdacht",
        "t_ohne_verdacht", "bewertet_utc", "code_hash", "daten_hash", "methodenstand", "roh")


class IntegritaetsFehler(Exception):
    pass


def ohne_nan(o):
    """Ersetzt NaN und unendliche Werte durch None, in beliebig verschachtelten Listen und Wörterbüchern. JSON kennt
    kein NaN; eine Datei mit NaN lässt sich nicht in die Datenbank übernehmen (Betriebslauf 27, S0022, 5.10.2026)."""
    if isinstance(o, float):
        return None if (o != o or o in (float("inf"), float("-inf"))) else o
    if isinstance(o, dict):
        return {k: ohne_nan(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [ohne_nan(v) for v in o]
    return o


def _h(h):
    try:
        hh = int(h.get("h", 0))
    except (TypeError, ValueError):
        hh = 0
    return [h.get("id"), h.get("indikator"), h.get("art"), h.get("ziel"), hh, h.get("erwartung", "positiv")]


def registrierung_sha(ch):
    """Prüfsumme der vollständigen kanonischen Registrierung: Charge, Familiengrösse und je Hypothese
    id, Indikator, Extremtyp, Ziel, Haltedauer, Erwartung – in der registrierten Reihenfolge."""
    hyps = ch.get("hypothesen", [])
    kanon = {"charge": ch.get("charge"), "n": len(hyps), "hypothesen": [_h(h) for h in hyps]}
    return hashlib.sha256(json.dumps(kanon, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def familie_pruefen(ch, alt, max_n):
    """Wirft IntegritaetsFehler, wenn die Charge ungültig ist oder von der eingefrorenen Registrierung abweicht.
    alt = bereits veröffentlichte Ergebnisdatei (oder None). Gibt die Prüfsumme zurück."""
    hyps = ch.get("hypothesen")
    if not isinstance(hyps, list) or not hyps:
        raise IntegritaetsFehler("Charge ohne Hypothesen")
    if len(hyps) > max_n:
        raise IntegritaetsFehler(f"Charge mit {len(hyps)} Hypothesen, erlaubt sind höchstens {max_n} (kein stilles Abschneiden)")
    ids = [h.get("id") for h in hyps]
    if any(i in (None, "") for i in ids) or len(set(ids)) != len(ids):
        raise IntegritaetsFehler("Hypothesen ohne id oder mit doppelter id")
    sha = registrierung_sha(ch)
    if alt:
        fest = alt.get("registrierung_sha")
        if fest:
            if fest != sha:
                raise IntegritaetsFehler(f"Registrierung weicht vom eingefrorenen Stand ab ({fest[:12]} gegen {sha[:12]})")
        else:
            # Altbestand ohne Prüfsumme: mindestens Familiengrösse und Schlüssel müssen stimmen
            alt_keys = [z.get("schluessel") for z in alt.get("hypothesen", [])]
            neu_keys = [f"{h.get('indikator')}|{h.get('art')}|{h.get('ziel')}|{_h(h)[4]}" for h in hyps]
            if alt_keys != neu_keys:
                raise IntegritaetsFehler("Registrierung weicht von der veröffentlichten Bewertung ab (Schlüssel oder Familiengrösse)")
    return sha


def p_roh(z):
    """Ungerundeter p-Wert einer bewerteten Zeile: aus Zähler und Nenner, sonst (Altbestand) der gespeicherte Wert."""
    if z.get("status") != "bewertet":
        return 1.0
    a, b = z.get("p_f5_zaehler"), z.get("p_f5_nenner")
    if isinstance(a, int) and isinstance(b, int) and b > 0:
        return a / b
    return float(z["p_f5"])


def wert_roh(z, feld):
    """Ungerundete Entscheidgrösse (mu, t1, t2, t_ohne_verdacht, n) aus z['roh'], sonst der gespeicherte Wert."""
    r = z.get("roh")
    if isinstance(r, dict) and feld in r:
        return r[feld]
    return z.get(feld)


def endurteil_geaendert(veroeff, eigen):
    """Vergleicht zwei Fassungen einer Ergebnisdatei vorreg/<charge>.json. Gibt die Liste der Verstösse zurück:
    jede endgültige Zeile der veröffentlichten Fassung muss in der eigenen mit denselben festen Feldern stehen."""
    verst = []
    if not isinstance(veroeff, dict) or not isinstance(eigen, dict):
        return verst
    eig = {z.get("schluessel"): z for z in eigen.get("hypothesen", []) if isinstance(z, dict)}
    for z in veroeff.get("hypothesen", []):
        if not isinstance(z, dict) or z.get("status") not in ENDGUELTIG:
            continue
        k = z.get("schluessel"); e = eig.get(k)
        if e is None:
            verst.append({"schluessel": k, "feld": "(Zeile)", "veroeffentlicht": z.get("status"), "eigen": "fehlt"}); continue
        for f in FEST:
            if f in z and e.get(f) != z[f]:
                verst.append({"schluessel": k, "feld": f, "veroeffentlicht": z[f], "eigen": e.get(f)})
    fa, fb = veroeff.get("registrierung_sha"), eigen.get("registrierung_sha")
    if fa and fb != fa:
        verst.append({"schluessel": None, "feld": "registrierung_sha", "veroeffentlicht": fa, "eigen": fb})
    if veroeff.get("familie_n") is not None and eigen.get("familie_n") != veroeff.get("familie_n"):
        verst.append({"schluessel": None, "feld": "familie_n", "veroeffentlicht": veroeff.get("familie_n"), "eigen": eigen.get("familie_n")})
    return verst
