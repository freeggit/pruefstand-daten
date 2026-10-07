# Vorwärtsregister (Verfassung V3.15, E32)

Das Register wird explorativ geführt: Ein Strang ergibt ein beschreibendes Papierergebnis, keine Aussage mit 5% Fehlalarm.
Je Strang eine Datei `<Kennung>.json`. Massgebender Beginn ist der Tag, an dem das Register die Datei erstmals auf `main` sieht.
Eine registrierte Datei wird nie mehr geändert: Jede Änderung stoppt den Strang endgültig, auch wenn die alte Datei zurückkehrt und auch wenn die Änderung nur in der Historie von `main` steht.
Jede Registrierung gibt Reto einzeln frei. Das Handelsbuch liegt auf dem Zweig `claude/lernen` im Ordner `vorwaerts/`.

## Steuerdateien in diesem Ordner

| Datei | Inhalt | Fehlt die Datei |
|---|---|---|
| `freigabe.json` | `{modus, freigabe, seit}`; modus `gesperrt`, `uebung` (nur Übungsstränge) oder `offen` | gesperrt |
| `bestaetigung_geoeffnet.json` | `{geoeffnet_utc, regeln, freigabe}`; Regeln des Finalisten der Bestätigung (E32f). Erzeugt mit `vorwaerts.oeffnungsmarker` aus dem Ergebnis von `auswahl.py`. Ein ungültiger Marker blockiert jeden Lauf, auch im leeren und gesperrten Register. Jede Fassung, die je auf `main` lag, wird als Öffnung gespeichert und gilt weiter, auch wenn die Datei später fehlt. | keine Öffnung |
| `dispatcher_freigaben.json` | `{freigaben: [{sha256, freigabe}]}`; freigegebene Stände von `vorwaerts.py`, solange Stränge laufen | jeder Wechsel bricht ab |
| `sonderschliessungen.json` | `{tage: [{tag, quelle, freigabe}]}`; ausserordentliche Schliessungen der Börse | keine |

Unter `gesperrt` und `uebung` wird eine nicht zugelassene Registrierung weder aufgenommen noch abgewiesen. Laufende Stränge werden in jedem Modus weitergeführt.

## Felder der Registrierung

| Feld | Inhalt |
|---|---|
| kennung | gleich dem Dateinamen ohne `.json`; Buchstaben, Ziffern, `_` und `-` |
| art | `strang`, `typ_k` (Haltedauer 60, 120, 250) oder `uebung` (wird nie ausgewertet, belegt keinen Platz) |
| registriert | Tag der Registrierung (JJJJ-MM-TT); höchstens 3 Tage vor dem Beginn, nie danach |
| regeln | 1 bis 5 Regeln `{indikator, art, ziel, h}`; je Grundreihe und je Ziel höchstens eine; gleich gewichtet. Der Indikator muss bei der Aufnahme im Suchraum stehen, das Ziel zur Familie S gehören. Für 0/1-Reihen (`…_stand`) gilt nur `hoch`. Diese Punkte prüft der Signalrechner des Strangs vor der Aufnahme; ein Mangel führt zur Abweisung und belegt keinen Platz. |
| kosten_pp | Kosten je Wechsel in Prozentpunkten (heute 0.88); endlich, über 0, höchstens 5 |
| letzter_einstieg | letzter zulässiger Einstiegstag (ein Handelstag); sein Haltefenster läuft vor dem Schlusstag aus |
| schlusstag | letzter Tag des Strangs; höchstens 5 Jahre nach dem Beginn. Ausgewertet wird ab dem Folgetag. |
| min_ereignisse | ganze Zahl, mindestens 10 |
| vorpruefung | `{jahresschwankung_pp, beleg}` aus der Discovery; daraus folgt die Mindestdauer (40% gegen 3 Prozentpunkte pro Jahr netto). Tagesregel: Dauer in Tagen mindestens Planungsjahre × 365.25, aufgerundet, minus 3 Tage Vorlauf. |
| code_commit | vollständige Commit-Kennung (40 Zeichen), die bei der Aufnahme schon auf `main` lag. Der Code dieses Commits prüft die Registrierung und rechnet Kalender, Auslöser, Frist, Sperrfrist, Auftragsentscheid, Kursaufbereitung, Kosten und Aggregation dieses Strangs. |
| freigabe | `{wortlaut, datum, kennung}`: Wortlaut und Datum (JJJJ-MM-TT) der Freigabe von Reto; `kennung` ist genau die Kennung dieses Strangs |
| mechanismus | ökonomische Begründung in einem Satz |
| vorgaenger | nur wenn dieselbe Regel schon in einem früheren Strang stand: genau die Kennungen dieser Stränge |

## Regeln des Handelsbuchs

