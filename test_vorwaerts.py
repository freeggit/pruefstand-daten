"""Tests für vorwaerts.py (V3.15; Gegenbeispiele aus den Astra-Gutachten 7, 8 und 9: T8-01 bis T8-18, T9-01 bis T9-18).
Aufruf: python test_vorwaerts.py                                     (Logik, Journale, Abbrüche, echte Git-Historie)
PS_VORWAERTS_DATENTEST=1 python test_vorwaerts.py <BASIS>            (zusätzlich mit Daten, nur Discovery bis 31.12.2020)
Kein Test hängt vom ausgelieferten Freigabemodus ab: Jeder Test legt seine eigene freigabe.json an (G8-11)."""
import contextlib, datetime, json, os, shutil, subprocess, sys, tempfile
import vorwaerts as v
D = datetime.date; T = datetime.datetime
CC = "a" * 40; AUF = "c" * 40
DS = "main=" + "1" * 40 + ";neu=" + "2" * 40 + ";energie=" + "3" * 40
DS2 = "main=" + "9" * 40 + ";neu=" + "2" * 40 + ";energie=" + "3" * 40


def reg(**kw):
    d = dict(kennung="T1", art="strang", registriert="2026-10-12", regeln=[dict(indikator="X_d5", art="hoch", ziel="xlu", h=5)],
             kosten_pp=0.88, letzter_einstieg="2028-09-15", schlusstag="2028-10-13", min_ereignisse=10,
             vorpruefung=dict(jahresschwankung_pp=3.0, beleg="Lauf L-Test, auswahl_e27.json"), code_commit=CC, mechanismus="Test")
    d.update(kw); d.setdefault("freigabe", dict(wortlaut="Test: freigeben", datum=d["registriert"], kennung=d["kennung"]))
    return d


class Stub(v.Umgebung):
    """Umgebung ohne Git und ohne Daten. Uhr, Aufnahme, Historie, Veröffentlichung und Kursdateien werden vorgegeben;
    «pruefe», «buche» und «schliesse» rechnet der Code dieses Standes, «finde» ist vorgegeben."""
    def __init__(self, jetzt=T(2026, 10, 12, 10, 0), finde=None, werte=None):
        self.jetzt, self.folge, self.f, self.w, self.rufe_n = jetzt, [], finde or {}, werte, 0
        self.daten_dir = "/nicht/vorhanden"; self.aufn = {}; self.hist = {}; self.kein_vorfahr = set(); self.pub = None
        self.daten_fehler = []; self.mf = {"acwi": "m1", "xlu": "m2"}; self.bis = "2099-12-31"; self.modi = []
        self.marker_hist = []; self.bekannt = False; self.struktur = {}; self.finde_fehler = None; self.ver = dict(python="3.12.1", numpy="1", pandas="2")
    def marker_historie(self, ordner): return self.marker_hist
    def journal_bekannt(self, pfad): return self.bekannt
    def veroeffentlicht_stand(self, logdir): return False
    def uhr(self): return self.folge.pop(0) if self.folge else self.jetzt
    def aufnahme(self, pfad): return self.aufn.get(os.path.basename(pfad), (AUF, T(2026, 10, 12, 9, 0)))
    def geaendert_seit(self, pfad, commit): return self.hist.get(os.path.basename(pfad), [])
    def ist_vorfahr(self, a, b): return a not in self.kein_vorfahr
    def code_dir(self, commit): return None if commit.startswith("f") else "/code/" + commit
    def rufe(self, code_dir, modus, e):
        self.rufe_n += 1; self.modi.append(modus)
        e = json.loads(json.dumps(e))                                                  # wie über die Prozessgrenze
        if modus == "pruefe":
            return dict(fehler_liste=v.pruefe_sicher(e["reg"], e["beginn"]), protokoll=v.PROTOKOLL)
        if modus == "finde":
            if self.finde_fehler:
                return dict(fehler=self.finde_fehler)
            g = self.f.get(e["reg"]["kennung"], [{} for _ in e["reg"]["regeln"]])
            return dict(regeln=[dict(gefunden=x, reihe_bis=None) for x in g], struktur=list(self.struktur.get(e["reg"]["kennung"], [])),
                        kalender=[str(t) for t in v.nyse_handelstage(v._tag(e["beginn"]), D(2029, 1, 31))], protokoll=v.PROTOKOLL)
        if modus == "buche":
            return v.buche(e["reg"], e["alt"], e["gefunden"], e["kalender"], e["reihe_bis_vorher"], e["erkannt_utc"])
        if modus == "bedarf":
            return v.bedarf(e["auftraege"], e["sonder"])
        if self.w is None:
            return v.schliesse(e["reg"], e["beginn"], e["auftraege"], e["daten_dir"], e["sonder"])
        return self.w(e) if callable(self.w) else self.w
    def daten_pruefen(self, ds): return list(self.daten_fehler)
    def manifest(self, namen): return {n: self.mf.get(n) for n in sorted(set(namen))}
    def kurse_bis(self, name="acwi"): return self.bis.get(name) if isinstance(self.bis, dict) else self.bis
    def versionen(self): return dict(self.ver)


def ordner(modus="offen"):
    d = tempfile.mkdtemp(); r, l = os.path.join(d, "vorwaerts"), os.path.join(d, "log"); os.makedirs(r)
    if modus:
        json.dump(dict(modus=modus, freigabe="Test", seit="2026-10-12"), open(os.path.join(r, v.FREIGABE), "w"))
    return d, r, l


def lege(r, d):
    json.dump(d, open(os.path.join(r, d["kennung"] + ".json"), "w"))


def L(r, l, u, ds=None, nach=2):
    """Ein Lauf und danach, wie im Betrieb, der Vermerk der Veröffentlichung («nach» Minuten nach der letzten Uhrzeit)."""
    z = v.lauf(r, l, DS if ds is None else ds, u)
    if os.path.isdir(l):
        v.vermerken(l, v._fmt(u.jetzt + datetime.timedelta(minutes=nach)))
    return z


def status(l, k):
    return v.zustand(v.journal_lesen(os.path.join(l, "status.jsonl"))[0])["straenge"][k]["status"]


def abbruch(fn, teil):
    try:
        fn()
    except v.Abbruch as e:
        assert teil in str(e), (teil, str(e)); return str(e)
    raise AssertionError(f"kein Abbruch mit «{teil}»")


@contextlib.contextmanager
def ersetzt(name, neu):
    alt = getattr(v, name); setattr(v, name, neu)
    try:
        yield alt
    finally:
        setattr(v, name, alt)


# ---------------------------------------------------------------------------------------------- reine Funktionen
def test_kalender():
    f = v.nyse_feiertage(2026)
    assert {D(2026, 1, 1), D(2026, 1, 19), D(2026, 2, 16), D(2026, 4, 3), D(2026, 5, 25), D(2026, 6, 19), D(2026, 7, 3), D(2026, 9, 7), D(2026, 11, 26), D(2026, 12, 25)} == f
    assert len(v.nyse_handelstage(D(2026, 1, 1), D(2026, 12, 31))) == 251
    assert D(2021, 12, 31) in v.nyse_handelstage(D(2021, 12, 27), D(2022, 1, 5)) and D(2022, 1, 3) in v.nyse_handelstage(D(2021, 12, 27), D(2022, 1, 5))   # Neujahr 2022 am Samstag: nicht vorgeholt
    assert D(2021, 6, 18) in v.nyse_handelstage(D(2021, 6, 14), D(2021, 6, 21)) and D(2022, 6, 20) in v.nyse_feiertage(2022)                          # Juneteenth erst ab 2022
    assert v.ostern(2027) == D(2027, 3, 28) and v.ostern(2030) == D(2030, 4, 21)


def test_registrierung():
    b = D(2026, 10, 12); P = v.pruefe_registrierung
    assert P(reg(), b) == []
    assert P({"kennung": "x"}, b) and P(reg(regeln=[]), b)
    assert P(reg(regeln=[dict(indikator="a", art="hoch", ziel="xlu", h=60)]), b)
    assert P(reg(regeln=[dict(indikator="a", art="hoch", ziel="xlu", h=5), dict(indikator="b", art="tief", ziel="xlu", h=5)]), b)
    assert P(reg(min_ereignisse=5), b)
    f = P(reg(vorpruefung=dict(jahresschwankung_pp=8.0, beleg="x")), b); assert f and "mehr als" in f[0]              # sigma 8: 14 Jahre, keine Registrierung
    f = P(reg(vorpruefung=dict(jahresschwankung_pp=4.0, beleg="x")), b); assert f and "kürzer" in f[0]                # sigma 4 braucht 3.5 Jahre, eingetragen 2
    assert P(reg(vorpruefung={}), b)
    f = P(reg(vorpruefung=dict(jahresschwankung_pp=3.0)), b); assert f and "beleg" in f[0]                           # G8-10: Beleg der Schwankung
    f = P(reg(registriert="2026-10-01"), b); assert f and "passt nicht zum Beginn" in f[0]                           # rückdatiert
    f = P(reg(registriert="2026-10-13"), b); assert any("passt nicht zum Beginn" in x for x in f)                           # nach dem Beginn
    assert P(reg(letzter_einstieg="2028-09-16"), b)                                                                   # Samstag
    assert P(reg(letzter_einstieg="2028-10-09"), b)                                                                   # Haltefenster läuft nicht aus (Feiertage zählen nicht)
    k = reg(art="typ_k", regeln=[dict(indikator="a", art="hoch", ziel="xlu", h=250)], schlusstag="2030-10-11", letzter_einstieg="2029-10-22", vorpruefung=dict(jahresschwankung_pp=4.0, beleg="x"))
    f = P(k, b); assert f and "Haltefenster" in f[0]                                                                  # 250 Handelstage brauchen mehr als ein Kalenderjahr
    k["letzter_einstieg"] = "2029-10-01"; assert P(k, b) == []
    assert P(reg(art="uebung", vorpruefung={}, schlusstag="2026-12-31", letzter_einstieg="2026-11-30"), b) == []
    assert v.dauer_jahre(3.0) == 2.0 and v.dauer_jahre(4.0) == 3.5 and v.dauer_jahre(5.0) == 5.5
    # Tagesregel der Dauer (G8-10): 2 Jahre = 731 Tage, Toleranz genau 3 Tage Vorlauf
    assert P(reg(schlusstag="2028-10-10", letzter_einstieg="2028-09-15"), b) == []                                     # 729 Tage
    f = P(reg(schlusstag="2028-10-06", letzter_einstieg="2028-09-15"), b); assert f and "kürzer" in f[0]              # 725 Tage
    # G8-03 / T8-05: nur vollständige Commit-Kennungen
    for c in ("refs/remotes/origin/main", "main", "abcdef1", CC[:39], CC.upper(), CC + "x", None, 7):
        f = P(reg(code_commit=c), b); assert f and "vollständige Commit-Kennung" in f[0], c
    # G8-09 / G8-10 / T8-15: Freigabe, Typen, Endlichkeit; nie ein Abbruch
    FR = dict(wortlaut="Reto: freigeben", datum="2026-10-12", kennung="T1")
    for bad in (dict(freigabe=None), dict(freigabe=""), dict(freigabe="Strang T1 freigeben"), dict(freigabe=dict(FR, kennung="T10")),     # T9-15: Freigabe für T10 gilt nicht für T1
                dict(freigabe={k: w for k, w in FR.items() if k != "datum"}), dict(freigabe=dict(FR, datum="12.10.2026")), dict(freigabe=dict(FR, datum="2026-10-13")),
                dict(freigabe=dict(FR, wortlaut="")), dict(freigabe=dict(FR, mehr=1)), dict(mechanismus=None), dict(kosten_pp=float("inf")),
                dict(kosten_pp=1e309), dict(kosten_pp=True), dict(kosten_pp="0.88"), dict(kosten_pp=9.0), dict(min_ereignisse=True),
                dict(vorpruefung=dict(jahresschwankung_pp=float("nan"), beleg="x")), dict(vorpruefung=dict(jahresschwankung_pp=float("inf"), beleg="x")),
                dict(regeln=[dict(indikator="a", art="hoch", ziel="xlu", h=True)]), dict(regeln=[dict(indikator="a|b", art="hoch", ziel="xlu", h=5)]),
                dict(regeln="x"), dict(registriert=20261012), dict(schlusstag=None), dict(kennung="../x"), dict(vorgaenger="T0"), dict(art=["strang"])):
        assert v.pruefe_sicher(reg(**bad), "2026-10-12"), bad
    for wurzel in (None, [], "x", 3, [reg()]):
        assert v.pruefe_sicher(wurzel, "2026-10-12")
    assert v.pruefe_sicher(reg(), "kein Datum")


