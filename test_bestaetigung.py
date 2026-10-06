"""Tests zu bestaetigung.py (V3.12, E27c). Aufruf: python test_bestaetigung.py"""
import numpy as np
import bestaetigung as b

def ok(bed, name):
    assert bed, name
    print("ok ", name)

# 1 Tagesertrag: ein Einstieg, 3 Tage, Kosten am Einstiegstag
n = 40
ocz = np.full(n, 0.01); ccz = np.full(n, 0.02); ocb = np.zeros(n); ccb = np.full(n, 0.005)
x, g = b.tagesertrag(ocz, ccz, ocb, ccb, [5], 3, 0.88)
ok(list(g) == [5], "ein Einstieg genutzt")
ok(abs(x[5] - (1.0 - 0.88)) < 1e-12 and abs(x[6] - 100 * (1.01 * 0.02 - 0.005)) < 1e-12, "Einstiegstag Eröffnung->Schluss minus Kosten, danach Wertänderung Schluss->Schluss")
ok(abs(x[5:8].sum() + 0.88 - 100 * ((1.01 * 1.02 * 1.02 - 1) - (1.005 * 1.005 - 1))) < 1e-10, "Summe der Haltezeit = Mehrrendite der Suche (Schluss/Eröffnung Ziel minus Index)")
ok(x[:5].sum() == 0 and x[8:].sum() == 0, "ausserhalb der Haltezeit null")
# 2 Abstand wie in der Suche: max(10, h)
x, g = b.tagesertrag(ocz, ccz, ocb, ccb, [5, 9, 15, 30], 3, 0.0)
ok(list(g) == [5, 15, 30], "Einstieg mit weniger als 10 Tagen Abstand ausgelassen")
# 3 kein Teilfenster am Rand, kein Fenster mit fehlendem Kurs
x, g = b.tagesertrag(ocz, ccz, ocb, ccb, [38], 3, 0.0); ok(len(g) == 0 and x.sum() == 0, "Haltezeit über das Ende hinaus: ausgelassen")
c2 = ccz.copy(); c2[7] = np.nan
x, g = b.tagesertrag(ocz, c2, ocb, ccb, [5], 3, 0.0); ok(len(g) == 0, "fehlender Kurs in der Haltezeit: ausgelassen")
# 4 Tests: klarer Effekt wird erkannt, kein Effekt nicht
rng = np.random.default_rng(1)
stark = np.zeros(1200); stark[::40] = 2.0 + rng.normal(0, 0.5, 30)
k, B, m = b.blocktest(stark, np.random.default_rng(2)); ok(b.p_wert(k, B) < 0.01 and B == b.ZIEHUNGEN, "Blocktest erkennt klaren Effekt")
k, B, m = b.vorzeichentest(stark, np.random.default_rng(2)); ok(b.p_wert(k, B) < 0.01, "Vorzeichentest erkennt klaren Effekt")
null = np.zeros(1200); null[::40] = rng.normal(0, 2.0, 30)
ok(b.p_wert(*b.blocktest(null, np.random.default_rng(3))[:2]) > 0.01, "Blocktest: kein Effekt, kein kleiner p-Wert")
ok(b.p_wert(*b.vorzeichentest(null, np.random.default_rng(3))[:2]) > 0.01, "Vorzeichentest: kein Effekt, kein kleiner p-Wert")
# 5 negativer Ertrag wird nie bestätigt
neg = -stark
ok(b.p_wert(*b.blocktest(neg, np.random.default_rng(4))[:2]) > 0.9, "Blocktest: negativer Ertrag")
ok(b.p_wert(*b.vorzeichentest(neg, np.random.default_rng(4))[:2]) > 0.9, "Vorzeichentest: negativer Ertrag")
# 6 Plus-eins-Rechnung, nie null; gleicher Startwert gibt gleiches Ergebnis
ok(b.p_wert(0, 10000) == 1 / 10001 and b.p_wert(None, None) == 1.0, "p-Wert mit Plus-eins-Rechnung; nicht prüfbar = 1")
ok(b.blocktest(stark, np.random.default_rng(7)) == b.blocktest(stark, np.random.default_rng(7)), "reproduzierbar")
# 7 keine Ereignisse: nicht bestätigt
ok(b.p_wert(*b.vorzeichentest(np.zeros(1200), np.random.default_rng(1))[:2]) > 0.99, "keine Ereignisse: p nahe 1")
ok(abs(b.jahresertrag(np.full(252, 0.01)) - 2.52) < 1e-9, "Jahresertrag")
# 8 ungültige Zahlen: Abbruch statt kleiner p-Wert (Astra-Gutachten 6, G6-08)
xn = np.zeros(1235); xn[0] = np.nan
for f in (b.blocktest, b.vorzeichentest):
    try:
        f(xn, np.random.default_rng(1)); ok(False, "NaN muss abbrechen")
    except ValueError:
        ok(True, f"{f.__name__}: NaN bricht ab")
# 9 Ersatzindex als Korb wie in der Suche: 55% ganze SPY-Rendite plus 45% ganze EFA-Rendite (G6-05)
z2 = np.zeros(12); spy_oc = np.zeros(12); spy_cc = np.zeros(12); efa_oc = np.zeros(12); efa_cc = np.zeros(12)
spy_oc[0] = 0.10; spy_cc[1] = -0.10; efa_oc[0] = -0.10; efa_cc[1] = 0.10
x, g = b.tagesertrag(z2, z2, [[(0.55, spy_oc, spy_cc), (0.45, efa_oc, efa_cc)]], None, [0], 2, 0.0)
ok(abs(x[:2].sum() - 1.0) < 1e-12, "Ersatzindex: beide Anlagen enden bei -1%, Mehrertrag des flachen Ziels +1 pp")
nanb = np.full(12, np.nan)
x, g = b.tagesertrag(z2, z2, [[(1.0, nanb, nanb)], [(0.55, spy_oc, spy_cc), (0.45, efa_oc, efa_cc)]], None, [0], 2, 0.0)
ok(abs(x[:2].sum() - 1.0) < 1e-12 and len(g) == 1, "erster Korb ohne Kurse: zweiter Korb gilt")
# 10 Abnahmegrenzen (Astra-Gutachten 6, Frage 3) und diskrete Schwelle (G6-03)
ok((b.k_max(7300, 0.05), b.k_max(7300, 0.025), b.k_max(7300, 0.05 / 3)) == (334, 160, 103), "höchstens 334 / 160 / 103 Fehlalarme in 7300 Welten")
pn = np.r_[np.full(149, 80 / 2001), np.full(20, 90 / 2001), np.full(2831, 1000 / 2001)]
c = b.schwelle_diskret(pn, 0.05, k_erlaubt=150)
ok(abs(c - 80 / 2001) < 1e-15 and int((pn <= c).sum()) == 149, "Bindungen: Schwelle 80/2001 verwirft 149, nicht 169")
ok(b.schwelle_diskret(np.full(100, 0.001), 0.05, k_erlaubt=3) == 0.0, "zu viele Welten auf der kleinsten Stufe: Test verwirft nie")
ok(b.urteil(0.001, 0.05, 9) == "unentschieden" and b.urteil(0.001, 0.05, 10) == "bestätigt" and b.urteil(0.2, 0.05, 30) == "nicht bestätigt", "Urteil mit Mindestzahl 10")
print("alle Tests bestanden")
