"""Prüfstand – Bestätigungstest der Finalisten (Verfassung V3.12, E27c; Astra-Gutachten 5, G5-18).

Reine Funktionen ohne Daten und ohne Netz. Sie werden zuerst an Welten ohne Netto-Effekt geprüft (E27d) und erst nach
bestandener Abnahme und Retos Freigabe auf versiegelte Daten angewendet. Dieses Modul liest selbst keine Kurse.

Endpunkt (E27): täglicher Netto-Mehrertrag der festen Regel gegenüber dem Vergleichsindex, in Prozentpunkten.
  - Je Einheit Kapital am Einstieg: tägliche Wertänderung des Ziels minus tägliche Wertänderung des Vergleichsindex,
    am Einstiegstag p von der Eröffnung zum Schluss, an den folgenden h - 1 Handelstagen von Schluss zu Schluss.
  - Die Summe über die Haltezeit ist damit genau die Mehrrendite der Suche (Rechengleichheit, Astra-Gutachten 5).
  - Ausserhalb der Haltezeit: null. Die Kosten je Wechsel (hin und zurück) werden am Einstiegstag abgezogen.
  - Einstiege mit weniger als max(10, h) Handelstagen Abstand zum vorigen werden wie in der Suche ausgelassen.
Nullhypothese: Der mittlere tägliche Netto-Mehrertrag ist nicht grösser als null (Grenze: brutto gleich Kosten).

Test 1 (zuerst): Block-Bootstrap in Kalenderzeit, Ringblöcke von 20 Handelstagen, zentriert:
  p = (k + 1) / (B + 1), k = Zahl der Ziehungen mit (Mittel* - Mittel) >= Mittel.
Test 2 (Ersatz): Vorzeichenwechsel in Blöcken von 20 Handelstagen auf den Netto-Blocksummen:
  p = (k + 1) / (B + 1), k = Zahl der Ziehungen mit Summe(Vorzeichen * Blocksumme) >= Summe(Blocksumme).
Zähler und Nenner werden ungerundet zurückgegeben. Tests: python test_bestaetigung.py
"""
import numpy as np

BLOCK = 20
ZIEHUNGEN = 10000


def entclustern(pos, abstand):
    out, letzte = [], -10**9
    for p in np.sort(np.asarray(pos, dtype=int)):
        if p - letzte >= abstand:
            out.append(int(p)); letzte = p
    return np.array(out, dtype=int)


def _koerbe(oc_bench, cc_bench):
    """Vergleichsindex als Liste von Körben in Rangfolge. Ein Korb ist eine Liste (Gewicht, oc, cc); er wird am Einstieg
    gekauft und gehalten. So lässt sich der Ersatzindex vor Beginn von ACWI genau wie in der Suche rechnen: 55% der
    ganzen SPY-Rendite plus 45% der ganzen EFA-Rendite des Fensters (Astra-Gutachten 6, G6-05)."""
    if isinstance(oc_bench, (list, tuple)) and cc_bench is None:
        return [[(float(g), np.asarray(o, dtype=float), np.asarray(c, dtype=float)) for g, o, c in korb] for korb in oc_bench]
    return [[(1.0, np.asarray(oc_bench, dtype=float), np.asarray(cc_bench, dtype=float))]]