def test_schluessel_und_stand():
    assert v.kanon("X_d5|hoch|xlu|5") == v.kanon("S|X_d5|hoch|xlu|5") == v.kanon("V|V20261004-03|X_d5|hoch|xlu|5") == "X_d5|hoch|xlu|5"
    for bad in ("", "S|X|hoch|xlu", "X|hoch|xlu|5|6|7|8", "X|rauf|xlu|5", "X|hoch|xlu|7", "X|hoch||5", None, 5, "W|a|X|hoch|xlu|5"):
        try:
            v.kanon(bad); assert False, bad
        except ValueError:
            pass
    assert v.stand_lesen(DS) == dict(main="1" * 40, neu="2" * 40, energie="3" * 40)
    for bad in ("", "main=a", "main=;neu=;energie=", DS.replace("1" * 40, "1" * 12), DS + ";x=1", None):
        assert v.stand_lesen(bad) is None, bad
    m = v.oeffnungsmarker(dict(finalist=dict(regeln=["S|X_d5|hoch|xlf|5", "V|V20261004-03|Y|tief|gld|20"])), "2026-11-01T07:00:00Z", "Reto: öffnen")
    assert m["regeln"] == ["X_d5|hoch|xlf|5", "Y|tief|gld|20"] and v.marker_lesen(json.dumps(m)) == m["regeln"]
    for bad in ("{}", "[]", "null", '{"regeln": []}', '{"regeln": ["X|hoch|xlf|5"]}', json.dumps(dict(m, regeln=["unsinn"])), "{kaputt",
                json.dumps(dict(m, geoeffnet_utc="irgendwann")), json.dumps(dict(m, geoeffnet_utc=None))):                 # T9-02: Zeit muss lesbar sein
        abbruch(lambda: v.marker_lesen(bad), "ungültig")


KAL = v.nyse_handelstage(D(2026, 10, 1), D(2027, 6, 30)); R5 = dict(indikator="X", art="hoch", ziel="xlu", h=5)


def test_entscheid_und_handelsbuch():
    # rechtzeitig, verspätet, nach dem letzten Einstieg, Sperrfrist
    assert v.entscheid("2026-10-12", "2026-10-14", "2026-10-13T06:00:00Z", [], R5, "2027-05-28", KAL) == ("auftrag", None)
    assert v.entscheid("2026-10-12", "2026-10-14", "2026-10-14T13:29:59Z", [], R5, "2027-05-28", KAL)[0] == "auftrag"
    assert v.entscheid("2026-10-12", "2026-10-14", "2026-10-14T13:30:00Z", [], R5, "2027-05-28", KAL) == ("kein_auftrag", "verspätet erkannt")
    assert v.entscheid("2027-05-27", "2027-06-01", "2027-05-28T06:00:00Z", [], R5, "2027-05-28", KAL)[1].startswith("nach dem letzten")
    assert v.entscheid("2026-10-19", "2026-10-21", "2026-10-20T06:00:00Z", ["2026-10-14"], R5, "2027-05-28", KAL)[1].startswith("Sperrfrist")
    assert v.entscheid("2026-10-27", "2026-10-28", "2026-10-27T20:00:00Z", ["2026-10-14"], R5, "2027-05-28", KAL)[0] == "auftrag"     # 10 Handelstage später
    assert v.entscheid("2026-10-12", None, "2026-10-13T06:00:00Z", [], R5, "2027-05-28", KAL)[0] == "kein_auftrag"
    assert v.entscheid("2027-06-25", "2027-06-29", "2027-06-28T06:00:00Z", [], R5, "2027-06-30", KAL)[1].startswith("Haltefenster")    # Kalender reicht nicht für 5 Sitzungen
    # Astra 7: rechtzeitige Nachlieferung mit künftigem Einstieg wird gehandelt; Revision und Verspätung sind getrennte Merkmale
    z1 = v.fortschreiben([], {"2026-10-12": (1.5, "2026-10-16")}, R5, "2027-05-28", KAL, "2026-10-13", "2026-10-14T06:00:00Z")
    assert len(z1) == 1 and z1[0]["ereignis"] == "auftrag" and z1[0]["nachlieferung"] is True
    z2 = v.fortschreiben(z1, {"2026-10-12": (1.7, "2026-10-16")}, R5, "2027-05-28", KAL, "2026-10-14", "2026-10-15T06:00:00Z")
    assert [(z["ereignis"], z["grund"]) for z in z2] == [("revision", "Wert geändert")] and z2[0]["wert_vorher"] == 1.5
    assert v.fortschreiben(z1 + z2, {"2026-10-12": (1.7, "2026-10-16")}, R5, "2027-05-28", KAL, "2026-10-15", "2026-10-16T06:00:00Z") == []
    z3 = v.fortschreiben(z1 + z2, {}, R5, "2027-05-28", KAL, "2026-10-15", "2026-10-19T06:00:00Z")
    assert [(z["ereignis"], z["grund"]) for z in z3] == [("revision", "entfallen")]
    assert v.fortschreiben(z1 + z2 + z3, {}, R5, "2027-05-28", KAL, "2026-10-15", "2026-10-20T06:00:00Z") == []
    z4 = v.fortschreiben(z1 + z2 + z3, {"2026-10-12": (1.7, "2026-10-16")}, R5, "2027-05-28", KAL, "2026-10-15", "2026-10-21T06:00:00Z")
    assert [(z["ereignis"], z["grund"]) for z in z4] == [("revision", "wieder da")]
    assert sum(z["ereignis"] == "auftrag" for z in z1 + z2 + z3 + z4) == 1
    z5 = v.fortschreiben([], {"2026-11-02": (2.0, "2026-11-04"), "2026-11-03": (2.1, "2026-11-05")}, R5, "2027-05-28", KAL, None, "2026-11-03T20:00:00Z")
    assert [z["ereignis"] for z in z5] == ["auftrag", "kein_auftrag"]
    z6 = v.fortschreiben(z5, {"2026-11-02": (2.0, "2026-11-06"), "2026-11-03": (2.1, "2026-11-05")}, R5, "2027-05-28", KAL, None, "2026-11-10T06:00:00Z")
    assert len(z6) == 1 and z6[0]["grund"].startswith("Einstiegstag") and z6[0]["einstieg_vorher"] == "2026-11-04"
    # buche: vollständiger Auftrag mit den erwarteten Sitzungen (G8-02); Thanksgiving 26.11.2026 ist keine Sitzung
    b = v.buche(reg(), [], [dict(gefunden={"2026-11-20": [1.5, "2026-11-23"]}, reihe_bis=None)], [str(t) for t in KAL], [None], "2026-11-21T06:00:00Z")["zeilen"]
    assert b[0]["ereignis"] == "auftrag" and b[0]["sitzungen"] == ["2026-11-23", "2026-11-24", "2026-11-25", "2026-11-27", "2026-11-30"] and b[0]["ausstieg"] == "2026-11-30"
    assert b[0]["frist_utc"] == "2026-11-23T13:30:00Z" and b[0]["kosten_pp"] == 0.88 and b[0]["ziel"] == "xlu" and b[0]["regel"] == 0
    assert v.buche(reg(), [], [dict(gefunden=None, reihe_bis=None)], [str(t) for t in KAL], [None], "2026-11-21T06:00:00Z")["zeilen"][0]["ereignis"] == "ausfall"


def test_zeitnachweis():
    """G8-01 / G9-03 / T8-01 / T8-02 / T9-07 / T9-08: getrennte Zeiten; massgebend ist die Zeit NACH dem gelungenen Push;
    jeder Auftragsversuch löst die Sperrfrist aus (beschlossene Regel), auch wenn er später verfällt."""
    o = dict(frist_utc="2026-10-15T13:30:00Z", erkannt_utc="2026-10-15T13:29:00Z", gespeichert_utc="2026-10-15T13:29:30Z", veroeffentlicht_utc="2026-10-15T13:29:50Z")
    assert v.gueltig(o) == (True, None)
    for feld in ("erkannt_utc", "gespeichert_utc", "veroeffentlicht_utc"):
        assert v.gueltig(dict(o, **{feld: "2026-10-15T13:30:00Z"}))[0] is False and v.gueltig(dict(o, **{feld: None}))[0] is False
    assert v.gueltig({})[0] is False and v.gueltig(dict(o, frist_utc="unsinn"))[0] is False
    V = [dict(gepusht_utc="2026-10-14T04:20:00Z", zeilen=dict(handelsbuch=2)), dict(gepusht_utc="2026-10-15T04:20:00Z", zeilen=dict(handelsbuch=5)), dict(zeilen=None, gepusht_utc="x")]
    assert [v.veroeffentlicht_utc(V, n) for n in (0, 1, 2, 4, 5)] == ["2026-10-14T04:20:00Z", "2026-10-14T04:20:00Z", "2026-10-15T04:20:00Z", "2026-10-15T04:20:00Z", None]
    d, r, l = ordner()
    try:
        # T8-01: Lauf startet 13:29:50, die Signalrechnung ist erst 13:30:10 fertig
        u = Stub(T(2026, 10, 12, 10)); lege(r, reg()); assert L(r, l, u)["aktiv"] == ["T1"]
        g = {"2026-10-14": (1.5, "2026-10-15")}; u.f = {"T1": [g]}
        u.folge = [T(2026, 10, 15, 13, 29, 50), T(2026, 10, 15, 13, 30, 10), T(2026, 10, 15, 13, 30, 12)]; u.jetzt = T(2026, 10, 15, 13, 31); L(r, l, u)
        b = v.journal_lesen(os.path.join(l, "handelsbuch.jsonl"))[0][-1]
        assert (b["ereignis"], b["grund"]) == ("kein_auftrag", "verspätet erkannt")
        assert (b["lauf_start_utc"], b["erkannt_utc"], b["gespeichert_utc"]) == ("2026-10-15T13:29:50Z", "2026-10-15T13:30:10Z", "2026-10-15T13:30:12Z")
        # T8-02: vor der Frist erkannt, aber erst danach gespeichert: der Versuch steht als Auftrag im Buch und verfällt am Schluss
        g["2026-11-10"] = (1.6, "2026-11-12"); u.folge = [T(2026, 11, 12, 13, 29, 0), T(2026, 11, 12, 13, 29, 50), T(2026, 11, 12, 13, 30, 5)]; u.jetzt = T(2026, 11, 12, 13, 31); L(r, l, u)
        # T9-08: Am nächsten Handelstag käme B rechtzeitig. Der Versuch vom 12.11. sperrt ihn trotzdem (ausdrücklich protokolliert)
        g["2026-11-12"] = (1.65, "2026-11-13"); u.jetzt = T(2026, 11, 13, 4, 12); L(r, l, u)
        b = v.journal_lesen(os.path.join(l, "handelsbuch.jsonl"))[0][-1]; assert b["ereignis"] == "kein_auftrag" and b["grund"].startswith("Sperrfrist")
        # T9-07: Commit und Speicherung 13:21, der Push gelingt erst 13:31: der Vermerk trägt die Zeit nach dem Push, der Auftrag verfällt
        g["2026-12-01"] = (1.7, "2026-12-03"); u.jetzt = T(2026, 12, 3, 13, 21); L(r, l, u, nach=10)
        # Push gelingt gar nicht (kein Vermerk); der nächste Lauf trägt nach, was er im veröffentlichten Stand sieht: zu spät
        g["2026-12-21"] = (1.75, "2026-12-23"); u.jetzt = T(2026, 12, 22, 4, 12); v.lauf(r, l, DS, u)
        u.veroeffentlicht_stand = lambda logdir: True; u.jetzt = T(2026, 12, 23, 13, 40); v.lauf(r, l, DS, u); u.veroeffentlicht_stand = lambda logdir: False
        g["2027-01-11"] = (1.8, "2027-01-13"); u.jetzt = T(2027, 1, 12, 6); L(r, l, u)                                       # sauber
        b = v.journal_lesen(os.path.join(l, "handelsbuch.jsonl"))[0]
        assert [x["ereignis"] for x in b] == ["kein_auftrag", "auftrag", "kein_auftrag", "auftrag", "auftrag", "auftrag"]
        u.jetzt = T(2028, 10, 16, 6); u.w = None; u.daten_dir = os.path.join(d, "leer")
        e = v.lauf(r, l, DS, u, nur_schluss="T1")
        assert e["auftraege_n"] == 4 and e["verfallen_n"] == 3 and e["gueltig_n"] == 1
        gr = [x["grund"] for x in e["verfallen"]]
        assert "gespeichert_utc" in gr[0] and gr[1] == "nicht vor der Frist: veroeffentlicht_utc" and gr[2] == "nicht vor der Frist: veroeffentlicht_utc"
        res = json.load(open(os.path.join(l, "schluss_T1.reserviert.json")))
        assert [a["veroeffentlicht_utc"] for a in res["auftraege"]] == ["2026-11-12T13:33:00Z", "2026-12-03T13:31:00Z", "2026-12-23T13:40:00Z", "2027-01-12T06:02:00Z"]
        vm = v.journal_lesen(os.path.join(l, v.VERMERK))[0]; assert sum(x["art"].startswith("nachtrag") for x in vm) == 1
    finally:
        shutil.rmtree(d)


