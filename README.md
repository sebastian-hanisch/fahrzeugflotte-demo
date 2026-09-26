# Fahrzeugflotte am Kai: Wie viele Fahrzeuge braucht eine Containerbrücke? – Streamlit-Demo

**[→ Demo live ausprobieren](https://sebastianhanisch-fahrzeugflotte-demo.streamlit.app/)**

Interaktive Fall-Demo zur **Fahrzeug-Disposition zwischen Containerbrücke und Stapelblock**: Jede Brücke braucht für jeden Container ein Fahrzeug zur richtigen Zeit. Zu wenige
Fahrzeuge lassen die **Brücke warten** (Kranwartezeit), zu viele kosten Geld. Die **Mindestflotte** ist exakt und in Millisekunden berechenbar. Die Demo beantwortet zwei
Fragen: **Wie knapp ist diese Antwort?** (ein Fahrzeug weniger kostet kaum etwas, zwei weniger schon viel) und **hält sie, wenn die Fahrzeiten schwanken?**

Teil des Portfolios für die Website „Sebastian Hanisch – Operations Research und Machine Learning", Welle 2 der Hafen-Linie (Kran ↔ Block, unter der Kaiplatz-Demo
`robuste-kaiplatz-demo` und der Stapelplanung `stapelplanung-demo`).

## Warum dieses Problem

