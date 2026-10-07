"""Tests für vorwaerts.py. Aufruf: python test_vorwaerts.py            (reine Funktionen)
PS_VORWAERTS_DATENTEST=1 python test_vorwaerts.py <BASIS>            (zusätzlich mit Daten, nur Discovery bis 31.12.2020)"""
import datetime, json, os, shutil, sys, tempfile
import vorwaerts as v
GESPERRT_AUSGELIEFERT = v.GESPERRT
v.GESPERRT = False        # die übrigen Tests prüfen die Logik hinter der Sperre


def test_gesperrt():
    """V3.15: Im ausgelieferten Zustand ist das Register gesperrt; jede Registrierung wird als Fehler gemeldet, nichts wird geschrieben."""
    assert GESPERRT_AUSGELIEFERT is True
    d = tempfile.mkdtemp()
    try:
        r, l = os.path.join(d, "vorwaerts"), os.path.join(d, "log"); os.makedirs(r)
        v.GESPERRT = True
        json.dump(reg(kennung="T1"), open(os.path.join(r, "T1.json"), "w"))
        z = v.lauf(r, l, datetime.date(2019, 7, 1), "2019-07-01T06:00:00Z")
        assert z["fehler"] and "gesperrt" in z["fehler"][0]["fehler"][0] and not os.path.exists(l)
    finally:
        v.GESPERRT = False; shutil.rmtree(d)


def reg(**kw):
    d = dict(kennung="T1", art="strang", registriert="2019-01-02", regeln=[dict(indikator="X_d5", art="hoch", ziel="xlu", h=5)],
             kosten_pp=0.88, niveau=0.05, test=dict(name="blocktest", block=20, ziehungen=10000, startwert=1), letzter_einstieg="2020-06-30",
             schlusstag="2020-09-30", min_ereignisse=10, vorpruefung=dict(jahresschwankung_pp=3.0, dauer_jahre=2.0), freigabe="Test", mechanismus="Test")
    d.update(kw); return d


def test_registrierung():
    assert v.pruefe_registrierung(reg()) == []
    assert v.pruefe_registrierung({"kennung": "x"})                                    # Felder fehlen
    assert v.pruefe_registrierung(reg(regeln=[]))
    assert v.pruefe_registrierung(reg(regeln=[dict(indikator="a", art="hoch", ziel="xlu", h=60)]))      # 60 nur Typ K
    assert v.pruefe_registrierung(reg(art="typ_k", regeln=[dict(indikator="a", art="hoch", ziel="xlu", h=60)], letzter_einstieg="2020-05-01")) == []
    assert v.pruefe_registrierung(reg(regeln=[dict(indikator="a", art="hoch", ziel="xlu", h=5), dict(indikator="b", art="tief", ziel="xlu", h=5)]))
    assert v.pruefe_registrierung(reg(letzter_einstieg="2020-09-28"))                  # Haltefenster läuft nicht aus
    assert v.pruefe_registrierung(reg(schlusstag="2025-01-01", letzter_einstieg="2024-06-01"))          # über 5 Jahre
    assert v.pruefe_registrierung(reg(art="uebung", schlusstag="2025-01-01", letzter_einstieg="2024-06-01")) == []
    assert v.pruefe_registrierung(reg(test=dict(name="blocktest", block=20, ziehungen=2000, startwert=1)))
    assert v.pruefe_registrierung(reg(niveau=0.1)) and v.pruefe_registrierung(reg(min_ereignisse=5))


def test_dauer():
    assert v.dauer_jahre(3.0) == 2.0 and v.dauer_jahre(4.0) == 3.5 and v.dauer_jahre(5.0) == 5.5      # 1.94, 3.44, 5.38 aufgerundet
    assert v.dauer_jahre(8.0) > v.MAX_JAHRE