# ---------------------------------------------------------------------------------------------- Freigabe, Status, Schutzregeln
def test_freigabe():
    """G8-11 / T8-16: Der Freigabemodus liegt in einer eigenen Datei; «uebung» gibt echte Stränge nicht frei."""
    for inhalt in (None, "{kaputt", "[]", json.dumps(dict(modus="offen")), json.dumps(dict(modus="alles", freigabe="x")), json.dumps(dict(modus="offen", freigabe=""))):
        d, r, l = ordner(modus=None)
        try:
            if inhalt is not None:
                open(os.path.join(r, v.FREIGABE), "w").write(inhalt)
            lege(r, reg()); assert v.freigabemodus(r) == "gesperrt"
            z = v.lauf(r, l, DS, Stub())
            assert z["modus"] == "gesperrt" and z["fehler"] and "gesperrt" in z["fehler"][0]["fehler"][0] and not os.path.exists(l)      # nichts geschrieben
        finally:
            shutil.rmtree(d)
    d, r, l = ordner("uebung")
    try:
        u = Stub(); lege(r, reg()); lege(r, reg(kennung="U", art="uebung", vorpruefung={}, regeln=[dict(indikator="X_d5", art="hoch", ziel="xle", h=5)]))
        z = v.lauf(r, l, DS, u)
        assert z["aktiv"] == ["U"] and [f["kennung"] for f in z["fehler"]] == ["T1"] and "echte Stränge bleiben gesperrt" in z["fehler"][0]["fehler"][0]
        assert "T1" not in v.zustand(v.journal_lesen(os.path.join(l, "status.jsonl"))[0])["straenge"]                                     # weder aufgenommen noch abgewiesen
        # zurück auf gesperrt: der laufende Übungsstrang wird weitergeführt, Neues bleibt draussen
        os.remove(os.path.join(r, v.FREIGABE)); lege(r, reg(kennung="U2", art="uebung", vorpruefung={}, regeln=[dict(indikator="X_d5", art="hoch", ziel="xlf", h=5)]))
        u.f = {"U": [{"2026-10-13": (1.5, "2026-10-15")}]}; u.jetzt = T(2026, 10, 14, 6); z = v.lauf(r, l, DS, u)
        assert z["aktiv"] == ["U"] and z["neue_zeilen"] == 1 and z["modus"] == "gesperrt"
        # Übung endet ohne Auswertung
        u.jetzt = T(2028, 10, 16, 6); z = v.lauf(r, l, DS, u); assert status(l, "U") == "beendet_ohne_urteil" and not os.path.exists(os.path.join(l, "schluss_U.json"))
    finally:
        shutil.rmtree(d)


def test_status():
    d, r, l = ordner()
    try:
        u = Stub(finde={"T1": [{"2026-10-13": (1.5, "2026-10-15")}]})
        assert v.lauf(r, l, DS, u)["registrierungen"] == 0 and not os.path.exists(l)                                    # leeres Register: nichts geschrieben
        lege(r, reg()); abbruch(lambda: v.lauf(r, l, "main=;neu=;energie=", u), "Datenstand")                           # G8-05: leerer Datenstand ist keiner
        u.jetzt = T(2026, 10, 14, 6); z = v.lauf(r, l, DS, u)
        assert z["aktiv"] == ["T1"] and z["neue_zeilen"] == 1 and not z["fehler"] and u.modi == ["pruefe", "finde", "buche"]
        b = v.journal_lesen(os.path.join(l, "handelsbuch.jsonl"))[0]
        assert b[0]["ereignis"] == "auftrag" and b[0]["ziel"] == "xlu" and b[0]["h"] == 5 and b[0]["kosten_pp"] == 0.88 and b[0]["frist_utc"] == "2026-10-15T13:30:00Z"
        assert b[0]["code_commit"] == CC and b[0]["datenstand"]["main"] == "1" * 40 and b[0]["ausstieg"] == "2026-10-21"
        s = v.zustand(v.journal_lesen(os.path.join(l, "status.jsonl"))[0])["straenge"]["T1"]
        assert s["beginn"] == "2026-10-14" and s["aufnahme_commit"] == AUF and s["regeln"] == ["X_d5|hoch|xlu|5"]        # Beginn = erstes Sehen (G8-09)
        # Astra 7: Registrierung ändern und danach bytegleich zurücksetzen: der Stopp bleibt
        alt = open(os.path.join(r, "T1.json")).read(); lege(r, reg(mechanismus="anders"))
        u.jetzt = T(2026, 10, 15, 6); z = v.lauf(r, l, DS, u); assert z["aktiv"] == [] and z["statuswechsel"][0]["nach"] == "gestoppt"
        open(os.path.join(r, "T1.json"), "w").write(alt); n = u.rufe_n
        u.jetzt = T(2026, 10, 16, 6); z = v.lauf(r, l, DS, u); assert z["aktiv"] == [] and u.rufe_n == n and z["zaehler"]["gestoppt"] == 1
        # Astra 7: vierter Strang wird abgewiesen und rückt nicht nach, wenn später ein Platz frei wird
        u.jetzt = T(2026, 10, 14, 7)
        for k, ziel in (("A", "xle"), ("B", "xlf"), ("C", "xlk")):
            lege(r, reg(kennung=k, regeln=[dict(indikator="X_d5", art="hoch", ziel=ziel, h=5)]))
        lege(r, reg(kennung="U", art="uebung", vorpruefung={}, regeln=[dict(indikator="X_d5", art="hoch", ziel="xlb", h=5)]))
        z = v.lauf(r, l, DS, u); assert z["aktiv"] == ["A", "B", "C", "U"] and z["zaehler"]["plaetze_belegt"] == 3       # Übung zählt nicht zur Grenze
        lege(r, reg(kennung="D4", regeln=[dict(indikator="X_d5", art="hoch", ziel="xlv", h=5)]))
        z = v.lauf(r, l, DS, u); assert "D4" not in z["aktiv"] and z["zaehler"]["abgewiesen"] == 1
        os.remove(os.path.join(r, "A.json")); z = v.lauf(r, l, DS, u)
        assert "A" not in z["aktiv"] and "D4" not in z["aktiv"] and z["zaehler"]["gestoppt"] == 2 and z["zaehler"]["abgewiesen"] == 1
        # abgewiesen: rückdatiert, unbekannter Code, Code nicht auf main, alter Commit der Aufnahme, kaputte Dateien (T8-15); andere Stränge laufen weiter
        lege(r, reg(kennung="R", registriert="2026-09-01", regeln=[dict(indikator="X_d5", art="hoch", ziel="xly", h=5)]))
        lege(r, reg(kennung="F", code_commit="f" * 40, regeln=[dict(indikator="X_d5", art="hoch", ziel="xlp", h=5)]))
        lege(r, reg(kennung="N", code_commit="b" * 40, regeln=[dict(indikator="X_d5", art="hoch", ziel="xli", h=5)])); u.kein_vorfahr = {"b" * 40}
        lege(r, reg(kennung="ALT", regeln=[dict(indikator="X_d5", art="hoch", ziel="xlc", h=5)])); u.aufn["ALT.json"] = (AUF, T(2026, 10, 1, 9))
        lege(r, reg(kennung="G", freigabe=None, regeln=[dict(indikator="X_d5", art="hoch", ziel="xlre", h=5)]))
        lege(r, reg(kennung="K", kosten_pp=float("inf"), regeln=[dict(indikator="X_d5", art="hoch", ziel="smh", h=5)]))
        for name, inhalt in (("NULL", "null"), ("LISTE", "[]"), ("KAPUTT", "{kein json")):
            open(os.path.join(r, name + ".json"), "w").write(inhalt)
        z = v.lauf(r, l, DS, u)
        assert {x["kennung"] for x in z["fehler"]} == {"R", "F", "N", "ALT", "G", "K", "NULL", "LISTE", "KAPUTT"} and z["zaehler"]["abgewiesen"] == 10
        assert z["aktiv"] == ["B", "C", "U"]
        g = {x["kennung"]: x["fehler"][0] for x in z["fehler"]}
        assert "lag bei der Aufnahme" in g["N"] and "höchstens 3 Tage" in g["ALT"] and "freigabe" in g["G"] and "kosten_pp" in g["K"] and "kein JSON-Objekt" in g["NULL"]
        st = v.journal_lesen(os.path.join(l, "status.jsonl"))[0]
        assert all(x["von"] != x["nach"] for x in st if x["ereignis"] == "status")                                        # vollständiger Statusverlauf
        assert json.load(open(os.path.join(l, "stand.json")))["straenge"]["B"]["status"] == "aktiv"
    finally:
        shutil.rmtree(d)


def test_endzustaende_und_journal():
    """G8-07 / T8-10 / T8-11: Stopp auch im Zustand reserviert und beim direkten Schlussaufruf; der Stand entsteht aus dem Journal."""
    d, r, l = ordner()
    try:
        u = Stub(finde={"T1": [{"2026-10-13": (1.5, "2026-10-15")}]}); lege(r, reg()); v.lauf(r, l, DS, u)
        u.jetzt = T(2026, 10, 14, 6); v.lauf(r, l, DS, u)
        # T8-10: reservieren (die Rechnung scheitert), dann Registrierung ändern, direkten Schlussaufruf versuchen, Original zurückstellen
        u.jetzt = T(2028, 10, 16, 6); u.w = dict(fehler="Rechner ausgefallen")
        z = v.lauf(r, l, DS, u); assert status(l, "T1") == "reserviert" and "Rechner ausgefallen" in z["fehler"][0]["fehler"][0] and z["zaehler"]["plaetze_belegt"] == 1
        alt = open(os.path.join(r, "T1.json")).read(); lege(r, reg(mechanismus="anders"))
        abbruch(lambda: v.schluss(r, l, "T1", DS, u), "gestoppt"); assert status(l, "T1") == "gestoppt"
        open(os.path.join(r, "T1.json"), "w").write(alt); u.w = None
        abbruch(lambda: v.schluss(r, l, "T1", DS, u), "gestoppt"); v.lauf(r, l, DS, u)
        assert status(l, "T1") == "gestoppt" and not os.path.exists(os.path.join(l, "schluss_T1.json"))
        # T8-11 B/C: Stopp steht im Journal, stand.json ist alt oder fehlt: kein Wiederaufleben
        json.dump(dict(straenge=dict(T1=dict(status="aktiv"))), open(os.path.join(l, "stand.json"), "w")); v.lauf(r, l, DS, u); assert status(l, "T1") == "gestoppt"
        os.remove(os.path.join(l, "stand.json")); n = u.rufe_n; z = v.lauf(r, l, DS, u); assert z["aktiv"] == [] and u.rufe_n == n and z["zaehler"]["gestoppt"] == 1
        # T8-11 D: Änderung und Rücknahme in der Historie von main zwischen zwei Läufen
        lege(r, reg(kennung="H", regeln=[dict(indikator="X_d5", art="hoch", ziel="xle", h=5)])); u.jetzt = T(2026, 10, 14, 7); u.aufn["H.json"] = (AUF, T(2026, 10, 14, 6))
        assert "H" in v.lauf(r, l, DS, u)["aktiv"]
        u.hist["H.json"] = None; n = u.rufe_n; z = v.lauf(r, l, DS, u)                                                    # Historie nicht prüfbar: der Strang ruht, kein Stopp
        assert "H" in z["aktiv"] and "ruht" in z["fehler"][0]["fehler"][0] and u.rufe_n == n
        u.hist["H.json"] = ["d" * 40, "e" * 40]; z = v.lauf(r, l, DS, u)
        assert "H" not in z["aktiv"] and "Historie von main" in z["statuswechsel"][0]["grund"]
        u.hist["H.json"] = []; assert "H" not in v.lauf(r, l, DS, u)["aktiv"]
        # Statusjournal fehlt, Handelsbuch ist da: kein Neubeginn
        os.rename(os.path.join(l, "status.jsonl"), os.path.join(l, "weg")); abbruch(lambda: v.lauf(r, l, DS, u), "Statusjournal fehlt")
        os.rename(os.path.join(l, "weg"), os.path.join(l, "status.jsonl"))
        # T8-08: abgerissenes Ende eines Journals wird abgeschnitten und vermerkt; ein Fehler mitten in der Datei blockiert
        p = os.path.join(l, "status.jsonl"); n0 = len(v.journal_lesen(p)[0]); open(p, "a").write('{"ereignis": "status", "strang": "T1", "na')
        v.lauf(r, l, DS, u); j = v.journal_lesen(p)[0]
        assert len(j) == n0 + 1 and j[-1]["ereignis"] == "reparatur" and j[-1]["datei"] == "status.jsonl" and status(l, "T1") == "gestoppt"
        roh = open(p).read().split("\n"); roh[1] = roh[1][:20]; open(p, "w").write("\n".join(roh)); abbruch(lambda: v.lauf(r, l, DS, u), "beschädigt")
    finally:
        shutil.rmtree(d)


def test_oeffnung():
    """G8-08 / T8-12 / T8-13: Übergabe aus der Auswahl, ungültige Marker blockieren, die Öffnung bleibt ein dauerhaftes Ereignis."""
    d, r, l = ordner()
    try:
        u = Stub(jetzt=T(2026, 10, 12, 10))
        for k, ziel in (("A", "xle"), ("B", "xlf"), ("C", "xlk")):
            lege(r, reg(kennung=k, regeln=[dict(indikator="X_d5", art="hoch", ziel=ziel, h=5)]))
        assert v.lauf(r, l, DS, u)["aktiv"] == ["A", "B", "C"]
        p = os.path.join(r, v.OEFFNUNG)
        for bad in ("{}", json.dumps(dict(regeln=["X_d5|hoch|xlf|5"])), json.dumps(dict(geoeffnet_utc="x", freigabe="y", regeln=["S|X_d5|hoch"]))):
            open(p, "w").write(bad); n = u.rufe_n
            abbruch(lambda: v.lauf(r, l, DS, u), "ungültig"); assert u.rufe_n == n                                        # blockiert, bevor gerechnet wird
            abbruch(lambda: v.schluss(r, l, "B", DS, u), "ungültig")
        # tatsächliche Kennungen der Auswahl: Familie S und Familie V
        m = v.oeffnungsmarker(dict(finalist=dict(regeln=["S|X_d5|hoch|xlf|5", "V|V20261004-03|X_d5|hoch|xlk|5"])), "2026-11-01T07:00:00Z", "Reto, 1.11.2026: öffnen")
        json.dump(m, open(p, "w")); z = v.lauf(r, l, DS, u)
        assert z["aktiv"] == ["A"] and z["zaehler"]["beendet_ohne_urteil"] == 2
        # T8-13: Marker entfernen; dieselbe Regel unter neuer Kennung anmelden oder direkt auswerten
        os.remove(p); lege(r, reg(kennung="B2", vorgaenger=["B"], regeln=[dict(indikator="X_d5", art="hoch", ziel="xlf", h=5)]))
        z = v.lauf(r, l, DS, u); assert z["aktiv"] == ["A"] and "E32f" in z["fehler"][0]["fehler"][0] and status(l, "B2") == "abgewiesen"
        u.jetzt = T(2028, 10, 16, 6); abbruch(lambda: v.schluss(r, l, "B", DS, u), "beendet_ohne_urteil"); abbruch(lambda: v.schluss(r, l, "B2", DS, u), "abgewiesen")
    finally:
        shutil.rmtree(d)


