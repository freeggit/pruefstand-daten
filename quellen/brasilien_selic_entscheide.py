#!/usr/bin/env python3
import gzip
import io
import json
import os
import urllib.request
from datetime import date

ID = "brasilien_selic_entscheide"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)

# BCB SGS Serie 432 = Selic-Zielsatz (Meta Selic, % p.a.), taeglich; API begrenzt Fenster auf 10 Jahre
URL = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados?formato=json"
       "&dataInicial={a}&dataFinal={b}")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def gzip_write(path, rows, fmt):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for d, v in rows:
            t.write(fmt % (d, v))
        t.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    heute = date.today()
    raw = {}
    for a, b in ((1999, 2008), (2009, 2018), (2019, heute.year)):
        end = "31/12/%d" % b if b < heute.year else heute.strftime("%d/%m/%Y")
        for r in fetch(URL.format(a="01/01/%d" % a, b=end)):
            d, m, y = r["data"].split("/")
            raw["%s-%s-%s" % (y, m, d)] = float(r["valor"])
    rows = sorted(raw.items())
    if len(rows) < 500:
        raise SystemExit("zu wenige Daten")
    flags, prev = [], None
    for d, v in rows:
        flags.append((d, 1 if prev is not None and v != prev else 0))
        prev = v
    gzip_write(os.path.join(OUT_DIR, "aenderungstage.csv.gz"), flags, "%s,%d\n")
    gzip_write(os.path.join(OUT_DIR, "ziel.csv.gz"), rows, "%s,%s\n")
    q = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432"
    meta = {
        "aenderungstage": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am ersten Tag, an dem ein geaenderter Selic-Zielsatz (BCB SGS 432) gilt, sonst 0. Kalendertaeglich. Copom gibt den Entscheid am Abend des Vortags (Sitzungstag) bekannt.",
            "quelle_url": q,
            "verdichtung": "keine (Aenderungsindikator aus Tagesreihe abgeleitet)",
            "publikation": "taeglich (Copom-Entscheid am Vorabend des Wirksamkeitstags oeffentlich; Quelle: BCB Copom-Kommunikation)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
        "ziel": {
            "einheit": "% p.a.",
            "beschreibung": "Selic-Zielsatz (Meta Selic), BCB SGS 432, Wirksamkeitsdatum",
            "quelle_url": q,
            "verdichtung": "keine",
            "publikation": "taeglich (Zielsatz mit Copom-Entscheid am Vortag bekannt)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
            "status": "ruhend",
        },
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
