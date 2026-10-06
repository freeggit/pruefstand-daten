"""Tests für auswahl.py (reine Funktionen, ohne Daten). Aufruf: python test_auswahl.py"""
import datetime, math
import numpy as np
import auswahl as a


def k(kennung, score, t, reihe, ziel):
    return dict(kennung=kennung, score=score, t=t, grundreihe=reihe, ziel=ziel)


def test_grenzwert():
    j = a.jahre_bestaetigung(datetime.date(2026, 10, 6))
    assert abs(j - 5.676) < 0.01, j
    g = a.grenzwert(j)
    assert abs(g - 5.14) < 0.02, g                          # V3.13: «heute 5.1 Prozentpunkte»
    assert abs(a.staerke_naeherung(g, j) - a.STAERKE) < 1e-6   # am Grenzwert genau die Schwelle
    assert a.grenzwert(2 * j) > g and a.grenzwert(0) == 0.0
    assert abs(a._z(0.95) - 1.6449) < 1e-3 and abs(a._z(0.4) + 0.2533) < 1e-3


def test_rangfolge_und_beste():
    r = a.rangfolge([k("c", 0.5, 3.0, "r1", "xlu"), k("a", 0.2, 3.5, "r1", "gld"), k("b", 0.2, 3.9, "r2", "gld"),
                     k("d", 0.2, 3.9, "r3", "xle"), k("e", 0.6, 9.0, "r4", "xlb")])
    assert [x["kennung"] for x in r] == ["b", "d", "a", "c", "e"]        # Score, dann t absteigend, dann Kennung
    top = a.beste(r)
    assert [x["kennung"] for x in top] == ["b", "d", "c", "e"]           # «a»: Ziel gld schon vergeben; «c»: r1 frei
    assert len(a.beste(r, 2)) == 2


def test_waehlen():
    top = [k("eins", 0.1, 4, "r1", "z1"), k("zwei", 0.2, 4, "r2", "z2"), k("drei", 0.3, 4, "r3", "z3")]
    sw = {("eins",): 9.0, ("zwei",): 4.0, ("drei",): 3.0, ("eins", "zwei"): 5.0, ("eins", "zwei", "drei"): 4.0}
    f = lambda regeln: sw[tuple(x["kennung"] for x in regeln)]
    fin, pr = a.waehlen(top, f, 5.1)
    assert [x["kennung"] for x in fin] == ["zwei"] and len(pr) == 2      # beste einzelne Regel, die besteht
    fin, pr = a.waehlen(top, f, 2.0)
    assert fin is None and len(pr) == 5                                  # 3 einzelne, 2 Bündel geprüft
    sw2 = dict(sw); sw2[("zwei",)] = 8.0; sw2[("drei",)] = 8.0
    fin, pr = a.waehlen(top, lambda regeln: sw2[tuple(x["kennung"] for x in regeln)], 5.1)
    assert [x["kennung"] for x in fin] == ["eins", "zwei"]               # kleinstes Bündel
    # zweite Stufe: Vorprüfung bestanden, Welten zu schwach -> weiter zur nächsten Regel
    st = {("zwei",): 0.2, ("drei",): 0.55}
    fin, pr = a.waehlen(top, f, 5.1, lambda regeln: dict(staerke=st[tuple(x["kennung"] for x in regeln)]))
    assert [x["kennung"] for x in fin] == ["drei"]
    assert pr[1]["vorpruefung"] and not pr[1]["bestanden"] and "welten" not in pr[0]
    fin, _ = a.waehlen(top, lambda regeln: float("nan"), 5.1)
    assert fin is None                                                   # nicht endlich besteht nie


def test_schwankung_und_rho():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 0.5, 252 * 40)
    s = a.jahresschwankung(x)
    assert abs(s - 0.5 * math.sqrt(252)) < 0.8, s
    assert math.isnan(a.jahresschwankung(np.zeros(100))) and math.isnan(a.jahresschwankung(np.r_[x[:1000], np.nan]))
    assert a.rho1([1, 2, 3]) == 0.0 and a.rho1([1, -1, 1, -1, 1, -1]) == 0.0      # negativ wird null
    y = np.cumsum(rng.normal(size=400)); assert a.rho1(y) > 0.8
    assert a._r(float("nan")) is None and a._r(1.23456) == 1.235


def test_score():
    assert a.score_suche(4.0, [3.0, 4.0, 5.0]) == (3, 4)                 # 4.0 und 5.0 sind mindestens so hoch
    assert a.score_suche(9.0, [3.0, 4.0, 5.0]) == (1, 4) and a.score_suche(1.0, [3.0, 4.0]) == (3, 3)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
    print("alle Tests bestanden")