def test_vorgaenger_und_dispatcher():
    d, r, l = ordner()
    try:
        # G8-09: dieselbe Regel unter neuer Kennung nur mit genanntem Vorgänger; nie gleichzeitig
        u = Stub(); lege(r, reg()); v.lauf(r, l, DS, u)
        lege(r, reg(kennung="T2")); z = v.lauf(r, l, DS, u); assert "läuft schon" in z["fehler"][0]["fehler"][0]
        os.remove(os.path.join(r, "T1.json")); v.lauf(r, l, DS, u); assert status(l, "T1") == "gestoppt"
        lege(r, reg(kennung="T3")); z = v.lauf(r, l, DS, u); assert "vorgaenger muss genau" in z["fehler"][-1]["fehler"][0] and status(l, "T3") == "abgewiesen"
        lege(r, reg(kennung="T4", vorgaenger=["T1"])); z = v.lauf(r, l, DS, u); assert z["aktiv"] == ["T4"]
        assert v.zustand(v.journal_lesen(os.path.join(l, "status.jsonl"))[0])["straenge"]["T4"]["vorgaenger"] == ["T1"]
        # G8-04: Der Dispatcher ändert sich, während T4 läuft: Abbruch ohne Eintrag, Fortsetzung mit Eintrag
        echt = v.datei_sha
        with ersetzt("datei_sha", lambda p: "neu" + "0" * 61 if os.path.basename(p) == "vorwaerts.py" else echt(p)):
            n = u.rufe_n; abbruch(lambda: v.lauf(r, l, DS, u), "freigegebene Migration"); assert u.rufe_n == n
            json.dump(dict(freigaben=[dict(sha256="neu" + "0" * 61, freigabe="Reto: Korrektur freigegeben")]), open(os.path.join(r, v.DISPATCHER), "w"))
            assert v.lauf(r, l, DS, u)["aktiv"] == ["T4"]
        j = [x for x in v.journal_lesen(os.path.join(l, "status.jsonl"))[0] if x["ereignis"] == "dispatcher"]; assert len(j) == 2 and j[1]["vorher"] == j[0]["sha256"]
    finally:
        shutil.rmtree(d)


# ---------------------------------------------------------------------------------------------- Kurse und Schlussauswertung
def kurse_schreiben(k, tage, name, f, luecke=(), adj_davor=True):
    with open(os.path.join(k, name + "_d.csv"), "w") as fh:
        fh.write("Date,Open,High,Low,Close,Volume,AdjClose\n")
        for i, t in enumerate(tage):
            o, c = f * (100 + i), f * (100.5 + i); adj = "" if (not adj_davor and t < D(2021, 1, 15)) else f"{c:.4f}"
            if str(t) not in luecke:
                fh.write(f"{t},{o:.4f},{c:.4f},{o:.4f},{c:.4f},1,{adj}\n")


def test_werte_und_kuerzen():
    d = tempfile.mkdtemp()
    try:
        k = os.path.join(d, "data", "kurse"); os.makedirs(k); os.makedirs(os.path.join(d, "data", "fred"))
        tage = v.nyse_handelstage(D(2020, 12, 1), D(2021, 3, 31)); S = [str(t) for t in tage]
        kurse_schreiben(k, tage, "acwi", 1.0); kurse_schreiben(k, tage, "xlu", 2.0); kurse_schreiben(k, tage, "xle", 1.0, luecke=("2021-02-10",))
        g = v.kurse_kuerzen(os.path.join(d, "data"), os.path.join(d, "basis"))
        z = open(os.path.join(g, "kurse", "xlu_d.csv")).read().strip().split("\n")
        assert z[-1][:10] == "2020-12-31" and len(z) == 1 + len([t for t in tage if t <= D(2020, 12, 31)]) and os.path.islink(os.path.join(g, "fred"))
        R = reg(schlusstag="2021-03-15", kosten_pp=0.88)
        def auf(regel, beob, ein, ziel, h=5, sitz=None):
            i = S.index(ein) if ein in S else None
            return dict(strang="T1", regel=regel, beobachtung=beob, einstieg=ein, h=h, ziel=ziel, sitzungen=sitz if sitz is not None else (S[i:i + h] if i is not None else []))
        A = [auf(0, "2021-02-01", "2021-02-03", "xlu"), auf(1, "2021-02-04", "2021-02-08", "xle"),
             auf(0, "2021-02-12", "2021-02-15", "xlu"),                                                                  # Presidents' Day: keine Sitzung
             auf(0, "2021-03-09", "2021-03-11", "xlu"), auf(0, "2021-02-20", "2021-02-22", "xlz")]                       # Fenster über den Schlusstag; Datei fehlt (T8-04)
        w = v.werte(R, "2021-01-15", A, os.path.join(d, "data"))
        assert [x["status"] for x in w] == ["ausgewertet"] + ["nicht auswertbar"] * 4
        assert "xle 2021-02-10" in w[1]["grund"] and "Sitzungen des Auftrags" in w[2]["grund"] and "über den Schlusstag" in w[3]["grund"] and "Kursdatei fehlt" in w[4]["grund"] and "xlz" in w[4]["grund"]
        i = S.index("2021-02-03"); assert abs(w[0]["netto_pp"] - (-0.88)) < 1e-9 and w[0]["ausstieg"] == S[i + 4]
        # Astra 7: neue Daten ausserhalb des Fensters ändern die Aufbereitung des Fensters nicht
        kurse_schreiben(k, tage, "xlu", 2.0, adj_davor=False)
        assert v.werte(R, "2021-01-15", A[:1], os.path.join(d, "data"))[0]["netto_pp"] == w[0]["netto_pp"]
        # G8-02 / T8-03: Im Vergleichsindex fehlt die mittlere Zeile; der Folgetag hat einen stark anderen Zielkurs. Nichts wird verschoben.
        kurse_schreiben(k, tage, "acwi", 1.0, luecke=("2021-02-05",))
        with open(os.path.join(k, "xlu_d.csv"), "a") as fh:
            pass
        zeilen = open(os.path.join(k, "xlu_d.csv")).read().split("\n"); j = next(n for n, x in enumerate(zeilen) if x.startswith(S[i + 5]))
        zeilen[j] = f"{S[i + 5]},400,400,400,400,1,400"; open(os.path.join(k, "xlu_d.csv"), "w").write("\n".join(zeilen))
        w3 = v.werte(R, "2021-01-15", A[:1], os.path.join(d, "data"))[0]
        assert w3["status"] == "nicht auswertbar" and "acwi 2021-02-05" in w3["grund"]
        kurse_schreiben(k, tage, "xlu", 2.0, luecke=("2021-02-05",))                                                    # dieselbe Zeile fehlt auch im Ziel
        w4 = v.werte(R, "2021-01-15", A[:1], os.path.join(d, "data"))[0]; assert w4["status"] == "nicht auswertbar" and "xlu 2021-02-05" in w4["grund"] and "acwi 2021-02-05" in w4["grund"]
        # dokumentierte Regel: eine eingetragene Sonderschliessung am 5.2.2021 rückt die Sitzungen nach
        w5 = v.werte(R, "2021-01-15", A[:1], os.path.join(d, "data"), sonder=["2021-02-05"])[0]
        assert w5["status"] == "ausgewertet" and w5["ausstieg"] == S[i + 5]
        os.remove(os.path.join(k, "acwi_d.csv")); assert "acwi" in v.werte(R, "2021-01-15", A[:1], os.path.join(d, "data"))[0]["grund"]   # ganze Datei des Index fehlt
    finally:
        shutil.rmtree(d)


def strang_bis_schluss(u, r, l):
    """Ein Strang mit zwei sauberen Aufträgen, bereit zur Schlussauswertung."""
    u.f = {"T1": [{"2026-10-13": (1.5, "2026-10-15"), "2026-11-10": (1.6, "2026-11-12")}]}
    lege(r, reg()); u.jetzt = T(2026, 10, 12, 10); L(r, l, u); u.jetzt = T(2026, 10, 14, 6); L(r, l, u); u.jetzt = T(2026, 11, 11, 6); L(r, l, u)
    b = v.journal_lesen(os.path.join(l, "handelsbuch.jsonl"))[0]; assert [x["ereignis"] for x in b] == ["auftrag", "auftrag"]


def stub_werte(e):
    return dict(protokoll=v.PROTOKOLL, auftraege_n=len(e["auftraege"]), verfallen_n=0, verfallen=[], gueltig_n=len(e["auftraege"]), auswertbar_n=1,
                nicht_auswertbar=[dict(regel=0, grund="Kurs im Haltefenster fehlt")], vollstaendig=False, genug_ereignisse=False,
                mittel_netto_pp_je_auftrag=1.0, jahresertrag_netto_pp=None, hinweis_unvollstaendig="x", einzeln=[])


def test_schluss():
    """G8-05 / G8-06 / T8-07 / T8-17: eingefrorene Daten, eine Instanz, fälliger Abschluss über den normalen Betriebsweg."""
    d, r, l = ordner()
    try:
        u = Stub(); strang_bis_schluss(u, r, l); u.w = stub_werte
        u.jetzt = T(2028, 10, 13, 6); abbruch(lambda: v.schluss(r, l, "T1", DS, u), "vor Ablauf des Schlusstags")
        z = v.lauf(r, l, DS, u); assert z["aktiv"] == ["T1"] and u.modi[-1] == "buche"                                  # am Schlusstag läuft das Handelsbuch noch
        # T8-17: nach dem Schlusstag wartet der Strang auf Kurse bis zum letzten Ausstieg, ohne zu reservieren
        u.jetzt = T(2028, 10, 16, 6); u.bis = "2026-11-17"
        z = v.lauf(r, l, DS, u); assert "wartet" in z["fehler"][0]["fehler"][0] and status(l, "T1") == "aktiv" and not os.path.exists(os.path.join(l, "schluss_T1.reserviert.json"))
        # Datenstand nicht belegt: keine Reservierung
        u.bis = "2099-12-31"; u.daten_fehler = ["Kursdateien weichen vom ausgecheckten Commit ab"]
        assert "nicht belegt" in v.lauf(r, l, DS, u)["fehler"][0]["fehler"][0]; u.daten_fehler = []
        assert not os.path.exists(os.path.join(l, "schluss_T1.reserviert.json"))
        # Reservierung, dann scheitert die Rechnung: derselbe Stand bleibt reserviert und belegt einen Platz
        u.w = dict(fehler="Absturz"); z = v.lauf(r, l, DS, u)
        assert "Absturz" in z["fehler"][0]["fehler"][0] and status(l, "T1") == "reserviert" and z["zaehler"]["plaetze_belegt"] == 1 and z["zaehler"]["aktiv"] == 0
        res = json.load(open(os.path.join(l, "schluss_T1.reserviert.json")))
        assert res["datenstand"]["main"] == "1" * 40 and len(res["auftraege"]) == 2 and res["manifest"] == {"acwi": "m1", "xlu": "m2"} and res["registrierung_sha256"]
        # T8-07: gleiches Etikett, andere Kursbytes: Integritätsfehler; anderes Etikett: Abbruch; nie ein anderes Ergebnis unter derselben Instanz
        u.w = stub_werte; u.mf = {"acwi": "m1", "xlu": "ANDERS"}; n = u.rufe_n
        abbruch(lambda: v.schluss(r, l, "T1", DS, u), "Integritätsfehler"); assert u.rufe_n == n
        u.mf = {"acwi": "m1", "xlu": "m2"}; abbruch(lambda: v.schluss(r, l, "T1", DS2, u), "reservierten Datenstand")
        u.daten_fehler = ["ausgecheckter Commit der Kurse ist nicht der genannte Datenstand main"]; abbruch(lambda: v.schluss(r, l, "T1", DS, u), "nicht belegt"); u.daten_fehler = []
        # die gespeicherte Auftragsprüfsumme wird beim Einlesen kontrolliert
        p_res = os.path.join(l, "schluss_T1.reserviert.json"); gut = open(p_res).read()
        kaputt = json.loads(gut); kaputt["auftraege"][0]["einstieg"] = "2026-10-16"; json.dump(kaputt, open(p_res, "w")); abbruch(lambda: v.schluss(r, l, "T1", DS, u), "Integritätsfehler")
        open(p_res, "w").write(gut); assert not os.path.exists(os.path.join(l, "schluss_T1.json"))
        # normaler Betriebsweg schliesst ab; spätere Aufrufe lesen nur dieses Ergebnis
        u.jetzt = T(2028, 10, 18, 6); z = v.lauf(r, l, DS, u); assert status(l, "T1") == "ausgewertet" and z["zaehler"]["plaetze_belegt"] == 0 and not z["fehler"]
        e1 = json.load(open(os.path.join(l, "schluss_T1.json")))
        assert e1["auftraege_n"] == 2 and e1["vollstaendig"] is False and e1["jahresertrag_netto_pp"] is None and e1["auftraege_sha256"] == res["auftraege_sha256"] and "5%" in e1["art"]
        assert e1["reserviert_utc"] == "2028-10-16T06:00:00Z" and "zaehler" not in e1
        n = u.rufe_n; u.jetzt = T(2028, 10, 19, 6); u.mf = {"acwi": "zzz"}
        assert v.schluss(r, l, "T1", DS2, u) == e1 and u.rufe_n == n and v.lauf(r, l, DS, u)["zaehler"]["ausgewertet"] == 1
        assert sorted(n for n in os.listdir(l) if n.startswith("schluss_")) == ["schluss_T1.json", "schluss_T1.reserviert.json"]
    finally:
        shutil.rmtree(d)


