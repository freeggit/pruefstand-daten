# Vorwärtsregister (Verfassung V3.14, E32/E33)

Je Strang eine Datei `<Kennung>.json`. Der Commit auf `main` ist der Zeitstempel der Registrierung.
Eine registrierte Datei wird nie mehr geändert; `vorwaerts.py` stoppt einen Strang, dessen Datei sich ändert.
Jede Registrierung gibt Reto einzeln frei. Das Logbuch liegt auf dem Zweig `claude/lernen` im Ordner `vorwaerts/`.

Felder:

| Feld | Inhalt |
|---|---|
| kennung | gleich dem Dateinamen ohne `.json` |
| art | `strang`, `typ_k` (Haltedauer 60, 120, 250) oder `uebung` (wird nie ausgewertet) |
| registriert | Tag der Registrierung (JJJJ-MM-TT); gewertet werden nur Auslöser mit späterem Beobachtungstag |
| regeln | 1 bis 5 Regeln `{indikator, art, ziel, h}`; je Grundreihe und je Ziel höchstens eine; gleich gewichtet |
| kosten_pp | Kosten je Wechsel in Prozentpunkten (heute 0.88) |
| niveau | 0.05 |
| test | `{name: blocktest, block: 20, ziehungen: 10000, startwert: <ganze Zahl>}` |
| letzter_einstieg | letzter zulässiger Einstiegstag |
| schlusstag | Tag der einzigen Auswertung; alle Haltefenster laufen vorher aus; höchstens 5 Jahre nach der Registrierung |
| min_ereignisse | mindestens 10; darunter lautet das Urteil «unentschieden» |
| vorpruefung | Jahresschwankung in der Discovery, daraus die Dauer, Alternative 3 Prozentpunkte pro Jahr netto |
| freigabe | Wortlaut und Datum der Freigabe von Reto |
| mechanismus | ökonomische Begründung in einem Satz |

Höchstens 3 Stränge laufen gleichzeitig (ohne Übungen). Es gibt keine Zwischenstände und keine Zwischenentscheide.