Die Flottengröße eines Terminals ist eine teure Entscheidung, und die Standardantwort („so viele, wie der Fahrplan nominal braucht") sieht exakt aus: Die kleinste Zahl von
Fahrzeugketten, die alle Aufträge rechtzeitig bedient, ist eine **minimale Wegeüberdeckung** und folgt aus einem maximalen Matching. Was die Antwort nicht sagt: was passiert
knapp darunter, und was passiert, wenn die Fahrzeiten nicht nominal sind. Beides misst die Demo, und beides überrascht: Die Kante ist **scharf**, und der **exakte Plan ist
nicht robust** – die schlichte Regel „Nächstes freies" schlägt ihn bei Streuung deutlich.

## Modell

Ein Kai mit Q Containerbrücken (40 m Abstand), B Stapelblöcken, feste Fahrgeschwindigkeit 6 m/s, Absetzzeit 15 s. Jede Brücke ruft in ihrem Takt (mit Streuung) Container ab; eine
Brücke nimmt höchstens **alle 40 s** einen Container auf. Fahrzeiten werden immer auf die nächste ganze Sekunde **aufgerundet**, nie kaufmännisch gerundet – ein Fahrzeug kommt also nie
früher an, als die exakte Fahrzeit erlauben würde. Fahrzeuge starten „irgendwo" und sind ab
Beginn bereit.

**Kran-Kopplung:** Aufnahme p_j = max(Basis_j, Ankunft des Fahrzeugs), Basis_j = max(Fahrplan-Zeit r_j, p_Vorgänger derselben Brücke + 40 s), **Kranwartezeit** w_j = p_j − Basis_j.
Wartet eine Brücke, verschiebt sich ihre ganze Restfolge: ein Fehler pflanzt sich fort. Zielgröße: Σ w_j, im Bericht je Auftrag in Sekunden. **Rauschen:** jede Fahrt dauert
⌈t · (1 + σ·U)⌉ mit U ∈ [0, 1), nur verspätend; die Faktoren werden je Auftrag vorab gezogen und sind für alle Verfahren identisch (gepaart). Formal im Expander „📐 Mathematische Formulierung".

## Methodik – vier Verfahren und ein exakter Beweis

Flotte = **exaktes Minimum + Abstand** (Regler −4 bis +4), damit der Regler nie wirkungslos ist.

- **Nächstes freies** (Referenz aller Vergleiche): Der Auftrag geht an das Fahrzeug mit der frühesten Ankunft. Für jede Flottengröße definiert.
- **Bestfit**: unter den rechtzeitigen Fahrzeugen das mit der spätesten Ankunft (das knappste), sonst das früheste.
- **Optimalplan starr**: die Fahrzeugketten des Matchings, nominal ohne Wartezeit; im Ablauf starr befolgt. **Erst ab der Mindestflotte** (darunter gibt es keinen solchen Plan; ein Plan aus
  der nominalen Bestfit-Zuordnung war unter Rauschen 3-mal schlechter als der Matching-Plan).
- **Plan + Umdisposition**: wie der Optimalplan, aber ist das geplante Fahrzeug voraussichtlich zu spät, geht der Auftrag an das früheste freie. Trennt Reaktion von Reserve.
- **Mindestflotte mit Beweis** (Tab „Exakt"): n − Matching, belegt durch eine **Knotenüberdeckung** gleicher Größe (Satz von König); `verify_min_fleet_proof` prüft sie ohne Löser.
- **Optimum bei Flottenmangel**: CP-SAT (ein Kreis je Fahrzeug, Kopplung als Maximum-Gleichung, Symmetriebruch, Startlösung aus der besten Regel), Zeitlimit 10 s; ohne Beweis steht
  „nicht bewiesen" mit unterer Schranke, nie ein unbewiesener Wert als Optimum.

Die Hauptansicht zeigt bewusst **keine „beste Strategie" pro Ziehung** (die Rangfolge hängt vom Rauschen ab; mit Rückblick gewählt wäre das irreführend), sondern vier Kennzahlen als
Mittel über 100 Rausch-Ziehungen gegen die Referenz, dazu das Fahrzeug-Bild **einer** Ziehung, ausdrücklich so benannt.

## Befunde (gemessen, keine Behauptungen)

Alle Zahlen stammen aus Simulationen mit diesem Code (Vorab-Messreihe in `hafen-planung/messreihe_fahrzeug/ERGEBNIS.md`, Presets in `tools/PRESET_SWEEP.md`); Standard-Terminal
4 Brücken × 30 Aufträge, Takt 75 s.

| Frage | Befund |
|---|---|
| **Wie knapp ist die Mindestflotte?** | Kranwartezeit je Auftrag von Nächstes freies ohne Rauschen: Minimum − 1 im Mittel 0,4 s (Median 0,2), Minimum − 2 7,7 s (Median 2,6; 10. bis 90. Perzentil 1,4 bis 32 s), Minimum − 3 38 s. Die Kante ist scharf **und** von Auftragsfolge zu Auftragsfolge sehr verschieden. |
| **Ist der exakte Plan robust?** | Nein. Bei der Mindestflotte und bis zu 25 % längeren Fahrten: starrer Optimalplan 1,38 s je Auftrag, Bestfit 0,69, Plan + Umdisposition 0,31, **Nächstes freies 0,13**. Der starre Plan ist in über 90 % der Szenarien schlechter als die schlichte Regel. |
| **Was hilft?** | Reaktion mehr als Reserve: Die Umdisposition holt den größten Teil des Abstands. Zwei Reservefahrzeuge machen „Nächstes freies" wartefrei (in ≥ 95 % der Szenarien null), den starren Plan nicht (er benutzt sie nicht). |
| **Trifft Bestfit das Minimum?** | Fast immer: 3 von 432 großen Instanzen und etwa 1 von 700 bei Takt 75 s verfehlten es, jedes Mal um genau ein Fahrzeug. Gemessen, nicht bewiesen; ein Gegenbeispiel (3 Brücken, 6 Aufträge, Minimum 2, Bestfit 3) steht als Festwert im Test. |
| **Hängt der Befund am Rauschmodell?** | Die Rangfolge (Nächstes freies am besten, starrer Plan nie besser als Bestfit) blieb bei beidseitigem und log-normalem Rauschen gleich. |
| **Exakt?** | Das Matching braucht 2 bis 5 ms (auch bei 240 Aufträgen). CP-SAT beweist das Optimum bei Minimum − 1 bis etwa 40 Aufträge, bei Minimum − 2 nur bis etwa 12; darüber steht „nicht bewiesen". |
| **Presets** | Eine gemeinsame Auftragsfolge (Seed 72), an jeder Kennzahl zwischen dem 10. und 90. Perzentil aller Folgen. Die Schwelle für „Zwei zu wenig" liegt bei 2 s statt 5 s, weil die Kante schief verteilt ist (Median 2,6 s). |

## Ehrliche Grenzen

- Das Rauschen ist **gleichverteilt und nur verspätend**; es sind Annahmen, keine Messungen an einem echten Terminal.
- **Keine Fahrspur-, Kreuzungs- und Staukonflikte**, keine Blockkapazität, kein Laden am Kran; Fahrzeuge starten „irgendwo".
- **Der starre Plan ist bewusst einfach** (er wird nicht angepasst); der Plan mit Umdisposition ist die klügere Ausführung.
- **Fahrzeiten, Takt und Blockverteilung sind Annahmen** ohne Kalibrierung an echten Daten.
- Alle Zahlen sind **Größenordnungen aus einer Simulation, keine Messung an Echtdaten.**

## Design-Entscheidungen und Funde

**Flotte als Abstand zum Minimum.** Ein absoluter Flottenregler wäre je nach Terminal zu groß, zu klein oder wirkungslos; der Abstand zum exakten Minimum ist immer aussagekräftig und macht die
Kante und den Reservebedarf vergleichbar.

**Gemeinsame Zufallszahlen.** Die Rausch-Faktoren sind je Auftrag vorab gezogen und für alle Verfahren gleich, also sind alle Vergleiche gepaart und die Urteile („klar" heißt mehr als zwei
Standardfehler der gepaarten Differenz) trennscharf. Auftrags-Seed und Rausch-Seed sind getrennte Ströme: „Neues Rauschen" ändert die Aufträge nie und umgekehrt.

**Das Urteil kennt drei Zustände und nennt den Verlustanteil.** „Robuster", „kostet Kranwartezeit" und „kein klarer Unterschied", jeweils mit dem Anteil der Szenarien, in denen es
umgekehrt ist, und der Verteilung (besser / gleich / schlechter, Median gegen Mittel).

**Die Kante ist schief verteilt – die Presets sagen es ehrlich.** Der Plan verlangte für „Zwei zu wenig" mindestens 5 s Kranwartezeit je Auftrag (nach dem Mittel 7,7 s). Damit erfüllte nur ein
Sechstel der Auftragsfolgen (14 von 80) dieses Preset, und die beiden, die zugleich alle anderen Presets trugen, lagen bei 27 bis 29 s, weit über dem Median. Jetzt gilt 2 s, und „typisch" wird am Median gemessen.

**Abnahmetests prüfen Schwellen nicht.** Beim Fehler-Einbau überlebten 22 von 27 Mutanten der Preset-Kriterien, weil die echten Daten weit von den Schwellen entfernt liegen; erst Tests mit
künstlichen Werten, bei denen jedes Kriterium einzeln an seiner Schwelle kippt, töteten sie.

**Randfall kleine Terminals.** Bei 2 Brücken und Minimum 2 gibt es kein „Minimum − 2" (weniger als ein Fahrzeug); der Punkt bleibt leer und wird benannt, statt zu stürzen.

## Tests

`python -m pytest tests/ -v` – 298 Tests, rund 3 Minuten. Zusammensetzung:

- **Kern:** Mindestflotte gegen eine unabhängige Brute-Force-Zuordnung auf 120 kleinen geometrischen und 200 Zufallsmatrix-Instanzen (0 Abweichungen), iteratives gegen rekursives Matching,
  Simulation gegen ein **unabhängiges Kontrollmodell** (Abhängigkeitsrekursion statt Auftragsschleife), Invarianten je Lauf, feste Werte der Vorab-Messreihe.
- **Exakt:** CP-SAT gegen Brute Force auf Kleininstanzen, „Optimum ≤ jede Regel", Monotonie in der Flottengröße, Zeitlimit-Pfade, Beweisprüfung mit sechs manipulierten Beweisen.
- **Auswertung:** Kennzahlen, Verteilung, Urteil in drei Zuständen und an der Schwelle, Reservebedarf, Kurven Szenario für Szenario gegen Direktrechnungen.
- **Figuren und Panels:** Balken gegen Fahrten, Marker gegen Wartezeiten, logarithmische Achse mit Hover-Wert, Kennzahlen-Farben am Streamlit-Proto.
- **Presets:** Geschichte in der gezeigten Ziehung, im Mittel der Folge (Bootstrap), über die Grundgesamtheit, typisch je Kennzahl; Kriterien an ihren Schwellen.
- **PDF:** Inhalt Zelle für Zelle, genaue Sonderzeichen (fpdf2 stürzt bei „–", „€" und Emoji ab).
- **End-to-End (AppTest):** Skelett und Footer, jedes Preset, Permalink, alle Regler an Min und Max, 240-Aufträge- und Mini-Terminal, Exakt-Tab, Urteil in allen Zuständen.

Zusätzlich wurde jedes Modul mit **eingebauten Fehlern** geprüft (über 300 Stück); die verbleibenden Überlebenden sind nachweislich gleichwertig.

## Dateistruktur

| Datei | Inhalt |
|---|---|
| `app.py` | Streamlit-Hauptablauf: Presets, Sidebar, Hauptansicht, Terminal-Blick, Kernabschnitt, Methodenvergleich, Texte |
| `fz_constants.py` | Regler-Grenzen, `PRESETS`, Verfahren, Farben, feste Terminalparameter |
| `fz_presets.py` | `SETTING_SPECS`, Permalink (Begrenzen und Einrasten), Presets, zwei Seed-Knöpfe |
| `fz_scenario.py` | Auftragsfolge, Fahrzeitmatrix (aufgerundet), Prüfung einer eigenen Instanz |
| `fz_dispatch.py` | Matching (iterativ), Mindestflotte, Regeln, Simulation mit Kran-Kopplung, Rauschen |
| `fz_exact.py` | Mindestflotte mit Beweis (König), Optimum bei Flottenmangel (CP-SAT), Zeitlimit |
| `fz_evaluation.py` | Kennzahlen, Kurven über Flotte und Rauschen, gepaarte Differenz, Urteil, Reservebedarf, Abstand zum Optimum |
| `fz_visualization.py` | Fahrzeug-Gantt mit Kranwartezeit-Markern, Kurven, Verteilung, Vergleich (alle Achsen fest) |
| `fz_ui_panel.py` | Panel je Verfahren und Exakt-Tab |
| `fz_pdf_export.py` | PDF-Ergebnis (`fpdf2`, Kernschrift, Sonderzeichen-Bereinigung) |
| `fz_stories.py` | Abnahmekriterien der Presets (Quelle für Werkzeug und Tests) |
| `tools/tune_presets.py`, `tools/PRESET_SWEEP.md` | Preset-Abstimmung und ihr Bericht |
| `tests/` | siehe oben |

## Bewusst nicht umgesetzt (mögliche Erweiterungen)

- **Export** (Abrufzeit aus dem Stapelblock, Kopplung an die Stapelplanung).
- **Fahrspur-, Kreuzungs- und Staukonflikte**, Blockkapazität, Fahrzeuge mit Anfangsort, Laden am Kran.
- **Min-Cost-Flow bei fester Flotte** (Leerfahrten minimieren) und **beidseitiges Rauschen als Regler**.
- **Kalibrierung an echten Terminaldaten.**

## Lokal ausführen

```bash
pip install -r requirements-dev.txt
streamlit run app.py
```

Tests: `python -m pytest tests/ -v`. Preset-Abstimmung: `python tools/tune_presets.py population|seeds|pick`.

---

Teil des [Operations-Research-Demo-Portfolios](https://sebastianhanisch.net/demos.html) von
[Sebastian Hanisch](https://sebastianhanisch.net) – Operations Research und Machine Learning.
Interesse an einer maßgeschneiderten Lösung? [Kontakt aufnehmen](https://sebastianhanisch.net/kontakt.html).