def test_schreibabbruch():
    """G8-06 / T8-08 / T8-09: Abbruch an jeder Schreibgrenze der Schlussauswertung; danach genau eine Instanz und ein stimmiger Status."""
    class Aus(Exception):
        pass
    def lauf_mit_abbruch(stelle):
        d, r, l = ordner(); u = Stub()
        try:
            strang_bis_schluss(u, r, l); u.w = stub_werte; u.jetzt = T(2028, 10, 16, 6)
            echt_einmal, echt_anh, echt_link = v.schreibe_einmal, v.anhaengen, os.link
            def einmal(p, obj):
                if stelle == "vor_reservierung" and p.endswith(".reserviert.json"):
                    raise Aus
                if stelle == "vor_ergebnis" and p.endswith("schluss_T1.json"):
                    raise Aus
                if stelle == "mitten_im_ergebnis" and p.endswith("schluss_T1.json"):
                    open(p + ".teil.999", "w").write('{"kennung": "T1", "halb'); raise Aus                              # Hilfsdatei halb geschrieben, nie veröffentlicht
                return echt_einmal(p, obj)
            def anh(p, zeilen):
                nach = [z.get("nach") for z in zeilen]
                if stelle == "nach_reservierung" and "reserviert" in nach:
                    raise Aus
                if stelle == "nach_ergebnis" and "ausgewertet" in nach:
                    raise Aus
                if stelle == "halbe_statuszeile" and "ausgewertet" in nach:
                    open(p, "a").write(json.dumps(zeilen[0])[:25]); raise Aus
                return echt_anh(p, zeilen)
            with ersetzt("schreibe_einmal", einmal), ersetzt("anhaengen", anh):
                try:
                    v.lauf(r, l, DS, u); assert False, stelle
                except Aus:
                    pass
            vor = {n: open(os.path.join(l, n)).read() for n in os.listdir(l) if n.startswith("schluss_") and ".teil." not in n}
            u.jetzt = T(2028, 10, 17, 6); n0 = u.rufe_n; z = v.lauf(r, l, DS, u)
            assert status(l, "T1") == "ausgewertet" and not z["fehler"], (stelle, z["fehler"])
            fertig = sorted(n for n in os.listdir(l) if n.startswith("schluss_") and ".teil." not in n)
            assert fertig == ["schluss_T1.json", "schluss_T1.reserviert.json"], (stelle, fertig)
            for n, text in vor.items():
                assert open(os.path.join(l, n)).read() == text, (stelle, n)                                               # einmal Veröffentlichtes bleibt bytegleich
            if stelle in ("nach_ergebnis", "halbe_statuszeile"):                                                          # T8-09: Ergebnis wiederverwendet, nichts neu gerechnet
                assert u.rufe_n == n0, stelle
            j = v.journal_lesen(os.path.join(l, "status.jsonl"))[0]
            assert [x["nach"] for x in j if x["ereignis"] == "status" and x["strang"] == "T1"] == ["aktiv", "reserviert", "ausgewertet"], stelle
            if stelle == "halbe_statuszeile":
                assert any(x["ereignis"] == "reparatur" for x in j)
            json.load(open(os.path.join(l, "schluss_T1.json")))
        finally:
            shutil.rmtree(d)
    for stelle in ("vor_reservierung", "nach_reservierung", "vor_ergebnis", "mitten_im_ergebnis", "nach_ergebnis", "halbe_statuszeile"):
        lauf_mit_abbruch(stelle)
    # schreibe_einmal: zweiter Versuch überschreibt nicht; es bleibt keine Hilfsdatei
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "x.json"); assert v.schreibe_einmal(p, dict(a=1)) is True and v.schreibe_einmal(p, dict(a=2)) is False
        assert json.load(open(p)) == dict(a=1) and os.listdir(d) == ["x.json"]
    finally:
        shutil.rmtree(d)


# ---------------------------------------------------------------------------------------------- echte Git-Historie
def git(repo, *a, datum=None):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    if datum:
        env.update(GIT_AUTHOR_DATE=datum, GIT_COMMITTER_DATE=datum)
    r = subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, env=env)
    assert r.returncode == 0, (a, r.stderr)
    return r.stdout.strip()


def test_git():
    """T8-05, T8-06, T8-14 mit echter lokaler Historie und einem älteren Arbeitsbaum; dazu Zeitnachweis und Datenprüfung."""
    d = tempfile.mkdtemp()
    try:
        repo = os.path.join(d, "repo"); os.makedirs(os.path.join(repo, "vorwaerts")); os.makedirs(os.path.join(repo, "data", "kurse"))
        git(repo, "init", "-q", "-b", "main")
        quelle = open(os.path.join(v.HIER, "vorwaerts.py"), encoding="utf-8").read()
        open(os.path.join(repo, "vorwaerts.py"), "w", encoding="utf-8").write(quelle)
        open(os.path.join(repo, "data", "kurse", "acwi_d.csv"), "w").write("Date,Open,Close\n2026-10-12,1,1\n")
        git(repo, "add", "-A"); git(repo, "commit", "-qm", "A", datum="2026-10-10T09:00:00+00:00"); A = git(repo, "rev-parse", "HEAD")
        u = v.Umgebung(repo=repo, arbeit=os.path.join(d, "arbeit")); os.makedirs(u.arbeit)
        # T8-05: bewegliche Verweise und Kürzel werden nicht aufgelöst
        for c in ("refs/heads/main", "main", "HEAD", A[:12], A + "x"):
            assert u.code_dir(c) is None, c
        cdA = u.code_dir(A); assert cdA and cdA != repo and git(cdA, "rev-parse", "HEAD") == A
        # T8-06: Der Dispatcher von heute hat eine andere Frist; der Strang behält die Regel seines Commits
        assert "FRIST_UTC = datetime.time(13, 30)" in quelle
        open(os.path.join(repo, "vorwaerts.py"), "w", encoding="utf-8").write(quelle.replace("FRIST_UTC = datetime.time(13, 30)", "FRIST_UTC = datetime.time(20, 0)"))
        git(repo, "commit", "-qam", "B", datum="2026-10-11T09:00:00+00:00"); B = git(repo, "rev-parse", "HEAD")
        R = reg(code_commit=A); kal = [str(t) for t in v.nyse_handelstage(D(2026, 10, 12), D(2026, 12, 31))]
        ein = dict(reg=R, alt=[], gefunden=[dict(gefunden={"2026-10-14": [1.5, "2026-10-15"]}, reihe_bis=None)], kalender=kal, reihe_bis_vorher=[None], erkannt_utc="2026-10-15T14:00:00Z")
        zA = u.rufe(cdA, "buche", ein)["zeilen"][0]; zB = u.rufe(u.code_dir(B), "buche", ein)["zeilen"][0]
        assert (zA["ereignis"], zA["grund"]) == ("kein_auftrag", "verspätet erkannt") and zB["ereignis"] == "auftrag" and zB["frist_utc"].endswith("T20:00:00Z")
        u2 = v.Umgebung(repo=repo, arbeit=os.path.join(d, "arbeit2")); os.makedirs(u2.arbeit)                            # späterer Lauf, main ist weitergezogen
        assert u2.rufe(u2.code_dir(A), "buche", ein)["zeilen"][0]["ereignis"] == "kein_auftrag"
        assert u.rufe(cdA, "pruefe", dict(reg=R, beginn="2026-10-12"))["fehler_liste"] == []
        open(os.path.join(cdA, "vorwaerts.py"), "a").write("\n# verändert\n"); assert u.code_dir(A) is None                # veränderter Arbeitsbaum zählt nicht als dieser Commit
        assert u.ist_vorfahr(A, B) and not u.ist_vorfahr(B, A) and not u.ist_vorfahr("main", B)
        # T8-14: Datei früh auf einem Seitenzweig angelegt, später nach main übernommen: Es zählt die Aufnahme auf main
        git(repo, "checkout", "-qb", "seite"); p = os.path.join(repo, "vorwaerts", "T1.json"); json.dump(reg(code_commit=A), open(p, "w"))
        git(repo, "add", "-A"); git(repo, "commit", "-qm", "Registrierung auf dem Seitenzweig", datum="2026-10-01T09:00:00+00:00"); seite = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "-q", "main"); git(repo, "merge", "-q", "--no-ff", "-m", "Aufnahme", "seite", datum="2026-10-12T09:00:00+00:00"); M = git(repo, "rev-parse", "HEAD")
        auf = u.aufnahme(p); assert auf == (M, T(2026, 10, 12, 9, 0)) and auf[0] != seite
        assert u.geaendert_seit(p, M) == [] and u.geaendert_seit(p, "main") is None
        # Umbenennen: die neue Datei hat ihre eigene Aufnahme, kein alter Beginn über die Verfolgung von Umbenennungen
        git(repo, "mv", "vorwaerts/T1.json", "vorwaerts/T2.json"); git(repo, "commit", "-qm", "umbenannt", datum="2026-10-20T09:00:00+00:00")
        assert u.aufnahme(os.path.join(repo, "vorwaerts", "T2.json"))[1] == T(2026, 10, 20, 9, 0)
        # T8-11 D: ändern und zurückstellen in zwei Commits bleibt in der Historie sichtbar
        p2 = os.path.join(repo, "vorwaerts", "T2.json"); neu = git(repo, "rev-parse", "HEAD"); alt = open(p2).read()
        open(p2, "w").write(alt.replace("Test", "Anders")); git(repo, "commit", "-qam", "geändert"); open(p2, "w").write(alt); git(repo, "commit", "-qam", "zurück")
        assert open(p2).read() == alt and len(u.geaendert_seit(p2, neu)) == 2
        # G9-01 A: Der Öffnungsmarker wird aus der Historie gelesen; hinzufügen und wieder entfernen bleibt sichtbar
        po = os.path.join(repo, "vorwaerts", v.OEFFNUNG); assert u.marker_historie(os.path.join(repo, "vorwaerts")) == []
        m1 = json.dumps(v.oeffnungsmarker(dict(finalist=dict(regeln=["S|X_d5|hoch|xlf|5"])), "2026-11-01T07:00:00Z", "Reto: öffnen"))
        open(po, "w").write(m1); git(repo, "add", "-A"); git(repo, "commit", "-qm", "Öffnung"); c1 = git(repo, "rev-parse", "HEAD")
        open(po, "w").write("{}"); git(repo, "commit", "-qam", "Marker verändert"); c2 = git(repo, "rev-parse", "HEAD")
        git(repo, "rm", "-q", "vorwaerts/" + v.OEFFNUNG); git(repo, "commit", "-qm", "Marker entfernt")
        assert not os.path.exists(po) and u.marker_historie(os.path.join(repo, "vorwaerts")) == [(c1, m1), (c2, "{}")]
        # G9-02: Die Historie kennt ein Journal, auch wenn die Datei fehlt
        log = os.path.join(repo, "log"); os.makedirs(log); pb = os.path.join(log, "status.jsonl")
        assert u.journal_bekannt(pb) is False and u.veroeffentlicht_stand(log) is True
        v.anhaengen(pb, [dict(n=1)]); assert u.veroeffentlicht_stand(log) is False
        git(repo, "add", "-A"); git(repo, "commit", "-qm", "Journal"); assert u.journal_bekannt(pb) is True and u.veroeffentlicht_stand(log) is True
        os.remove(pb); assert u.journal_bekannt(pb) is True and u.journal_bekannt(os.path.join(d, "nirgends", "status.jsonl")) is None
        git(repo, "checkout", "-q", "--", "log/status.jsonl")
        # G8-05: Die Kursbytes müssen zum genannten Commit gehören
        K = git(repo, "rev-parse", "HEAD"); ds = dict(main=K, neu="2" * 40, energie="3" * 40)
        assert u.daten_pruefen(ds) == [] and u.daten_pruefen(dict(ds, main=A)) and u.kurse_bis() == "2026-10-12"
        m1 = u.manifest(["acwi", "xlu"]); assert m1["xlu"] is None and len(m1["acwi"]) == 64
        open(os.path.join(repo, "data", "kurse", "acwi_d.csv"), "a").write("2026-10-13,2,2\n")
        assert "weichen" in u.daten_pruefen(ds)[0] and u.manifest(["acwi"])["acwi"] != m1["acwi"]
    finally:
        shutil.rmtree(d)