def tagesertrag(oc_ziel, cc_ziel, oc_bench, cc_bench, einstiege, h, kosten):
    """Täglicher Netto-Mehrertrag in Prozentpunkten. oc_*: Rendite Eröffnung->Schluss je Tag (als Anteil), cc_*: Rendite
    Schluss->Schluss. einstiege: Tagesindizes (Eröffnung dieses Tages). Gibt (x, genutzte_einstiege) zurück. Ein Einstieg,
    dessen Haltezeit nicht ganz im Zeitraum liegt oder in der ein Kurs fehlt, wird ausgelassen (kein Teilfenster).
    Vergleichsindex: zwei Reihen (oc_bench, cc_bench) oder – mit cc_bench=None – eine Liste von Körben in Rangfolge;
    genutzt wird der erste Korb, der in der ganzen Haltezeit Kurse hat."""
    n = len(oc_ziel)
    x = np.zeros(n)
    genutzt = []
    koerbe = _koerbe(oc_bench, cc_bench)
    for p in entclustern(einstiege, max(10, h)):
        if p < 0 or p + h > n:
            continue
        rz = np.r_[oc_ziel[p], cc_ziel[p + 1:p + h]]
        if np.isnan(rz).any():
            continue
        vb = None
        for korb in koerbe:
            teile = [(g, np.r_[o[p], c[p + 1:p + h]]) for g, o, c in korb]
            if all(not np.isnan(r).any() for _, r in teile):
                vb = sum(g * np.cumprod(1.0 + r) for g, r in teile) / sum(g for g, _ in teile)
                break
        if vb is None:
            continue
        # Tagesbeitrag = Wertänderung des Ziels minus Wertänderung des Vergleichsindex, je Einheit Kapital am Einstieg.
        # Die Summe über die Haltezeit ist genau die Mehrrendite der Suche: Schluss(p+h-1)/Eröffnung(p) Ziel minus Index.
        vz = np.cumprod(1.0 + rz)
        w = np.diff(np.r_[1.0, vz]) - np.diff(np.r_[1.0, vb])
        x[p:p + h] += 100.0 * w
        x[p] -= kosten
        genutzt.append(p)
    return x, np.array(genutzt, dtype=int)


def _gueltig(x):
    """Astra-Gutachten 6, G6-08: Ungültige Zahlen dürfen nie einen kleinen p-Wert erzeugen. Bei NaN, unendlichen Werten
    oder falscher Form bricht der Test mit einem Fehler ab («nicht prüfbar»), statt ein Ergebnis zu liefern."""
    x = np.asarray(x, dtype=float)
    if x.ndim != 1 or len(x) == 0 or not np.isfinite(x).all():
        raise ValueError("Tagesertrag nicht prüfbar: leer, falsche Form oder nicht endliche Werte")
    return x


def blocktest(x, rng, block=BLOCK, ziehungen=ZIEHUNGEN):
    """Test 1. Gibt (k, B, mittel) zurück."""
    x = _gueltig(x); n = len(x)
    if n < 2 * block:
        return None, None, float("nan")
    m = float(x.mean())
    cs = np.concatenate([[0.0], np.cumsum(np.concatenate([x, x[:block]]))])
    bs = cs[block:block + n] - cs[:n]                       # Summe des Ringblocks ab jedem Starttag
    nb = int(np.ceil(n / block))
    k = 0; rest = ziehungen
    while rest > 0:                                          # in Portionen, damit der Speicher klein bleibt
        z = min(rest, 2000)
        s = bs[rng.integers(0, n, size=(z, nb))].sum(axis=1) / (nb * block)
        k += int(np.sum(s - m >= m)); rest -= z
    return k, int(ziehungen), m


def vorzeichentest(x, rng, block=BLOCK, ziehungen=ZIEHUNGEN):
    """Test 2 (Ersatz). Gibt (k, B, mittel) zurück. Blöcke ohne Ertrag ändern die Statistik nicht."""
    x = _gueltig(x); n = len(x)
    nb = n // block
    if nb < 2:
        return None, None, float("nan")
    s = x[:nb * block].reshape(nb, block).sum(axis=1)
    if n > nb * block:
        s = np.append(s, x[nb * block:].sum())
    s = s[s != 0.0]
    t = float(s.sum())
    if len(s) == 0:
        return int(ziehungen), int(ziehungen), 0.0
    k = 0; rest = ziehungen
    while rest > 0:
        z = min(rest, 2000)
        v = rng.choice((-1.0, 1.0), size=(z, len(s)))
        k += int(np.sum(v @ s >= t - 1e-12)); rest -= z
    return k, int(ziehungen), float(x.mean())


def p_wert(k, b):
    """(k + 1) / (B + 1); nicht prüfbar: 1."""
    return 1.0 if k is None else (k + 1) / (b + 1)


def jahresertrag(x, tage_pro_jahr=252):
    """Netto-Mehrertrag in Prozentpunkten pro Jahr (einfaches Mass: Tagesmittel mal Handelstage)."""
    return float(np.mean(x) * tage_pro_jahr)


