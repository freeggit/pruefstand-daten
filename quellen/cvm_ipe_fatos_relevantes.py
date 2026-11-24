#!/usr/bin/env python3
"""CVM Brasilien, Dados Abertos IPE: Ad-hoc-Meldungen boersenkotierter Firmen je Tag.

Reihen:
  fato_relevante      Anzahl «Fato Relevante» (Ad-hoc-Meldung nach Lei 6.404 Art. 157
                      und ICVM 358 / RCVM 44) je Einreichungstag
  comunicado_mercado  Anzahl «Comunicado ao Mercado» (freiwillige Marktmitteilung)
                      je Einreichungstag

Datum = Data_Entrega (Tag der Einreichung im CVM-System ENET; das Dokument ist ab
diesem Tag auf rad.cvm.gov.br und bei der B3 oeffentlich). Neuauflagen eines
Dokuments (RE/RC, hoehere Versao) werden mit dem Original zusammengefasst
(Schluessel Codigo_CVM, Data_Referencia, Assunto, Tipo, Especie) und mit dem
fruehesten Einreichungstag gezaehlt. Wo die Datei nur die Neuauflage fuehrt,
zaehlt deren (spaeterer oder gleicher) Tag: nie frueher als die Veroeffentlichung.
0 an Tagen ohne Meldung innerhalb des abgedeckten Zeitraums; letzter Tag = letzter
Einreichungstag in den Daten (Jahresdatei wird woechentlich erneuert).
Offenes Datenportal dados.cvm.gov.br (CKAN), ohne Login, ohne Schluessel.
"""
import csv
import datetime
import gzip
import io
import json
import os
import time
import urllib.error
import urllib.request
import zipfile

ID = "cvm_ipe_fatos_relevantes"
BASE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_%d.zip"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
ERSTES_JAHR = 2003
KAT = {"fato_relevante": "Fato Relevante", "comunicado_mercado": "Comunicado ao Mercado"}


def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise
            if e.code == 404:
                return None
            last = e
        except Exception as e:  # noqa
            last = e
        time.sleep(2 * (i + 1))
    raise last


def gzip_write(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for d, v in rows:
            t.write("%s,%s\n" % (d, v))
        t.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    heute = datetime.datetime.utcnow().date()
    docs = {k: {} for k in KAT}
    alle_tage = set()
    for jahr in range(ERSTES_JAHR, heute.year + 1):
        raw = fetch(BASE % jahr)
        if raw is None:
            if jahr >= heute.year - 1:
                continue
            raise RuntimeError("Jahresdatei %d fehlt" % jahr)
        z = zipfile.ZipFile(io.BytesIO(raw))
        name = [n for n in z.namelist() if n.endswith(".csv")][0]
        text = z.read(name).decode("latin-1")
        for x in csv.DictReader(io.StringIO(text), delimiter=";"):
            try:
                d = datetime.date.fromisoformat(x["Data_Entrega"].strip()[:10])
            except ValueError:
                continue
            if d.year < ERSTES_JAHR or d >= heute:
                continue
            alle_tage.add(d)
            for k, kat in KAT.items():
                if x["Categoria"].strip() == kat:
                    key = (x["Codigo_CVM"], x["Data_Referencia"], x["Assunto"], x["Tipo"], x["Especie"])
                    alt = docs[k].get(key)
                    if alt is None or d < alt:
                        docs[k][key] = d
    if not alle_tage:
        raise RuntimeError("keine Daten")
    erste, letzte = min(alle_tage), max(alle_tage)
    os.makedirs(OUT_DIR, exist_ok=True)
    for k in KAT:
        zaehl = {}
        for d in docs[k].values():
            zaehl[d] = zaehl.get(d, 0) + 1
        rows, d = [], erste
        while d <= letzte:
            rows.append((d.isoformat(), zaehl.get(d, 0)))
            d += datetime.timedelta(days=1)
        gzip_write(os.path.join(OUT_DIR, k + ".csv.gz"), rows)
    pub = ("taeglich: Fatos Relevantes muessen nach RCVM 44 Art. 3 (vorher ICVM 358) sofort ueber das "
           "CVM-System ENET veroeffentlicht werden und sind am Einreichungstag auf rad.cvm.gov.br und bei der B3 "
           "abrufbar; die Sammeldatei auf dados.cvm.gov.br wird woechentlich erneuert")
    meta = {
        "fato_relevante": {
            "einheit": "Anzahl Meldungen",
            "beschreibung": "CVM Brasilien: Anzahl eingereichter Fatos Relevantes (Ad-hoc-Meldungen) aller "
                            "Emittenten je Tag; Datum = Einreichungstag (Data_Entrega); Neuauflagen mit dem "
                            "Original zusammengefasst; 0 an Tagen ohne Meldung",
        },
        "comunicado_mercado": {
            "einheit": "Anzahl Meldungen",
            "beschreibung": "CVM Brasilien: Anzahl eingereichter Comunicados ao Mercado (Marktmitteilungen) "
                            "aller Emittenten je Tag; Datum = Einreichungstag (Data_Entrega); Neuauflagen mit "
                            "dem Original zusammengefasst; 0 an Tagen ohne Meldung",
        },
    }
    for k in meta:
        meta[k].update({
            "quelle_url": "https://dados.cvm.gov.br/dataset/cia_aberta-doc-ipe",
            "verdichtung": "Summe (Anzahl Dokumente je Einreichungstag, Ortszeit Brasilien)",
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
            "hinweis_revision": "Die Datei fuehrt bei manchen Neuauflagen nur die letzte Version; deren "
                                "Einreichungstag kann spaeter liegen als das Original. Werte verschieben sich "
                                "dadurch hoechstens auf spaetere Tage, nie frueher.",
            "publikation": pub,
            "status": "aktiv",
        })
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("ok", erste, letzte, {k: len(v) for k, v in docs.items()})


if __name__ == "__main__":
    main()