# ---------------------------------------------------------------------------------------------- Gegenproben aus Gutachten 9
def test_oeffnung_in_jedem_anfangszustand():
    """G9-01 A / T9-01 / T9-02: Eine Öffnung wird auch im leeren und gesperrten Register gesichert; ein ungültiger Marker
    blockiert auch dort; hinzugefügte und wieder entfernte Marker kommen aus der Historie."""
    m = json.dumps(v.oeffnungsmarker(dict(finalist=dict(regeln=["S|X_d5|hoch|xlu|5"])), "2026-11-01T07:00:00Z", "Reto, 1.11.2026: öffnen"))
    for modus in (None, "offen"):                                                       # T9-02: kontrollierter Fehler statt frühem Rücksprung
        d, r, l = ordner(modus)
        try:
            for bad in ("{}", m.replace("2026-11-01T07:00:00Z", "bald")):
                open(os.path.join(r, v.OEFFNUNG), "w").write(bad); abbruch(lambda: v.lauf(r, l, DS, Stub()), "ungültig")
        finally:
            shutil.rmtree(d)
    d, r, l = ordner(None)                                                              # T9-01: leer und gesperrt
    try:
        u = Stub(T(2026, 11, 1, 8)); open(os.path.join(r, v.OEFFNUNG), "w").write(m)
        z = v.lauf(r, l, "", u); assert z["modus"] == "gesperrt" and z["registrierungen"] == 0
        j = v.journal_lesen(os.path.join(l, "status.jsonl"))[0]; assert [x["regeln"] for x in j if x["ereignis"] == "oeffnung"] == [["X_d5|hoch|xlu|5"]]
        os.remove(os.path.join(r, v.OEFFNUNG)); json.dump(dict(modus="offen", freigabe="Test"), open(os.path.join(r, v.FREIGABE), "w"))
        u.jetzt = T(2026, 11, 20, 10); u.aufn["T1.json"] = (AUF, T(2026, 11, 20, 9)); spaet = dict(registriert="2026-11-20", letzter_einstieg="2028-10-20", schlusstag="2028-11-22"); lege(r, reg(**spaet))
        z = v.lauf(r, l, DS, u); assert z["aktiv"] == [] and "E32f" in z["fehler"][0]["fehler"][0] and status(l, "T1") == "abgewiesen"
        # zwischen zwei Läufen hinzugefügt und wieder entfernt: nur die Historie von main kennt die Fassung
        u.marker_hist = [("1" * 40, m.replace("xlu", "xle")), ("2" * 40, "{}")]
        lege(r, reg(kennung="T2", **spaet, regeln=[dict(indikator="X_d5", art="hoch", ziel="xle", h=5)])); u.aufn["T2.json"] = (AUF, T(2026, 11, 20, 9))
        z = v.lauf(r, l, DS, u); assert status(l, "T2") == "abgewiesen" and "E32f" in z["fehler"][0]["fehler"][0]
        j = v.journal_lesen(os.path.join(l, "status.jsonl"))[0]; n = len(j)
        assert [x["ereignis"] for x in j if x.get("commit")] == ["oeffnung", "oeffnung_unlesbar"]
        v.lauf(r, l, DS, u); assert len(v.journal_lesen(os.path.join(l, "status.jsonl"))[0]) == n                      # jede Fassung wird genau einmal verbucht
    finally:
        shutil.rmtree(d)


def test_semantische_aufnahme():
    """G9-07 / T9-03 / T9-14: Mängel der Regeln selbst führen vor «aktiv» zur Abweisung und belegen keinen Platz; ein
    vorübergehender Ausfall des Signalrechners ist keine Abweisung."""
    d, r, l = ordner()
    try:
        u = Stub(); u.struktur = {"T1": ["0/1-Reihe BIN_stand: nur Extremtyp «hoch»"], "T2": ["je Grundreihe höchstens eine Regel", "Ziel gehört nicht zur Familie S: abc"]}
        lege(r, reg(regeln=[dict(indikator="BIN_stand", art="tief", ziel="xlu", h=5)]))
        lege(r, reg(kennung="T2", regeln=[dict(indikator="X_d1", art="hoch", ziel="xle", h=5), dict(indikator="X_d5", art="hoch", ziel="abc", h=5)]))
        z = v.lauf(r, l, DS, u)
        assert z["aktiv"] == [] and z["zaehler"]["plaetze_belegt"] == 0 and z["zaehler"]["abgewiesen"] == 2 and z["neue_zeilen"] == 0
        assert not os.path.exists(os.path.join(l, "handelsbuch.jsonl")) and "buche" not in u.modi                       # keine Ausfallzeilen, kein belegter Platz
        # Signalrechner fällt aus: weder aktiv noch abgewiesen; der nächste Lauf nimmt auf
        u.finde_fehler = "Daten nicht erreichbar"; lege(r, reg(kennung="T3", regeln=[dict(indikator="X_d5", art="hoch", ziel="xlf", h=5)]))
        z = v.lauf(r, l, DS, u); assert "T3" not in v.zustand(v.journal_lesen(os.path.join(l, "status.jsonl"))[0])["straenge"] and "wieder versucht" in z["fehler"][0]["fehler"][0]
        u.finde_fehler = None; z = v.lauf(r, l, DS, u); assert z["aktiv"] == ["T3"]
    finally:
        shutil.rmtree(d)


def test_journal_vollstaendigkeit():
    """G9-02 A / T9-04 / T9-05: Ein fehlendes, geleertes, gekürztes oder verändertes Journal ist kein leerer Anfang."""
    def aufbau():
        d, r, l = ordner(); u = Stub(finde={"T1": [{}]}); lege(r, reg()); L(r, l, u)
        u.f["T1"][0]["2026-10-13"] = (1.5, "2026-10-15"); u.jetzt = T(2026, 10, 14, 6); L(r, l, u)
        return d, r, l, u
    def faelle():
        yield "Handelsbuch entfernt", lambda l: os.remove(os.path.join(l, "handelsbuch.jsonl")), "handelsbuch stimmt nicht"
        yield "Handelsbuch auf null Bytes", lambda l: open(os.path.join(l, "handelsbuch.jsonl"), "w").close(), "handelsbuch stimmt nicht"
        yield "Statusjournal geleert", lambda l: open(os.path.join(l, "status.jsonl"), "w").close(), "Statusjournal fehlt oder ist leer"
        yield "Statusjournal entfernt", lambda l: os.remove(os.path.join(l, "status.jsonl")), "Statusjournal fehlt oder ist leer"
        yield "Statusjournal um die letzte Zeile gekürzt", lambda l: kuerze(os.path.join(l, "status.jsonl")), "status stimmt nicht"
        yield "Vermerke entfernt", lambda l: os.remove(os.path.join(l, v.VERMERK)), "veroeffentlicht stimmt nicht"
        yield "Auftrag im Handelsbuch verändert", lambda l: ersetze(os.path.join(l, "handelsbuch.jsonl"), "2026-10-15", "2026-10-16"), "handelsbuch stimmt nicht"
    def kuerze(p):
        z = open(p).read().strip().split("\n"); open(p, "w").write("\n".join(z[:-1]) + "\n")
    def ersetze(p, a, b):
        t = open(p).read(); assert a in t; open(p, "w").write(t.replace(a, b))
    for name, schaden, teil in faelle():
        d, r, l, u = aufbau()
        try:
            schaden(l); n = u.rufe_n; u.jetzt = T(2026, 10, 15, 6)
            abbruch(lambda: v.lauf(r, l, DS, u), teil); assert u.rufe_n == n, name                                       # vor jedem neuen Entscheid
            abbruch(lambda: v.schluss(r, l, "T1", DS, u), teil)
        finally:
            shutil.rmtree(d)
    # T9-05: endgültiger Stopp, dann Statusdatei geleert, Registrierung unverändert und noch in der Frist: kein neues «aktiv»
    d, r, l, u = aufbau()
    try:
        alt = open(os.path.join(r, "T1.json")).read(); lege(r, reg(mechanismus="anders")); u.jetzt = T(2026, 10, 14, 7); L(r, l, u); assert status(l, "T1") == "gestoppt"
        open(os.path.join(r, "T1.json"), "w").write(alt); open(os.path.join(l, "status.jsonl"), "w").close()
        abbruch(lambda: v.lauf(r, l, DS, u), "Statusjournal fehlt oder ist leer")
        # alles gelöscht, aber die Historie des Zweigs kennt die Journale: kein Neubeginn
        shutil.rmtree(l); u.bekannt = True; abbruch(lambda: v.lauf(r, l, DS, u), "obwohl die Historie des Zweigs es kennt")
    finally:
        shutil.rmtree(d)
    # Anhängen nach dem Siegel ist erlaubt (ein abgebrochener Lauf darf Statuszeilen hinterlassen)
    d, r, l, u = aufbau()
    try:
        v.anhaengen(os.path.join(l, "status.jsonl"), [dict(ereignis="reparatur", datei="x", grund="Probe", zeit_utc="2026-10-14T07:00:00Z")])
        u.jetzt = T(2026, 10, 15, 6); assert v.lauf(r, l, DS, u)["aktiv"] == ["T1"]
        assert v.praefix_sha(os.path.join(l, "status.jsonl"), 10 ** 6) is None and v.praefix_sha(os.path.join(l, "fehlt"), 0) == v.praefix_sha(os.path.join(l, "fehlt2"), 0)
    finally:
        shutil.rmtree(d)


def test_umgebung_und_eingaben():
    """G9-04 / T9-09 / T9-11: Schalter der Umgebung erreichen den festgeschriebenen Code nicht; die Rechenumgebung wird je
    Strang festgehalten und bei einer reservierten Schlussauswertung erzwungen."""
    alt = dict(os.environ)
    try:
        os.environ.update(PS_PAARE="/fremd/paare.txt", PS_MECHANISMEN="/fremd/mech.txt", PS_PLACEBO="3", PS_BASIS_NEU="file:///neu", PS_VORWAERTS_MODUS="x", ANDERES="bleibt")
        e = v.Umgebung(arbeit=tempfile.gettempdir()).prozess_umgebung()
        assert e.get("PS_BASIS_NEU") == "file:///neu" and e.get("ANDERES") == "bleibt" and not [k for k in e if k.startswith("PS_") and k not in v.UMGEBUNG_ERLAUBT]
    finally:
        os.environ.clear(); os.environ.update(alt)
    G = v.umgebung_gleich
    assert G(dict(python="3.12.1", numpy="1", pandas="2"), dict(python="3.12.9", numpy="1", pandas="2"))
    assert not G(dict(python="3.12.1", numpy="1", pandas="2"), dict(python="3.13.0", numpy="1", pandas="2")) and not G(dict(python="3.12.1", numpy="1", pandas="2"), dict(python="3.12.1", numpy="1.1", pandas="2"))
    assert not G(None, dict(python="3.12.1")) and G(None, None)
    d, r, l = ordner()
    try:
        u = Stub(); strang_bis_schluss(u, r, l)
        assert v.zustand(v.journal_lesen(os.path.join(l, "status.jsonl"))[0])["straenge"]["T1"]["umgebung"] == u.ver
        u.ver = dict(u.ver, pandas="3"); u.jetzt = T(2026, 11, 12, 6); z = L(r, l, u); assert z["umgebung_abweichend"] == ["T1"] and z["aktiv"] == ["T1"]
        u.ver = dict(u.ver, pandas="2"); u.w = dict(fehler="Absturz"); u.jetzt = T(2028, 10, 16, 6); L(r, l, u); assert status(l, "T1") == "reserviert"
        u.w = stub_werte; u.ver = dict(u.ver, python="3.13.0"); abbruch(lambda: v.schluss(r, l, "T1", DS, u), "reservierten Rechenumgebung")
        u.ver = dict(u.ver, python="3.12.7"); assert v.schluss(r, l, "T1", DS, u)["kennung"] == "T1"
    finally:
        shutil.rmtree(d)


