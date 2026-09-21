"""Feste Terminalparameter, Regler-Grenzen und Vorgaben der Fahrzeugflotten-Demo.

Alle Zeiten ganzzahlig in Sekunden, alle Längen in Metern. Das Terminal ist fest (Brückenabstand, Geschwindigkeit, Absetzzeit,
Mindestabstand zweier Aufnahmen derselben Brücke); veränderlich sind Größe und Takt des Auftragsstroms, die Flotte und die Störung."""

# --- fest: Terminal ---
T_MIN = 40              # frühestens so viele Sekunden zwischen zwei Aufnahmen derselben Brücke
SERVICE = 15            # Absetzen am Block (s)
SPEED = 6               # Fahrgeschwindigkeit (m/s)
CRANE_SPACING = 40      # Abstand zweier Brücken am Kai (m)
YARD_OFFSET = 110       # Abstand des ersten Blocks vom Kai (m); jeder zweite Block liegt weitere YARD_STAGGER m dahinter
YARD_STAGGER = 20
BLOCK_MARGIN = 15       # Block 0 beginnt so weit vom Kaiende

# --- Regler: Grenzen und Vorgaben ---
N_CRANES_RANGE, N_CRANES_DEFAULT = (2, 6), 4
JOBS_PER_CRANE_RANGE, JOBS_PER_CRANE_DEFAULT = (10, 40), 30
CYCLE_RANGE, CYCLE_DEFAULT = (60, 150), 75            # Takt je Brücke (s)
JITTER_RANGE, JITTER_DEFAULT = (0, 20), 10            # Streuung des Takts (s)
BLOCKS_RANGE, BLOCKS_DEFAULT = (3, 8), 6
SEED_RANGE, SEED_DEFAULT = (0, 9999), 72
FLEET_DELTA_RANGE, FLEET_DELTA_DEFAULT = (-4, 4), 0   # Flotte = exaktes Minimum + Abstand (mindestens 1)
NOISE_PCT_RANGE, NOISE_PCT_STEP, NOISE_PCT_DEFAULT = (0, 50), 5, 10   # Fahrzeit-Rauschen: bis so viel Prozent länger (ganze Prozent)
NOISE_SEED_DEFAULT = 3
MAX_JOBS = 240          # Q * m höchstens (Laufzeit der Kurven)

# Exakt-Löser: Zeitlimit für das Optimum der Kranwartezeit bei Flottenmangel (s); danach gilt das Ergebnis als "nicht bewiesen"
EXACT_TIME_LIMIT_SECONDS = 10

# --- Verfahren (Schlüssel -> Beschriftung, in Anzeigereihenfolge); "Nächstes freies" ist die Referenz aller Deltas (für jede Flottengröße definiert) ---
STRAT_EARLIEST, STRAT_BESTFIT, STRAT_PLAN, STRAT_REDISPATCH = "earliest", "bestfit", "plan", "redispatch"
STRATEGY_LABELS = {
    STRAT_EARLIEST: "⏭️ Nächstes freies",
    STRAT_BESTFIT: "🎯 Bestfit",
    STRAT_PLAN: "📋 Optimalplan starr",
    STRAT_REDISPATCH: "🔁 Plan + Umdisposition",
}
STRATEGY_SHORT = {STRAT_EARLIEST: "Nächstes<br>freies", STRAT_BESTFIT: "Bestfit", STRAT_PLAN: "Optimalplan<br>starr", STRAT_REDISPATCH: "Plan +<br>Umdisposition"}
STRATEGY_KEYS = tuple(STRATEGY_LABELS)
BASELINE = STRAT_EARLIEST
PLAN_KEYS = (STRAT_PLAN, STRAT_REDISPATCH)      # brauchen mindestens die Mindestflotte: darunter gibt es keinen Plan ohne Wartezeit

# --- Kurven: Stichprobe (Auftragsfolgen mit den Seeds 0.. unabhängig vom eingestellten Seed x Rausch-Ziehungen je Punkt) ---
SWEEP_INSTANCES = 20
SWEEP_INSTANCES_LARGE = 10      # ab SWEEP_LARGE_JOBS Aufträgen (Laufzeit)
SWEEP_LARGE_JOBS = 120
SWEEP_DRAWS = 10
FLEET_SWEEP_DELTAS = tuple(range(-6, 5))
NOISE_SWEEP_PCT = tuple(range(0, 55, 5))
FOCUS_DRAWS = 100               # Rausch-Ziehungen für die Kennzahlen der eigenen Auftragsfolge
TIE_TOLERANCE = 0.5             # Unterschiede bis zu dieser Kranwartezeit (s, Summe je Szenario) zählen als "gleich"
VERDICT_Z = 2.0                 # "klar" heißt gepaarte Differenz > VERDICT_Z Standardfehler
ZERO_WAIT_SHARE = 0.95          # Reservebedarf: kleinster Abstand, bei dem ein Verfahren in so vielen Szenarien keine Kranwartezeit hat