MIN_EREIGNISSE = 10


def obergrenze_95(k, n):
    """Exakte einseitige obere 95%-Grenze (Clopper-Pearson) für einen Anteil k von n; ohne scipy, per Bisektion."""
    from math import lgamma, log, exp
    if k >= n:
        return 1.0
    def cdf(p):                                   # P(X <= k) für X ~ Bin(n, p)
        lp, lq = log(p), log(1.0 - p)
        return sum(exp(lgamma(n + 1) - lgamma(i + 1) - lgamma(n - i + 1) + i * lp + (n - i) * lq) for i in range(k + 1))
    lo, hi = k / n if k else 0.0, 1.0
    lo = max(lo, 1e-12)
    for _ in range(60):
        m = (lo + hi) / 2
        if cdf(m) > 0.05:
            lo = m
        else:
            hi = m
    return hi


def k_max(n, niveau):
    """Grösste Zahl Fehlalarme in n Welten, bei der die obere 95%-Grenze das Niveau nicht übersteigt (Astra-Gutachten 6,
    Frage 3: Messunsicherheit ist kein zusätzliches Budget)."""
    k = int(n * niveau)
    while k >= 0 and obergrenze_95(k, n) > niveau:
        k -= 1
    return k


def schwelle_diskret(p_null, niveau, k_erlaubt=None, ziehungen=ZIEHUNGEN):
    """Geeichte Schwelle auf dem GANZEN Raster der erreichbaren p-Werte j / (ziehungen + 1) (Astra-Gutachten 6, G6-03, und
    Gutachten 7, G7-14): die grösste Rasterstufe c <= niveau, bei der höchstens k_erlaubt Nullwelten p <= c haben. Bindungen
    zählen voll. Gesucht wird auf dem ganzen Raster, nicht nur unter den beobachteten Null-p-Werten (sonst wäre die
    Schwelle unnötig streng). Gibt 0.0 zurück, wenn schon die kleinste Stufe zu viele Welten verwirft."""
    p = np.sort(np.asarray(p_null, dtype=float)); n = len(p)
    if k_erlaubt is None:
        k_erlaubt = k_max(n, niveau)
    b1 = int(ziehungen) + 1
    j_max = int(np.floor(niveau * b1 + 1e-9))                  # grösste Stufe j / b1 <= niveau
    if k_erlaubt < 0 or j_max < 1:
        return 0.0
    if k_erlaubt >= n or p[k_erlaubt] > j_max / b1 + 1e-12:    # höchstens k_erlaubt Nullwelten liegen auf oder unter der Stufe
        return j_max / b1
    j = int(np.ceil(p[k_erlaubt] * b1 - 1e-9)) - 1             # grösste Stufe strikt unter dem (k_erlaubt + 1)-kleinsten p
    return j / b1 if j >= 1 else 0.0


def ereignisse_buendel(einstiege_je_regel):
    """Zahl der Ereignisse eines Finalisten (V3.15): verschiedene genutzte Einstiegstage über alle Regeln. Mehrere Regeln,
    die am selben Tag einsteigen, zählen als ein Ereignis (gleichzeitige Teilgeschäfte sind keine getrennten Informationen)."""
    tage = set()
    for g in einstiege_je_regel:
        tage.update(int(x) for x in np.asarray(g).ravel())
    return len(tage)


def urteile_zaehlen(p, ereignisse, schwelle):
    """Wendet dieselbe Urteilsfunktion auf viele Pfade an (Welten, Abnahme, Öffnung): Anteile der drei Urteile."""
    u = [urteil(float(a), schwelle, int(b)) for a, b in zip(p, ereignisse)]
    n = max(len(u), 1)
    return {k: u.count(k) / n for k in ("bestätigt", "nicht bestätigt", "unentschieden")}


def urteil(p, schwelle, ereignisse):
    """«bestätigt», «nicht bestätigt» oder «unentschieden» (weniger als MIN_EREIGNISSE genutzte Einstiege; E32-Logik)."""
    if ereignisse < MIN_EREIGNISSE:
        return "unentschieden"
    return "bestätigt" if p <= schwelle else "nicht bestätigt"