def test_wartefrist_je_quelle():
    """G9-05 / T9-12: Die Wartefrist gilt je benötigter Kursdatei und nach Sonderschliessungen; danach ein endgültiges Ergebnis."""
    d, r, l = ordner()
    try:
        u = Stub(); strang_bis_schluss(u, r, l); u.w = stub_werte                              # letzter Ausstieg 18.11.2026 (Ziel xlu)
        assert v.bedarf([dict(ziel="xlu", h=5, einstieg="2026-11-12", sitzungen=["2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18"])])["bedarf"] == {"xlu": "2026-11-18", "acwi": "2026-11-18"}
        b = v.bedarf([dict(ziel="xlu", h=5, einstieg="2026-11-12", sitzungen=["2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18"])], ["2026-11-16"])["bedarf"]
        assert b == {"xlu": "2026-11-19", "acwi": "2026-11-19"}                                  # Sonderschliessung verlängert das Fenster
        u.jetzt = T(2028, 10, 16, 6); u.bis = {"acwi": "2099-12-31", "xlu": "2026-11-17"}        # der Index ist vollständig, das Ziel endet einen Tag zu früh
        z = v.lauf(r, l, DS, u); assert "wartet" in z["fehler"][0]["fehler"][0] and "xlu" in z["fehler"][0]["fehler"][0] and status(l, "T1") == "aktiv"
        assert not os.path.exists(os.path.join(l, "schluss_T1.reserviert.json"))
        u.bis["xlu"] = None; assert "wartet" in v.lauf(r, l, DS, u)["fehler"][0]["fehler"][0]     # ganze Datei fehlt: ebenfalls warten
        u.jetzt = T(2028, 10, 17, 6); u.bis["xlu"] = "2026-11-18"; z = v.lauf(r, l, DS, u)       # am Folgetag geliefert
        assert not z["fehler"] and status(l, "T1") == "ausgewertet" and json.load(open(os.path.join(l, "schluss_T1.reserviert.json")))["kurse_unvollstaendig_nach_wartefrist"] == []
    finally:
        shutil.rmtree(d)
    d, r, l = ordner()
    try:
        u = Stub(); strang_bis_schluss(u, r, l); u.w = stub_werte; u.bis = {"acwi": "2099-12-31", "xlu": "2026-11-17"}
        u.jetzt = T(2028, 11, 12, 6); assert "wartet" in v.lauf(r, l, DS, u)["fehler"][0]["fehler"][0]          # 30 Tage nach dem Schlusstag: noch warten
        u.jetzt = T(2028, 11, 13, 6); z = v.lauf(r, l, DS, u)                                                 # danach: endgültig, die Lücke steht in der Reservierung
        assert status(l, "T1") == "ausgewertet" and json.load(open(os.path.join(l, "schluss_T1.reserviert.json")))["kurse_unvollstaendig_nach_wartefrist"] == ["xlu"]
        e1 = open(os.path.join(l, "schluss_T1.json")).read(); u.bis["xlu"] = "2099-12-31"; u.jetzt = T(2028, 11, 14, 6); v.lauf(r, l, DS, u)
        assert open(os.path.join(l, "schluss_T1.json")).read() == e1                                           # die einzige Schlussinstanz bleibt unverändert
    finally:
        shutil.rmtree(d)


def test_ungueltige_kurse():
    """G9-06 / T9-13: Kurse von null, negative Kurse und ungültige Anpassungsfaktoren machen den Auftrag «nicht auswertbar»."""
    d = tempfile.mkdtemp()
    try:
        k = os.path.join(d, "data", "kurse"); os.makedirs(k); tage = v.nyse_handelstage(D(2021, 1, 4), D(2021, 3, 31)); S = [str(t) for t in tage]
        def schreibe(name, aendern=None, adj=True):
            with open(os.path.join(k, name + "_d.csv"), "w") as fh:
                fh.write("Date,Open,High,Low,Close,Volume" + (",AdjClose\n" if adj else "\n"))
                for i, t in enumerate(tage):
                    z = dict(o=100.0 + i, c=100.5 + i, a=100.5 + i); z.update((aendern or {}).get(str(t), {}))
                    fh.write(f"{t},{z['o']},{z['c']},{z['o']},{z['c']},1" + (f",{z['a']}\n" if adj else "\n"))
        R = reg(schlusstag="2021-03-15"); i = S.index("2021-02-03")
        A = [dict(strang="T1", regel=0, beobachtung="2021-02-01", einstieg=S[i], h=5, ziel="xlu", sitzungen=S[i:i + 5])]
        W = lambda: v.werte(R, "2021-01-15", A, os.path.join(d, "data"))[0]                    # noqa: E731
        schreibe("acwi"); schreibe("xlu"); assert W()["status"] == "ausgewertet"
        for name, adj, aendern, teil in (("Eröffnung null, ohne AdjClose", False, {S[i]: dict(o=0.0)}, "(Eröffnung)"),
                                         ("Eröffnung negativ, ohne AdjClose", False, {S[i]: dict(o=-100.0)}, "(Eröffnung)"),
                                         ("Schluss null am Ausstieg", False, {S[i + 4]: dict(c=0.0)}, S[i + 4]),
                                         ("Anpassungsfaktor negativ", True, {S[i + 2]: dict(a=-5.0)}, S[i + 2]),
                                         ("Schlusskurs null bei vorhandenem AdjClose", True, {S[i + 4]: dict(c=0.0)}, S[i + 4])):
            schreibe("xlu", aendern, adj); w = W()
            assert w["status"] == "nicht auswertbar" and "ungültig" in w["grund"] and teil in w["grund"] and "netto_pp" not in w, (name, w)
        schreibe("xlu"); schreibe("acwi", {S[i]: dict(o=0.0)}, False); assert "acwi" in W()["grund"]
        e = v.schliesse(R, "2021-01-15", [dict(A[0], frist_utc=S[i] + "T13:30:00Z", erkannt_utc=S[i] + "T06:00:00Z", gespeichert_utc=S[i] + "T06:00:01Z", veroeffentlicht_utc=S[i] + "T06:02:00Z")], os.path.join(d, "data"))
        assert e["vollstaendig"] is False and e["jahresertrag_netto_pp"] is None and e["auswertbar_n"] == 0       # kein Absturz des Schlussrechners
    finally:
        shutil.rmtree(d)


def test_auswahl_uebergabe():
    """T9-16: Die Kennungen entstehen mit den Funktionen der Auswahl selbst und laufen durch Marker, Lauf und Schlussaufruf."""
    import auswahl as a
    ks, kv = a.kennung_s("X_d5", "hoch", "xlf", 5.0), a.kennung_v("V20261004-03", v.regel_schluessel(dict(indikator="X_d5", art="hoch", ziel="xlk", h=5)))
    assert v.kanon(ks) == "X_d5|hoch|xlf|5" and v.kanon(kv) == "X_d5|hoch|xlk|5"
    d, r, l = ordner()
    try:
        u = Stub()
        for k, ziel in (("A", "xle"), ("B", "xlf"), ("C", "xlk")):
            lege(r, reg(kennung=k, regeln=[dict(indikator="X_d5", art="hoch", ziel=ziel, h=5)]))
        assert v.lauf(r, l, DS, u)["aktiv"] == ["A", "B", "C"]
        json.dump(v.oeffnungsmarker(dict(finalist=dict(regeln=[ks, kv])), "2026-11-01T07:00:00Z", "Reto: öffnen"), open(os.path.join(r, v.OEFFNUNG), "w"))
        u.jetzt = T(2028, 10, 16, 6); abbruch(lambda: v.schluss(r, l, "B", DS, u), "beendet_ohne_urteil")                # direkter Schlussaufruf sichert die Öffnung zuerst
        assert status(l, "B") == status(l, "C") == "beendet_ohne_urteil" and status(l, "A") == "aktiv"
    finally:
        shutil.rmtree(d)


def test_veroeffentlichen():
    """G9-02 B / T9-06 / T9-18: der ganze Weg mit einem lokalen Git-Ziel. Aufnahme, Buchung, Commit und Push, neuer Checkout,
    Fortsetzung, Stopp und Öffnung; Konflikt zweier Fortsetzungen; Pushfehler mit Bergung; Wiederaufnahme einer Reservierung."""
    d = tempfile.mkdtemp()
    try:
        fern = os.path.join(d, "fern.git"); git(d, "init", "-q", "--bare", "-b", "claude/lernen", fern)
        saat = os.path.join(d, "saat"); git(d, "clone", "-q", fern, saat); open(os.path.join(saat, "index.json"), "w").write("{}")
        git(saat, "add", "-A"); git(saat, "commit", "-qm", "Anfang"); git(saat, "push", "-q", "origin", "HEAD:refs/heads/claude/lernen")
        r = os.path.join(d, "vorwaerts"); os.makedirs(r); json.dump(dict(modus="offen", freigabe="Test"), open(os.path.join(r, v.FREIGABE), "w"))
        class GitStub(Stub):                                                            # Journalordner mit echtem Git, der Rest vorgegeben
            def journal_bekannt(self, pfad): return v.Umgebung.journal_bekannt(self, pfad)
            def veroeffentlicht_stand(self, logdir): return v.Umgebung.veroeffentlicht_stand(self, logdir)
        def checkout(name):                                                             # wie in der Action: frischer Arbeitsbaum des Zweigs, HEAD gelöst
            p = os.path.join(d, name); git(d, "clone", "-q", fern, p); git(p, "checkout", "-q", "--detach", "origin/claude/lernen"); return p, os.path.join(p, "vorwaerts")
        def fern_datei(n):
            return subprocess.run(["git", "-C", fern, "show", f"claude/lernen:vorwaerts/{n}"], capture_output=True).stdout
        u = GitStub(finde={"T1": [{}]}); uhr = lambda: u.jetzt + datetime.timedelta(minutes=3)      # noqa: E731
        # Lauf 1: Aufnahme; Lauf 2 in neuem Checkout: Buchung
        a1, l1 = checkout("a1"); lege(r, reg()); v.lauf(r, l1, DS, u); e = v.veroeffentliche_mit_vermerk(l1, uhr)
        assert e["gepusht"] and e["vermerk"]["gepusht"] and fern_datei("status.jsonl") == open(os.path.join(l1, "status.jsonl"), "rb").read()
        a2, l2 = checkout("a2"); u.f["T1"][0]["2026-10-13"] = (1.5, "2026-10-15"); u.jetzt = T(2026, 10, 14, 4, 12)
        z = v.lauf(r, l2, DS, u); assert z["aktiv"] == ["T1"] and z["neue_zeilen"] == 1
        vor_push = open(os.path.join(l2, v.VERMERK)).read(); e = v.veroeffentliche_mit_vermerk(l2, uhr)
        vm = v.journal_lesen(os.path.join(l2, v.VERMERK))[0]
        assert vm[-1]["gepusht_utc"] == "2026-10-14T04:15:00Z" and vm[-1]["zeilen"]["handelsbuch"] == 1 and vm[-1]["kopf"] == e["kopf"] and vor_push in open(os.path.join(l2, v.VERMERK)).read()
        assert v.veroeffentlichen(l2, uhr)["gepusht"] is False                                                           # nichts Neues
        # T9-06: zwei Fortsetzungen desselben Anfangs. Die erste wird veröffentlicht (Stopp); die zweite darf nicht gewinnen.
        a3, l3 = checkout("a3"); a4, l4 = checkout("a4")
        alt = open(os.path.join(r, "T1.json")).read(); lege(r, reg(mechanismus="anders")); u.jetzt = T(2026, 10, 15, 4, 12); v.lauf(r, l3, DS, u)
        assert status(l3, "T1") == "gestoppt"; v.veroeffentliche_mit_vermerk(l3, uhr); stand_fern = {n: fern_datei(n) for n in ("status.jsonl", "handelsbuch.jsonl", "laeufe.jsonl")}
        open(os.path.join(r, "T1.json"), "w").write(alt); u.f["T1"][0]["2026-10-28"] = (1.6, "2026-10-30"); u.jetzt = T(2026, 10, 29, 4, 12)
        z = v.lauf(r, l4, DS, u); assert z["aktiv"] == ["T1"]                                                           # der veraltete Checkout weiss nichts vom Stopp …
        abbruch(lambda: v.veroeffentliche_mit_vermerk(l4, uhr), "Anhängeregel verletzt")                                  # … und kann seine Fortsetzung nicht veröffentlichen
        assert {n: fern_datei(n) for n in stand_fern} == stand_fern and os.path.exists(os.path.join(l4, "handelsbuch.jsonl"))   # Stopp bleibt massgebend; lokale Ausgabe liegt zur Bergung
        a5, l5 = checkout("a5"); z = v.lauf(r, l5, DS, u); assert z["aktiv"] == [] and status(l5, "T1") == "gestoppt"
        # ein fremder Commit ausserhalb von vorwaerts/ (z. B. die Suche) stört nicht: der eigene Stand wird dahinter gesetzt
        lege(r, reg(kennung="T2", vorgaenger=["T1"], registriert="2026-10-29", letzter_einstieg="2028-10-20", schlusstag="2028-11-01")); u.aufn["T2.json"] = (AUF, T(2026, 10, 29, 4)); u.f["T2"] = [{"2026-10-28": (1.6, "2026-10-30")}]
        z = v.lauf(r, l5, DS, u); assert z["aktiv"] == ["T2"]
        open(os.path.join(saat, "index.json"), "w").write('{"suche": 1}'); git(saat, "pull", "-q", "origin", "claude/lernen"); git(saat, "commit", "-qam", "Suchlauf"); git(saat, "push", "-q", "origin", "HEAD:refs/heads/claude/lernen")
        e = v.veroeffentliche_mit_vermerk(l5, uhr); assert e["gepusht"] and fern_datei("handelsbuch.jsonl") == open(os.path.join(l5, "handelsbuch.jsonl"), "rb").read()
        assert subprocess.run(["git", "-C", fern, "show", "claude/lernen:index.json"], capture_output=True, text=True).stdout == '{"suche": 1}'
        # T9-18: Pushfehler. Nichts geht verloren; nach Behebung wird dieselbe Ausgabe veröffentlicht.
        a6, l6 = checkout("a6"); u.f["T2"][0]["2026-11-20"] = (1.7, "2026-11-24"); u.jetzt = T(2026, 11, 23, 4, 12); v.lauf(r, l6, DS, u)
        git(a6, "remote", "set-url", "origin", os.path.join(d, "gibt_es_nicht.git")); lokal = open(os.path.join(l6, "handelsbuch.jsonl"), "rb").read()
        abbruch(lambda: v.veroeffentliche_mit_vermerk(l6, uhr), "Push nach 4 Versuchen gescheitert")
        assert open(os.path.join(l6, "handelsbuch.jsonl"), "rb").read() == lokal and fern_datei("handelsbuch.jsonl") != lokal
        git(a6, "remote", "set-url", "origin", fern); e = v.veroeffentliche_mit_vermerk(l6, uhr); assert e["gepusht"] and fern_datei("handelsbuch.jsonl") == lokal
        # Der Auftrag vom 23.11. hat seinen Vermerk aus dem gelungenen zweiten Versuch
        assert v.veroeffentlicht_utc(v.journal_lesen(os.path.join(l6, v.VERMERK))[0], 2) == "2026-11-23T04:15:00Z"
        # Reservierung, Rechnung scheitert, veröffentlichen; im neuen Checkout kommt inzwischen eine Öffnung dazu: kein Ergebnis mehr
        a7, l7 = checkout("a7"); u.jetzt = T(2028, 11, 2, 4, 12); u.w = dict(fehler="Rechner ausgefallen"); v.lauf(r, l7, DS, u); assert status(l7, "T2") == "reserviert"
        v.veroeffentliche_mit_vermerk(l7, uhr); assert fern_datei("schluss_T2.reserviert.json")
        a8, l8 = checkout("a8"); json.dump(v.oeffnungsmarker(dict(finalist=dict(regeln=["S|X_d5|hoch|xlu|5"])), "2028-11-02T09:00:00Z", "Reto: öffnen"), open(os.path.join(r, v.OEFFNUNG), "w"))
        u.w = stub_werte; u.jetzt = T(2028, 11, 3, 4, 12); v.lauf(r, l8, DS, u)
        assert status(l8, "T2") == "beendet_ohne_urteil" and not os.path.exists(os.path.join(l8, "schluss_T2.json")); os.remove(os.path.join(r, v.OEFFNUNG))
        e = v.veroeffentliche_mit_vermerk(l8, uhr); assert e["gepusht"]
        # veröffentlichte Schlussdatei lokal verändert: Anhängeregel greift auch dort
        a9, l9 = checkout("a9"); open(os.path.join(l9, "schluss_T2.reserviert.json"), "a").write(" "); v.anhaengen(os.path.join(l9, "laeufe.jsonl"), [dict(n=1)])
        git(a9, "add", "-A"); git(a9, "commit", "-qm", "lokal"); a10, l10 = checkout("a10"); v.anhaengen(os.path.join(l10, "laeufe.jsonl"), [dict(n=2)]); v.veroeffentlichen(l10, uhr)
        abbruch(lambda: v.veroeffentlichen(l9, uhr), "Anhängeregel verletzt")
        # Journale im entfernten Stand: nie gekürzt über die ganze Geschichte
        hist = subprocess.run(["git", "-C", fern, "log", "--format=%H", "claude/lernen"], capture_output=True, text=True).stdout.split()
        for n in ("status.jsonl", "handelsbuch.jsonl", "laeufe.jsonl", v.VERMERK):
            vers = [subprocess.run(["git", "-C", fern, "show", f"{c}:vorwaerts/{n}"], capture_output=True).stdout for c in reversed(hist)]
            assert all(b.startswith(a_) for a_, b in zip(vers, vers[1:])), n
    finally:
        shutil.rmtree(d)


