#!/usr/bin/env python3
"""CVM Brasilien, Dados Abertos: registrierte oeffentliche Aktienemissionen je Tag.

Reihe:
  aktien_angebote  Anzahl oeffentlicher Aktienangebote (Erst- und Folgeemissionen,
                   primaer, sekundaer, gemischt), deren Registrierung die CVM an diesem
                   Tag erteilt hat.

Quellen (offenes Datenportal dados.cvm.gov.br, CKAN, ohne Login, ohne Schluessel, ODbL):
  oferta_distribuicao.csv     Regime ICVM 400 (bis 2022): Zeilen mit Data_Registro_Oferta
                              und Tipo_Ativo Aktien (ON/PN). Ein Angebot = Numero_Processo +
                              Registrierungstag (ON- und PN-Zeilen zusammengefasst).
                              Nicht gezaehlt: ICVM 476 (eingeschraenkte Angebote ohne
                              Registrierung) und ICVM 400 «dispensada de registro».
  oferta_resolucao_160.csv    Regime RCVM 160 (ab 2.1.2023): Valor_Mobiliario «Ações» mit
                              Data_Registro; ein Angebot = Numero_Requerimento.
Datum = Registrierungstag (Data_Registro_Oferta bzw. Data_Registro). 0 an Tagen ohne
Registrierung, ab 1990-01-01 (1989 nur 5 Datensaetze, Abdeckung unvollstaendig) bis
zum letzten Aktualisierungstag der Datei (hoechstens gestern, UTC).
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

ID = "cvm_ofertas_acoes"
ZIP_URL = "https://dados.cvm.gov.br/dados/OFERTA/DISTRIB/DADOS/oferta_distribuicao.zip"
PKG_URL = "https://dados.cvm.gov.br/api/3/action/package_show?id=oferta-distrib"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
ERSTER_TAG = datetime.date(1990, 1, 1)


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
    lm = [r.get("last_modified") or r.get("metadata_modified") or ""
          for r in pkg["resources"] if r.get("url", "").endswith("DADOS/oferta_distribuicao.zip")]
    stand = datum(lm[0]) if lm and lm[0] else None
    if stand is None:
        stand = datum(pkg.get("metadata_modified") or "")
    if stand is None:
        raise RuntimeError("Aktualisierungsdatum fehlt")
    letzte = min(stand, heute - datetime.timedelta(days=1))
    z = zipfile.ZipFile(io.BytesIO(fetch(ZIP_URL)))
    angebote = set()
    t400 = z.read("oferta_distribuicao.csv").decode("latin-1")
    for x in csv.DictReader(io.StringIO(t400), delimiter=";"):
        if not x["Tipo_Ativo"].strip().upper().startswith("A"):
            continue
        if "AÇ" not in x["Tipo_Ativo"].upper() and "AÇÔ" not in x["Tipo_Ativo"].upper():
            continue
        if not x["Rito_Oferta"].startswith("ICVM 400 (com registro)"):
            continue
        d = datum(x["Data_Registro_Oferta"])
        if d:
            angebote.add(("400", x["Numero_Processo"].strip(), d))
    t160 = z.read("oferta_resolucao_160.csv").decode("latin-1")
    for x in csv.DictReader(io.StringIO(t160), delimiter=";"):
        if not x["Valor_Mobiliario"].strip().startswith("Aç"):
            continue
        d = datum(x["Data_Registro"])
        if d:
            angebote.add(("160", x["Numero_Requerimento"].strip(), d))
    zaehl = {}
    for _, _, d in angebote:
        if ERSTER_TAG <= d <= letzte:
            zaehl[d] = zaehl.get(d, 0) + 1
    if len(zaehl) < 300:
        raise RuntimeError("zu wenige Angebote: %d" % len(zaehl))
    rows, d = [], ERSTER_TAG
    while d <= letzte:
        rows.append((d.isoformat(), zaehl.get(d, 0)))
        d += datetime.timedelta(days=1)
    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "aktien_angebote.csv.gz"), rows)
    meta = {"aktien_angebote": {
        "einheit": "Anzahl Angebote",
        "beschreibung": "CVM Brasilien: Anzahl oeffentlicher Aktienangebote (Erst- und Folgeemissionen, primaer, "
                        "sekundaer, gemischt), deren Registrierung die CVM an diesem Tag erteilt hat; bis 2022 "
                        "Regime ICVM 400 mit Registrierung (ohne ICVM 476 und ohne Registrierungsbefreiung), ab "
                        "2023 Regime RCVM 160 (automatische Registrierung, damit auch frueher nach ICVM 476 "
                        "gefuehrte Angebote an professionelle Anleger: Regelbruch 2.1.2023); ON- und PN-Tranchen "
                        "eines Angebots einmal gezaehlt; 0 an Tagen ohne Registrierung; ab 1990",
        "quelle_url": "https://dados.cvm.gov.br/dataset/oferta-distrib",
        "verdichtung": "Summe (Anzahl Angebote je Registrierungstag, Ortszeit Brasilien)",
        "verfuegbar_nach_tagen": 1,
        "revidiert": False,
        "hinweis_revision": "Bestandsdatei, die laufend nachgefuehrt wird; Registrierungstage aendern sich nicht, "
                            "verspaetet erfasste Angebote koennen aber nachtraeglich hinzukommen (Zaehlung kann "
                            "rueckwirkend steigen, nie auf fruehere Tage verschoben).",
        "publikation": "taeglich: die CVM veroeffentlicht erteilte Registrierungen am Registrierungstag im "
                       "Angebotsverzeichnis (sistemas.cvm.gov.br, Ofertas Registradas); der Emittent muss danach "
                       "das Anuncio de Inicio veroeffentlichen (ICVM 400 Art. 52, RCVM 160 Art. 59); die Datei "
                       "auf dados.cvm.gov.br wird taeglich erneuert",
        "status": "aktiv",
    }}
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("ok", ERSTER_TAG, letzte, "Angebote", sum(zaehl.values()), "Tage mit Angebot", len(zaehl))


if __name__ == "__main__":
    main()