def test_fortschreiben_und_wertbar():
    t1 = "2019-03-01T06:00:00Z"; t2 = "2019-03-05T06:00:00Z"; t3 = "2019-03-20T06:00:00Z"
    z1 = v.fortschreiben([], {"2019-02-27": (1.5, None)}, None, t1)
    assert len(z1) == 1 and z1[0]["ereignis"] == "ausloeser" and z1[0]["kennzeichen"] is None
    z2 = v.fortschreiben(z1, {"2019-02-27": (1.5, "2019-03-04")}, "2019-02-28", t2)       # Einstiegstag wird bekannt
    assert [z["ereignis"] for z in z2] == ["einstieg_bestimmt"]
    assert v.fortschreiben(z1 + z2, {"2019-02-27": (1.5, "2019-03-04")}, "2019-03-04", t2) == []          # nichts Neues
    z3 = v.fortschreiben(z1 + z2, {"2019-02-27": (1.5, "2019-03-04"), "2019-03-01": (2.0, "2019-03-06")}, "2019-03-15", t3)
    assert len(z3) == 1 and z3[0]["kennzeichen"] == "nachlieferung"                       # Wert lag schon vor, Auslöser kam erst jetzt
    z4 = v.fortschreiben(z1 + z2 + z3, {"2019-03-01": (2.0, "2019-03-06")}, "2019-03-15", t3)
    assert [z["ereignis"] for z in z4] == ["entfallen"] and z4[0]["beobachtung"] == "2019-02-27"
    assert v.fortschreiben(z1 + z2 + z3 + z4, {"2019-03-01": (2.0, "2019-03-06")}, "2019-03-15", t3) == []   # entfallen nur einmal
    gut, verpasst = v.wertbare(z1 + z2 + z3 + z4)
    assert gut == ["2019-03-04"] and verpasst == 1          # rechtzeitig erkannt zählt (auch wenn später entfallen); Nachlieferung ist verpasst
    spaet = [dict(ereignis="ausloeser", beobachtung="2019-04-01", wert=1.0, einstieg="2019-04-02", erkannt_utc="2019-04-02T14:00:00Z", kennzeichen=None)]
    assert v.wertbare(spaet) == ([], 1)                     # erst nach der Eröffnung erkannt
    assert v.erkannt_rechtzeitig("2019-04-02T13:29:59Z", "2019-04-02") and not v.erkannt_rechtzeitig("2019-04-02T13:30:00Z", "2019-04-02")
    offen = [dict(ereignis="ausloeser", beobachtung="2019-04-01", wert=1.0, einstieg=None, erkannt_utc="2019-04-02T06:00:00Z", kennzeichen=None)]
    assert v.wertbare(offen) == ([], 0)


def test_lauf_ohne_daten():
    d = tempfile.mkdtemp()
    try:
        r, l = os.path.join(d, "vorwaerts"), os.path.join(d, "log"); os.makedirs(r)
        z = v.lauf(r, l, datetime.date(2026, 10, 6), "2026-10-06T06:00:00Z")
        assert z["registrierungen"] == 0 and z["neue_zeilen"] == 0 and not z["fehler"]     # leeres Register: kein Motor nötig
        assert not os.path.exists(l)                                                     # und nichts geschrieben
        x = reg(kennung="ALT", registriert="2019-01-02", letzter_einstieg="2019-06-28", schlusstag="2019-09-30")
        json.dump(x, open(os.path.join(r, "ALT.json"), "w"))
        z = v.lauf(r, l, datetime.date(2026, 10, 6), "2026-10-06T06:00:00Z")               # Schlusstag vorbei: nicht aktiv
        assert z["aktiv"] == [] and not z["fehler"] and z["straenge_je_registriert"] == 1
        x["mechanismus"] = "geändert"; json.dump(x, open(os.path.join(r, "ALT.json"), "w"))
        z = v.lauf(r, l, datetime.date(2026, 10, 6), "2026-10-06T07:00:00Z")
        assert z["fehler"] and "VERÄNDERT" in z["fehler"][0]["fehler"][0]
        json.dump(reg(kennung="B"), open(os.path.join(r, "falsch.json"), "w"))
        z = v.lauf(r, l, datetime.date(2026, 10, 6), "2026-10-06T08:00:00Z")
        assert any("Dateiname" in " ".join(f["fehler"]) for f in z["fehler"])
        assert len(v.lesen_jsonl(os.path.join(l, "laeufe.jsonl"))) == 3
    finally:
        shutil.rmtree(d)