# ---------------------------------------------------------------------------------------------- mit Daten (nur Discovery)
def test_mit_daten():
    """Nur Discovery. (1) Regelkalender gegen die echten Handelstage. (2) Siegel und Gleichheit der Auslöser bei
    abgeschnittenen Reihen. (3) Ein gedachter Strang über 2019/2020: Dispatcher, eigener Prozess je Modus, gekürzte Kurse,
    Aufträge nach der Uhr, Schlussauswertung gegen die Mehrrendite der Suche."""
    import numpy as np, pandas as pd
    import suchmaschine as sm
    echt = {t.date() for t in sm.KAL if t >= pd.Timestamp("2002-01-01")}
    regel = set(v.nyse_handelstage(D(2002, 1, 1), D(2020, 12, 31)))
    sonder = {D(2004, 6, 11), D(2007, 1, 2), D(2012, 10, 29), D(2012, 10, 30), D(2018, 12, 5)}                    # Staatstrauer, Hurrikan Sandy
    print(f"   Kalender 2002–2020: echt {len(echt)}, Regel {len(regel)}, nur Regel {sorted(regel - echt)}, nur echt {sorted(echt - regel)}")
    assert regel - echt <= sonder and not (echt - regel)
    S = "2019-12-31"
    voll = v.motor_laden("2020-12-31"); kurz = v.motor_laden(S)
    for m in (voll, kurz):
        assert all(d.index.max() <= m.STICHTAG for d in m.kurse.values()) and m.acwi.index.max() <= m.STICHTAG
    namen = sorted(n for n in voll.ind if n in kurz.ind); rng = np.random.default_rng(3); stich = rng.choice(len(namen), 400, replace=False)
    gepr, abw, rand = 0, [], []
    for i in stich:
        n = namen[i]
        for art in (("hoch",) if n in voll.EREIGNIS else ("hoch", "tief", "sprung_auf", "sprung_ab")):
            a = sm.ereignisse(sm.ind[n][0], art, n in sm.EREIGNIS); b = voll.ereignisse(voll.ind[n][0], art, n in voll.EREIGNIS)
            assert a.equals(b), n
            c = kurz.ereignisse(kurz.ind[n][0], art, n in kurz.EREIGNIS)
            if not b[b < pd.Timestamp(S)].equals(c[c < pd.Timestamp(S)]):
                abw.append((n, art))
            elif not b[b <= pd.Timestamp(S)].equals(c):
                rand.append(n)
            gepr += 1
    print(f"   Gleichheit bei abgeschnittenen Reihen: {gepr} Paare geprüft, abweichend {len(abw)} {abw[:5]}; nur am letzten Tag abweichend {len(rand)}")
    assert not abw and all(n.startswith(v.UNTERTAEGIG) for n in rand), rand
    # G9-01 B / G9-07 / T9-03 / T9-14: Mängel der Regeln am echten Suchraum
    binaer = sorted(voll.EREIGNIS)[0]; stetig = sorted(n for n in voll.ind if n.endswith("_d1") and n[:-3] + "_d5" in voll.ind)[0]
    X = lambda ind, art="hoch", ziel="xlu": dict(indikator=ind, art=art, ziel=ziel, h=5)       # noqa: E731
    assert v.struktur_pruefen(voll, [X(binaer), X(stetig, "tief", "xle")]) == []
    for art in ("tief", "sprung_auf", "sprung_ab"):
        f = v.struktur_pruefen(voll, [X(binaer, art)]); assert len(f) == 1 and "0/1-Reihe" in f[0], f
        assert voll.ereignisse(voll.ind[binaer][0], art, True).equals(voll.ereignisse(voll.ind[binaer][0], "hoch", True))     # darum: dieselben Ereignisse
    assert "Grundreihe" in v.struktur_pruefen(voll, [X(stetig), X(stetig[:-3] + "_d5", "hoch", "xle")])[0]
    assert "Familie S" in v.struktur_pruefen(voll, [X(stetig, "hoch", "abc")])[0] and "nicht im Suchraum" in v.struktur_pruefen(voll, [X("gibt_es_nicht_d1")])[0]
    print(f"   Struktur am echten Suchraum: 0/1-Reihe {binaer} nur «hoch»; zwei Varianten von {stetig[:-3]} abgewiesen")
    # (3) gedachter Strang
    tab = {(e["indikator"], e["art"]): e for e in sm.ereignis_tabelle() if e["fam"] == "S"}
    def tage_in(e):
        p = e["pos"][e["pos"] < len(sm.KAL)]; t = sm.KAL[p]; return t[(t > "2019-03-01") & (t < "2020-10-01")]
    kand = [(k, e) for k, e in sorted(tab.items()) if not k[0].startswith(v.UNTERTAEGIG) and 8 <= len(tage_in(e)) <= 40]
    (ind, art), e = kand[len(kand) // 2]; ziel, h = "xlu", 5
    x, fristen = sm.ind[ind]; tg = sm.ereignisse(x, art, ind in sm.EREIGNIS); tg = tg[tg > "2019-01-02"]
    pos = sm.einstieg(sm.KAL, tg, fristen); ein = [(str(t.date()), str(sm.KAL[p].date()), int(p)) for t, p in zip(tg, pos) if 0 <= p < len(sm.KAL) and sm.KAL[p] <= pd.Timestamp("2020-11-30")]
    wahl = [ein[0]]
    for q in ein[1:]:
        if q[2] - wahl[-1][2] >= 25 and len(wahl) < 3:
            wahl.append(q)
    d, r, l = ordner()
    try:
        kopf = v._git("rev-parse", "HEAD"); echt_code = bool(kopf) and v._git("status", "--porcelain", "--untracked-files=no") == ""
        R = reg(kennung="GEDACHT", registriert="2019-01-02", regeln=[dict(indikator=ind, art=art, ziel=ziel, h=h)], letzter_einstieg="2020-11-30",
                schlusstag="2020-12-30", code_commit=kopf if echt_code else CC)
        lege(r, R)
        daten = sys.argv[1].replace("file://", "")
        class Echt(v.Umgebung):                                                        # echte Prozesse und Kursdateien; Uhr und Git vorgegeben
            jetzt = T(2019, 1, 2, 10, 0)
            def uhr(self): return self.jetzt
            def aufnahme(self, pfad): return AUF, T(2019, 1, 2, 9, 0)
            def geaendert_seit(self, pfad, commit): return []
            def ist_vorfahr(self, a, b): return True
            def code_dir(self, commit): return v.Umgebung.code_dir(self, commit) if echt_code else v.HIER   # eigener Arbeitsbaum des Commits
            def daten_pruefen(self, ds): return []
            def marker_historie(self, ordner): return []
            def journal_bekannt(self, pfad): return False
            def veroeffentlicht_stand(self, logdir): return False
        u = Echt(daten_dir=daten, arbeit=os.path.join(d, "arbeit")); os.makedirs(u.arbeit)
        z = L(r, l, u); assert z["aktiv"] == ["GEDACHT"] and not z["fehler"], z["fehler"]
        for b_, e_, p_ in wahl:                                                       # Lauf jeweils am Morgen des Einstiegstags: dieser Auslöser ist rechtzeitig
            u.jetzt = T.fromisoformat(e_ + "T06:00:00"); z = L(r, l, u); assert not z["fehler"], z["fehler"]
        gek = open(os.path.join(u.arbeit, "basis", "kurse", "acwi_d.csv")).read().strip().split("\n")[-1][:10]
        assert gek <= "2020-12-31"
        buch = v.journal_lesen(os.path.join(l, "handelsbuch.jsonl"))[0]; auf = [q for q in buch if q["ereignis"] == "auftrag"]
        assert all(q["beobachtung"] > "2019-01-02" for q in buch)
        assert sorted(q["einstieg"] for q in auf) == sorted({w_[1] for w_ in wahl}), (auf, wahl)
        for q in auf:                                                                 # die Sitzungen des Auftrags sind die echten Handelstage
            p_ = next(w_[2] for w_ in wahl if w_[1] == q["einstieg"]); assert q["sitzungen"] == [str(t.date()) for t in sm.KAL[p_:p_ + h]]
        alle = {q["beobachtung"]: q["einstieg"] for q in buch if q["ereignis"] in ("auftrag", "kein_auftrag")}
        soll = {b_: e_ for b_, e_, _ in ein if e_ <= wahl[-1][1] or b_ < wahl[-1][1]}
        assert all(alle.get(b_) == e_ for b_, e_ in soll.items() if b_ in alle) and len(alle) >= len(wahl)
        u.jetzt = T(2020, 12, 31, 6, 0); z = v.lauf(r, l, DS, u); assert not z["fehler"], z["fehler"]              # fälliger Abschluss über den Betriebsweg
        erg = json.load(open(os.path.join(l, "schluss_GEDACHT.json")))
        assert erg["vollstaendig"] and erg["auswertbar_n"] == len(wahl) and erg["verfallen_n"] == 0 and len(erg["manifest"]["acwi"]) == 64
        mr = sm.FAM["S"]["mr"][(ziel, h)]
        for q in erg["einzeln"]:
            p_ = next(w_[2] for w_ in wahl if w_[1] == q["einstieg"])
            assert abs(q["netto_pp"] - (mr[p_] - sm.KOSTEN)) < 1e-6, (q, mr[p_] - sm.KOSTEN)
        cd_ = u.code_dir(R["code_commit"]); assert cd_ and (not echt_code or (cd_ != v.HIER and os.path.exists(os.path.join(cd_, "suchmaschine.py"))))
        print(f"   gedachter Strang {ind} {art} → {ziel}: {len(ein)} Auslöser, {len(auf)} Aufträge (Läufe am Einstiegstag), Schlussauswertung gleich der Suche; "
              + (f"Code aus eigenem Arbeitsbaum des Commits {kopf[:12]}" if echt_code else "Code des Arbeitsordners (Stand nicht eingecheckt)"))
    finally:
        shutil.rmtree(d); v._git("worktree", "prune")


if __name__ == "__main__":
    mit = os.environ.get("PS_VORWAERTS_DATENTEST") == "1"
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and (mit or name != "test_mit_daten"):
            fn(); print("ok", name)
    print("alle Tests bestanden" + ("" if mit else " (ohne Datentest)"))
