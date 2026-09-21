# Preset-Abstimmung (AP 6)

Werkzeug: `tools/tune_presets.py` (Modi `population`, `seeds`, `pick`); Kriterien in `fz_stories.py`, Abnahme in `tests/test_preset_stories.py` und `tests/test_stories.py`.

## Grundgesamtheit (Standard-Terminal 4 x 30 Aufträge, Takt 75 s, 20 Auftragsfolgen x 10 Rausch-Ziehungen)

| Kennzahl (Nächstes freies, s je Auftrag) | Mittel |
|---|---|
| Minimum 0, ohne Rauschen | 0,01 |
| Minimum − 1, ohne Rauschen | 0,34 |
| Minimum − 2, ohne Rauschen | 6,97 |
| Minimum − 3, ohne Rauschen | 37,9 |
| Minimum 0, Rauschen 25 % | 0,13 (Bestfit 0,69, Plan + Umdisposition 0,31, starrer Plan 1,38) |

Über 80 Auftragsfolgen (100 Ziehungen, ohne Rauschen eine): Minimum − 1 Mittel 0,40 / Median 0,21; **Minimum − 2 Mittel 7,7 / Median 2,6 / 10.-90. Perzentil 1,4-32 s**; Minimum − 3 Mittel 38 / Median 36.

## Befund und Abweichung vom Plan

Die Kante bei Minimum − 2 ist von Folge zu Folge sehr verschieden (Mittel gut das Dreifache des Medians). Der Plan verlangte für „Zwei zu wenig“ ≥ 5 s (nach dem Mittel);
damit erfüllten nur 14 von 80 Folgen alle Kriterien, und die einzigen, die zusammen mit den anderen Presets trugen, lagen beim 85. Perzentil (28 s gegen Median 2,6 s): nicht typisch.
Die Schwelle liegt jetzt bei **2 s** (und weiter ≥ 10-mal die Wartezeit bei Minimum − 1); „typisch“ wird am Median der Folgen gemessen.

## Gewählt

- Eine gemeinsame Auftragsfolge für alle Presets: **Seed 72** (Minimum 7; Abstand zum Median der Kennzahlen 0,49 im Log, das ist der kleinste von 6 Kandidaten). Gleiches Terminal, nur Flotte und Rauschen wechseln.
- Rausch-Seeds: „Rauschen 25 %“ **37**, „Mit Reserve“ **22** (Ziehung nahe am Median des Abstands Plan minus Nächstes freies; alle 200 geprüften Ziehungen tragen die Geschichte). Die Presets ohne Rauschen brauchen keinen (Standard 3, ohne Wirkung).
- Alle Kriterien halten an der Folge (100 Ziehungen, Bootstrap-Stabilität 100 %), an der Grundgesamtheit und in der gezeigten Ziehung; bei jeder Kennzahl liegt Seed 72 zwischen dem 10. und 90. Perzentil.
