# pruefstand-daten

Öffentlicher Datenspiegel für das Programm «Börsenvorteil / Prüfstand».
Eine GitHub Action holt täglich öffentliche Reihen und legt sie als CSV unter `data/` ab.
Der Prüfstand liest sie über `raw.githubusercontent.com`.

## Einrichten (einmalig, rund fünf Minuten)
1. Auf github.com anmelden, oben rechts ‹+› → ‹New repository›.
   Name `pruefstand-daten`, Sichtbarkeit **Public** (nötig, damit raw-Links ohne Token gehen), ‹Create repository›.
2. Diese Dateien hochladen: ‹Add file› → ‹Upload files›, den ganzen Inhalt des Zips hineinziehen
   (inklusive des Ordners `.github/workflows/`), ‹Commit changes›.
3. Reiter ‹Actions› → falls gefragt ‹I understand my workflows, go ahead and enable them›.
4. Links ‹Prüfstand Datenspiegel› → rechts ‹Run workflow› → ‹Run workflow›. Nach rund einer Minute liegt `data/` im Repo.
5. Reiter ‹Settings› → ‹Actions› → ‹General› → unter «Workflow permissions» ‹Read and write permissions› wählen, ‹Save›
   (nur nötig, falls Schritt 4 beim Push mit «permission denied» endet).

Danach läuft die Action täglich um 05:15 UTC von selbst.

## Was abgelegt wird
- `data/stooq/<ticker>_us_d.csv` – Tageskurse, Kopf `Date,Open,High,Low,Close,Volume`, ganze Historie
- `data/fred/<SERIE>.csv` – FRED-Reihen, Kopf `observation_date,<SERIE>`
- `data/french/*.csv` – Ken-French-Faktoren und Industrieportfolios (entpackt)
- `data/manifest.json` – Abrufzeit, Zeilenzahl, erstes und letztes Datum je Reihe, Fehler

Ticker in `tickers.txt`, FRED-Serien in `fred_series.txt` – je eine Zeile, ergänzen und einchecken genügt.

## Grundsatz
Das Skript repariert nichts. Kommt eine Reihe nicht sauber an (HTML statt CSV, falscher Kopf, zu wenige Zeilen),
bleibt die alte Datei stehen und `manifest.json` nennt den Fehler. Der Prüfstand liest das Manifest zuerst.