def test_mit_daten():
    """Nur Discovery. (1) Siegel: keine Kurse nach dem Stichtag. (2) Echtzeit-Gleichheit: Auslöser bis zum Tag S sind
    dieselben, ob die Signalreihen bis S oder bis Ende 2020 reichen. (3) Gleichheit mit der Suche. (4) Ein gedachter
    Strang über 2019/2020 in drei Läufen; Logbuch nur verlängert; gewertete Einstiege wie in der Ereignistabelle."""
    import numpy as np, pandas as pd
    import suchmaschine as sm
    S = "2019-12-31"
    voll = v.motor_laden("2020-12-31"); kurz = v.motor_laden(S); heute_m = v.motor_laden(str(datetime.date.today()))
    for m in (voll, kurz, heute_m):
        assert all(d.index.max() <= m.STICHTAG for d in m.kurse.values()) and m.acwi.index.max() <= m.STICHTAG
    assert len(heute_m.KAL) == len(sm.KAL) and set(voll.ind) == set(sm.ind)
    namen = sorted(n for n in voll.ind if n in kurz.ind); rng = np.random.default_rng(3); stich = rng.choice(len(namen), 400, replace=False)
    gepr, abw, rand = 0, [], []
    for i in stich:
        n = namen[i]
        for art in (("hoch",) if n in voll.EREIGNIS else ("hoch", "tief", "sprung_auf", "sprung_ab")):
            a = sm.ereignisse(sm.ind[n][0], art, n in sm.EREIGNIS); b = voll.ereignisse(voll.ind[n][0], art, n in voll.EREIGNIS)
            assert a.equals(b), n                                                      # (3) private Kopie = Suche
            c = kurz.ereignisse(kurz.ind[n][0], art, n in kurz.EREIGNIS)
            if not b[b < pd.Timestamp(S)].equals(c[c < pd.Timestamp(S)]):
                abw.append((n, art))                                                   # vor dem letzten Tag: muss gleich sein
            elif not b[b <= pd.Timestamp(S)].equals(c):
                rand.append(n)                                                         # nur der letzte, unvollständige Tag
            gepr += 1
    print(f"   Echtzeit-Gleichheit: {gepr} Paare geprüft, abweichend {len(abw)} {abw[:5]}; nur am letzten Tag abweichend {len(rand)}")
    assert not abw
    assert all(n.startswith(v.UNTERTAEGIG) for n in rand), rand                        # nur Reihen aus Stundenwerten; dafür zählt der letzte Tag nie
    # (4) gedachter Strang
    tab = {(e["indikator"], e["art"]): e for e in sm.ereignis_tabelle() if e["fam"] == "S"}
    kand = [(k, e) for k, e in sorted(tab.items()) if ((sm.KAL[e["pos"][e["pos"] < len(sm.KAL)]] > "2019-03-01") & (sm.KAL[e["pos"][e["pos"] < len(sm.KAL)]] < "2020-06-01")).sum() >= 6]
    (ind, art), e = kand[len(kand) // 2]
    d = tempfile.mkdtemp()
    try:
        r, l = os.path.join(d, "vorwaerts"), os.path.join(d, "log"); os.makedirs(r)
        x = reg(kennung="GEDACHT", registriert="2019-01-02", regeln=[dict(indikator=ind, art=art, ziel="xlu", h=5)], letzter_einstieg="2020-06-30", schlusstag="2020-09-30")
        json.dump(x, open(os.path.join(r, "GEDACHT.json"), "w"))
        n_alt = 0
        for tag in ("2019-07-01", "2020-01-02", "2020-07-15"):
            z = v.lauf(r, l, datetime.date.fromisoformat(tag), tag + "T06:00:00Z")
            assert not z["fehler"], z["fehler"]
            log = v.lesen_jsonl(os.path.join(l, "logbuch.jsonl")); assert len(log) >= n_alt; n_alt = len(log)
            assert all(q["beobachtung"] > "2019-01-02" for q in log)                    # nichts vor der Registrierung
        gut, verpasst = v.wertbare([q for q in log if q["ereignis"] != "ausfall"])
        erste = {}
        for q in log:
            erste.setdefault(q["beobachtung"], q)
        tage = sm.ereignisse(sm.ind[ind][0], art, ind in sm.EREIGNIS); tage = tage[tage > "2019-01-02"]
        pos = sm.einstieg(sm.KAL, tage, sm.ind[ind][1]); soll = sorted({str(sm.KAL[p].date()) for p in pos if 0 <= p < len(sm.KAL) and sm.KAL[p] <= pd.Timestamp("2020-06-30")})
        alle = sorted({q["einstieg"] for q in log if q.get("einstieg")})
        assert alle == soll, (alle[:3], soll[:3])                                      # Einstiegstage wie in der Suche
        print(f"   gedachter Strang {ind} {art}: {len(soll)} Einstiege, gewertet {len(gut)}, verpasst {verpasst} (drei Läufe im Halbjahresabstand)")
    finally:
        shutil.rmtree(d)


if __name__ == "__main__":
    mit = os.environ.get("PS_VORWAERTS_DATENTEST") == "1"
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and (mit or name != "test_mit_daten"):
            fn(); print("ok", name)
    print("alle Tests bestanden" + ("" if mit else " (ohne Datentest)"))