- Jeder Auslöser erhält beim ersten Erkennen genau einen Entscheid: `auftrag` oder `kein_auftrag` mit Grund.
- Je Zeile drei Zeiten: Start des Laufs, Erkennung (Uhr nach der Signalrechnung), Speicherung. Nach jedem gelungenen Push vermerkt der Lauf die Zeit und die Länge des Handelsbuchs in `veroeffentlicht.jsonl`. Das ist die Uhr des Rechners der Aktion, keine von GitHub beglaubigte Zeit.
- Ein Auftrag gilt nur, wenn er vor 13:30 UTC des Einstiegstags erkannt und gespeichert war und der Push vor dieser Zeit gelungen ist; sonst verfällt er bei der Schlussauswertung. Fehlt der Vermerk, zählt die Zeit, zu der ein späterer Lauf die Zeile im veröffentlichten Stand sah.
- Kein Auftrag innerhalb von max(10, h) Handelstagen nach dem vorigen Auftragsversuch derselben Regel (Sperrfrist). Jeder im Buch stehende Auftrag löst die Sperrfrist aus, auch wenn er später verfällt; so wird kein früherer Entscheid nachträglich umgedeutet.
- Der Auftrag hält die erwarteten Handelssitzungen und den Ausstieg fest. Fehlt später eine Kurszeile im Ziel oder im Vergleichsindex, oder fehlt eine Datei, ist der Auftrag «nicht auswertbar»; nichts wird verschoben. Es gibt dann keinen Jahresertrag.
- Spätere Änderungen der Quelle werden als `revision` vermerkt und ändern keinen Entscheid.
- Höchstens 3 Plätze für echte Stränge (aktiv oder reserviert); ein weiterer wird abgewiesen und rückt nicht nach. Das ist eine Aufwandsgrenze, keine Fehlerkontrolle.
- Dieselbe Regel läuft nie in zwei Strängen zugleich. Ist die Bestätigung geöffnet, enden Stränge mit einer Regel des Finalisten ohne Urteil, und neue werden abgewiesen.
- Es gibt keine Zwischenstände. Nach dem Schlusstag wartet das Register höchstens 30 Tage, bis jede benötigte Kursdatei (Ziele und Vergleichsindex) bis zu ihrem letzten Ausstieg reicht, reserviert dann einmal (Aufträge, Zeitnachweise, Datenstand, Prüfsummen der Kursdateien) und rechnet genau ein Ergebnis. Ein Wiederanlauf setzt nur dieselbe Instanz fort.

## Dateien auf `claude/lernen/vorwaerts/`

| Datei | Inhalt |
|---|---|
| `status.jsonl` | massgebendes Journal: Statuswechsel, Öffnungen, Dispatcher-Wechsel, Reparaturen |
| `veroeffentlicht.jsonl` | je gelungenem Push: Zeit danach, Länge der Journale, Commit |
| `handelsbuch.jsonl` | Aufträge, Nicht-Aufträge, Revisionen, Ausfälle; wird nur verlängert |
| `laeufe.jsonl` | je Lauf eine Zeile (Datenstand, Paketversionen, Zahlen, Fehler) und das Siegel: Länge und Prüfsumme der anderen Journale |
| `stand.json` | Ansicht des Stands; wird nie gelesen |
| `schluss_<Kennung>.reserviert.json`, `schluss_<Kennung>.json` | Reservierung und Ergebnis der Schlussauswertung |

Schutz der Journale: Sie werden nur verlängert, nie gekürzt. Jeder Lauf prüft sie zuerst gegen das Siegel des letzten Laufs; ein fehlendes, geleertes, gekürztes oder verändertes Journal bricht den Lauf ab. Ein abgerissenes Ende nach einem Schreibabbruch wird als ungültig vermerkt, nicht gelöscht. Veröffentlicht wird nur der Ordner `vorwaerts/`: Der Stand auf GitHub muss ein Anfangsstück des eigenen sein, sonst bricht die Veröffentlichung ab und die lokale Ausgabe wird als Artefakt der Aktion gesichert.

Rechenumgebung: Der Signalrechner erhält keine `PS_`-Variablen ausser den beiden Datenbasen. Python, numpy und pandas werden je Strang bei der Aufnahme festgehalten; eine Abweichung steht im Laufprotokoll. Eine reservierte Schlussauswertung wird nur mit derselben Umgebung fortgesetzt. Die laufenden Signaldaten sind mit den drei Commit-Kennungen etikettiert, nicht einzeln geprüft; das folgt mit dem Zuschnitt der Quellen vor dem ersten echten Strang.

Schutz des Siegels, genau gefasst: Der Signalrechner erhält eine Kopie der Daten, deren Kursdateien nur Zeilen bis 31.12.2020 enthalten. Das ist ein Schutz des Recheninputs, keine vollständige Zugriffssperre. Der Zuschnitt der Signalquellen auf die registrierten Reihen folgt vor dem ersten echten Strang.