# --- Darstellung ---
STRATEGY_COLORS = {STRAT_EARLIEST: "#8a94a3", STRAT_BESTFIT: "#2a6fb0", STRAT_PLAN: "#c77700", STRAT_REDISPATCH: "#2e7d4f"}
STRATEGY_DESCRIPTIONS = {
    STRAT_EARLIEST: "**Nächstes freies.** Jeder Auftrag geht an das Fahrzeug, das am frühesten unter der Brücke stehen kann. Keine Planung, keine Vorausschau: "
                    "die schlichte Regel und die Referenz aller Vergleiche. Sie ist für jede Flottengröße definiert.",
    STRAT_BESTFIT: "**Bestfit.** Unter den Fahrzeugen, die rechtzeitig kommen, geht der Auftrag an das mit der spätesten Ankunft (das knappste), damit die früher "
                   "verfügbaren für spätere Aufträge frei bleiben. Kommt keines rechtzeitig, geht er an das früheste. Findet nominal fast immer die Mindestflotte.",
    STRAT_PLAN: "**Optimalplan starr.** Die Fahrzeugketten kommen aus einem maximalen Matching: nominal genau die Mindestflotte und keine Wartezeit. Im Ablauf wird die "
                "Zuordnung starr befolgt, auch wenn ein Fahrzeug sich verspätet, und die Verspätung läuft die Kette entlang. Gibt es erst ab der Mindestflotte.",
    STRAT_REDISPATCH: "**Plan + Umdisposition.** Wie der Optimalplan, aber ist das geplante Fahrzeug voraussichtlich zu spät, geht der Auftrag an das früheste freie. "
                      "Trennt die Wirkung von Reserve und von Reaktion.",
}
OUTCOME_COLORS = {"better": "#2e7d4f", "equal": "#b8bfc9", "worse": "#c0392b"}
CRANE_COLORS = ("#2a6fb0", "#c77700", "#2e7d4f", "#7a3fb0", "#b0356a", "#1a8a8a")      # Brücke 1..6
CRANE_COLOR_NAMES = ("blau", "orange", "grün", "violett", "rosa", "türkis")
EMPTY_COLOR = "rgba(128,136,149,0.55)"    # Leerfahrt zur Brücke (halbtransparentes Mittelgrau: auf hellem und dunklem Grund lesbar)
IDLE_COLOR = "rgba(128,136,149,0.2)"      # Fahrzeug steht an der Brücke und wartet auf den Auftrag
CRANE_WAIT_COLOR = "#d62728"        # Brücke wartet auf das Fahrzeug (Kranwartezeit)
MARKER_LINE_COLOR = "#808895"       # mittleres Grau: auf hellem und dunklem Grund sichtbar
CHART_HEIGHT = 420
LOG_FLOOR = 0.01                    # Kurven mit logarithmischer Achse: 0 s wird an den unteren Rand gelegt
GANTT_LABEL_MAX_JOBS = 60           # bis zu so vielen Aufträgen tragen die Balken ihre Auftragsnummer

# --- Regler: weitere Vorgaben ---
CYCLE_STEP = 5
RIGHT_VIEW_KEYS = (STRAT_BESTFIT, STRAT_PLAN, STRAT_REDISPATCH)     # im Terminal-Blick steht links immer Nächstes freies
VIEW_DEFAULT = STRAT_PLAN

# --- Presets: eine gemeinsame Auftragsfolge (Seed 72), Flotte und Rauschen wechseln; Seeds von tools/tune_presets.py gewählt (typisch, rauschstabil) ---
_BASE = dict(n_cranes=4, jobs_per_crane=30, cycle=75, jitter=10, blocks=6, seed=SEED_DEFAULT, noise_seed=NOISE_SEED_DEFAULT)
PRESETS = {
    "Knapp geplant": dict(_BASE, fleet_delta=0, noise_pct=0),
    "Eins zu wenig": dict(_BASE, fleet_delta=-1, noise_pct=0),
    "Zwei zu wenig": dict(_BASE, fleet_delta=-2, noise_pct=0),
    "Rauschen 25 %": dict(_BASE, fleet_delta=0, noise_pct=25, noise_seed=37),
    "Mit Reserve": dict(_BASE, fleet_delta=2, noise_pct=25, noise_seed=22),
}
