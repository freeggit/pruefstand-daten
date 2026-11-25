#!/usr/bin/env python3
"""CVM Brasilien, Dados Abertos: Beschluesse ueber Aktienrueckkaufprogramme je Tag.

Reihe:
  firmen_rueckkaufbeschluss  Anzahl verschiedener brasilianischer Publikumsgesellschaften
                             (CNPJ), deren Verwaltungsrat an diesem Tag ein Programm zum
                             Rueckkauf eigener Aktien beschlossen hat (Data_Deliberacao).
                             Mehrere Programme derselben Firma am selben Tag zaehlen einmal;
                             reine Verkaufsprogramme (Tipo_Operacao «Venda») nicht gezaehlt.

Quelle: dados.cvm.gov.br, Datensatz cia_aberta-eventos-recompra_acoes (CKAN, ohne Login,
ohne Schluessel, ODbL), Datei cia_aberta_recompra_acoes.csv, taeglich erneuert.
Datum = Beschlusstag; der Beschluss ist nach CVM-Regeln (RCVM 77 Art. 5, vorher ICVM 567
bzw. ICVM 10) sofort als Fato Relevante/Comunicado zu veroeffentlichen. 0 an Tagen ohne
Beschluss, ab 1997-01-01 bis zum Aktualisierungstag der Datei (hoechstens gestern, UTC).
Die CVM traegt Programme bis rund 6 Wochen verspaetet nach; juengste Tage koennen
rueckwirkend steigen.
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

ID = "cvm_recompra_acoes"
ZIP_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/EVENTOS/RECOMPRA_ACOES/DADOS/cia_aberta_recompra_acoes.zip"
PKG_URL = "https://dados.cvm.gov.br/api/3/action/package_show?id=cia_aberta-eventos-recompra_acoes"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
ERSTER_TAG = datetime.date(1997, 1, 1)


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


def datum(s):
    try:
        return datetime.date.fromisoformat(s.strip()[:10])
    except ValueError:
        return None


def main():
    heute = datetime.datetime.utcnow().date()
    pkg = json.loads(fetch(PKG_URL).decode("utf-8"))["result"]
    lm = [r.get("last_modified") or "" for r in pkg["resources"]
          if r.get("url", "").endswith("DADOS/cia_aberta_recompra_acoes.zip")]
    stand = datum(lm[0]) if lm and lm[0] else None
    if stand is None:
        stand = datum(pkg.get("metadata_modified") or "")
    if stand is None:
        raise RuntimeError("Aktualisierungsdatum fehlt")
    letzte = min(stand, heute - datetime.timedelta(days=1))
    z = zipfile.ZipFile(io.BytesIO(fetch(ZIP_URL)))
    t = z.read("cia_aberta_recompra_acoes.csv").decode("latin-1")
    paare = set()
    for x in csv.DictReader(io.StringIO(t), delimiter=";"):
        if x["Tipo_Operacao"].strip().lower().startswith("venda"):
            continue
        d = datum(x["Data_Deliberacao"])
        if d and ERSTER_TAG <= d <= letzte:
            paare.add((x["CNPJ_Companhia"].strip(), d))
    zaehl = {}
    for _, d in paare:
        zaehl[d] = zaehl.get(d, 0) + 1
    if len(zaehl) < 500:
        raise RuntimeError("zu wenige Beschlusstage: %d" % len(zaehl))
    rows, d = [], ERSTER_TAG
    while d <= letzte:
        rows.append((d.isoformat(), zaehl.get(d, 0)))
        d += datetime.timedelta(days=1)
    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "firmen_rueckkaufbeschluss.csv.gz"), rows)
    meta = {"firmen_rueckkaufbeschluss": {
        "einheit": "Anzahl Firmen",
        "beschreibung": "CVM Brasilien: Anzahl verschiedener Publikumsgesellschaften, deren Verwaltungsrat an "
                        "diesem Tag ein Aktienrueckkaufprogramm beschlossen hat (Data_Deliberacao); reine "
                        "Verkaufsprogramme ausgeschlossen, mehrere Programme einer Firma am selben Tag einmal "
                        "gezaehlt; 0 an Tagen ohne Beschluss; ab 1997",
        "quelle_url": "https://dados.cvm.gov.br/dataset/cia_aberta-eventos-recompra_acoes",
        "verdichtung": "Summe (Anzahl Firmen je Beschlusstag, Ortszeit Brasilien)",
        "verfuegbar_nach_tagen": 1,
        "revidiert": False,
        "hinweis_revision": "Bestandsdatei, laufend nachgefuehrt; Beschlusstage aendern sich nicht, die CVM traegt "
                            "Programme aber bis rund 6 Wochen verspaetet ein (Stand 25.11.2026: 530 Eintraege mit "
                            "frueherem Datum als ein zuvor erfasster); juengste Tage koennen rueckwirkend steigen.",
        "publikation": "taeglich: der Rueckkaufbeschluss ist sofort als Fato Relevante bzw. Comunicado ao Mercado "
                       "ueber das IPE-System zu veroeffentlichen (RCVM 77/2022 Art. 5 mit RCVM 44 Art. 3; vorher "
                       "ICVM 567/2015 und ICVM 10/1980); Beschluesse fallen meist nach Handelsschluss, darum 1 Tag",
        "status": "aktiv",
    }}
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("ok", ERSTER_TAG, letzte, "Firmen-Beschluesse", sum(zaehl.values()), "Tage", len(zaehl))


if __name__ == "__main__":
    main()
