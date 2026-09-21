"""Auswertung: ein Szenario mit allen Verfahren, Kurven über die Flottengröße und über das Rauschen, gepaarte Differenz, Anteil besser/gleich/schlechter,
Anteil wartefreier Szenarien, Reservebedarf, Urteil, Abstand zum Optimum bei Flottenmangel.

Reine Rechnung ohne Streamlit. Alle Kosten sind Kranwartezeit in Sekunden (Summe über die Aufträge eines Szenarios; je Auftrag = Summe / Auftragszahl). "Gewinn" heißt
Kosten der Referenz (Nächstes freies) minus Kosten des Verfahrens, positiv = das Verfahren ist besser. Die Simulation ist so billig (0,2 bis 0,5 ms je Lauf), dass alle
Kurven live gerechnet werden."""

import math
import statistics
from dataclasses import dataclass

import fz_constants as C
from fz_dispatch import (draw_noise, make_rule_bestfit, make_rule_plan, make_rule_plan_redispatch, min_fleet, no_noise, rule_earliest, simulate,
                         smallest_fleet)
from fz_scenario import make_instance


def fleet_size(kmin, delta):
    """Flotte = exaktes Minimum + Abstand, mindestens ein Fahrzeug."""
    return max(1, kmin + delta)


def noise_for(noise_seed, draw=0):
    """Seed der Rausch-Ziehung `draw` zu einem eingestellten Rausch-Seed: Ziehung 0 ist die im Bild gezeigte."""
    return noise_seed * 1000 + draw


# ---------------------------------------------------------------------------------------------------
# Ein Szenario, alle Verfahren
# ---------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class StrategyOutcome:
    key: str
    label: str
    run: object             # fz_dispatch.Run oder None, wenn das Verfahren bei dieser Flotte nicht definiert ist
    reason: str = ""        # Begründung, wenn run None ist

    @property
    def available(self):
        return self.run is not None

    @property
    def wait_total(self):
        return self.run.wait_total if self.run else None

    @property
    def wait_per_job(self):
        return self.run.wait_per_job if self.run else None

    @property
    def late_jobs(self):
        return self.run.late_jobs if self.run else None

    @property
    def utilization(self):
        return self.run.utilization if self.run else None


NO_PLAN_BELOW_MINIMUM = ("Unter der Mindestflotte gibt es keinen Plan ohne Kranwartezeit: Der starre Optimalplan setzt genau so viele Fahrzeuge voraus, wie das Minimum braucht. "
                         "Das Optimum bei Flottenmangel steht im Exakt-Tab.")


def _rules(inst, assign):
    return {C.STRAT_EARLIEST: rule_earliest, C.STRAT_BESTFIT: make_rule_bestfit(inst), C.STRAT_PLAN: make_rule_plan(assign),
            C.STRAT_REDISPATCH: make_rule_plan_redispatch(inst, assign)}


def run_strategies(inst, K, noise=None, min_fleet_result=None):
    """Alle vier Verfahren mit K Fahrzeugen auf DEMSELBEN Rauschen (gepaart). Die Optimalplan-Verfahren gibt es erst ab der Mindestflotte."""
    kmin, assign = min_fleet_result or min_fleet(inst)
    rules = _rules(inst, assign)
    out = []
    for key in C.STRATEGY_KEYS:
        if key in C.PLAN_KEYS and K < kmin:
            out.append(StrategyOutcome(key, C.STRATEGY_LABELS[key], None, NO_PLAN_BELOW_MINIMUM))
        else:
            out.append(StrategyOutcome(key, C.STRATEGY_LABELS[key], simulate(inst, K, rules[key], noise)))
    return tuple(out)


def outcome_of(outcomes, key):
    return next(o for o in outcomes if o.key == key)


@dataclass(frozen=True)
class Row:
    key: str
    label: str
    available: bool
    wait_total: object
    wait_per_job: object
    late_jobs: object
    utilization: object
    delta_vs_baseline: object       # meine minus Referenz (negativ = besser), Summe der Kranwartezeit; None, wenn nicht verfügbar
    reason: str


def comparison_rows(outcomes, baseline=C.BASELINE):
    ref = outcome_of(outcomes, baseline).wait_total
    return tuple(Row(o.key, o.label, o.available, o.wait_total, o.wait_per_job, o.late_jobs, o.utilization,
                     None if not o.available else o.wait_total - ref, o.reason) for o in outcomes)


# ---------------------------------------------------------------------------------------------------
# Kennzahlen der eigenen Auftragsfolge über viele Rausch-Ziehungen
# ---------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class FocusStats:
    key: str
    available: bool
    n_draws: int
    mean_per_job: object            # Mittel der Kranwartezeit je Auftrag
    se_per_job: object
    zero_share: object              # Anteil der Ziehungen ganz ohne Kranwartezeit
    mean_utilization: object
    paired_diff: object             # (Mittel, Standardfehler) je Auftrag gegen die Referenz: meine minus Referenz


def focus_stats(inst, K, sigma, noise_seed, n_draws=C.FOCUS_DRAWS, min_fleet_result=None):
    """Mittel über `n_draws` Rausch-Ziehungen der eigenen Auftragsfolge (Ziehung 0 = die gezeigte). Ohne Rauschen (sigma = 0) genau eine, exakte Ziehung."""
    n = len(inst.jobs)
    mf = min_fleet_result or min_fleet(inst)
    draws = 1 if sigma == 0 else n_draws
    per = {k: [] for k in C.STRATEGY_KEYS}
    util = {k: [] for k in C.STRATEGY_KEYS}
    for j in range(draws):
        noise = draw_noise(n, sigma, noise_for(noise_seed, j))
        for o in run_strategies(inst, K, noise, mf):
            if o.available:
                per[o.key].append(o.wait_total)
                util[o.key].append(o.utilization)
    ref = per[C.BASELINE]
    out = []
    for key in C.STRATEGY_KEYS:
        vals = per[key]
        if not vals:
            out.append(FocusStats(key, False, draws, None, None, None, None, None))
            continue
        diffs = [(a - b) / n for a, b in zip(vals, ref)]
        out.append(FocusStats(
            key, True, draws, statistics.fmean(vals) / n, _se(vals) / n, sum(1 for v in vals if v == 0) / len(vals), statistics.fmean(util[key]),
            (statistics.fmean(diffs), _se(diffs))))
    return tuple(out)


def _se(xs):
    return statistics.stdev(xs) / math.sqrt(len(xs)) if len(xs) > 1 else 0.0


@dataclass(frozen=True)
class RunExtras:
    empty_share: float          # Anteil der Fahrzeit, der Leerfahrt zur Brücke ist
    crane_changes: int          # Fahrzeuge, die zum nächsten Auftrag zu einer anderen Brücke wechseln (Zahl der Wechsel)
    vehicles_used: int          # Fahrzeuge mit mindestens einem Auftrag


def run_extras(run, inst):
    """Leerfahrtanteil, Brückenwechsel und benutzte Fahrzeuge eines Ablaufs (für die Kennzahlen im Panel)."""
    empty = sum(t.empty_time for t in run.trips)
    total = empty + sum(t.loaded_time for t in run.trips)
    last_crane, changes = {}, 0
    for t in run.trips:
        q = inst.jobs[t.job].crane
        if t.vehicle in last_crane and last_crane[t.vehicle] != q:
            changes += 1
        last_crane[t.vehicle] = q
    return RunExtras(empty / total if total else 0.0, changes, len(last_crane))


# ---------------------------------------------------------------------------------------------------
# Kurven: Stichprobe aus Auftragsfolgen x Ziehungen
# ---------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Sweep:
    axis_name: str              # "delta" (Abstand zum Minimum) oder "sigma" (Rauschen in Prozent)
    axis: tuple
    n_jobs: int
    values: dict                # Verfahren -> Tupel über die Achse von Tupeln über Szenarien: Summe der Kranwartezeit (s); leer, wo das Verfahren nicht definiert ist
    kmins: tuple                # exaktes Minimum je Auftragsfolge der Stichprobe

    def index_of(self, x):
        return min(range(len(self.axis)), key=lambda i: abs(self.axis[i] - x))

    def series(self, key, i):
        return self.values[key][i]

    def available(self, key, i):
        return len(self.values[key][i]) > 0

    def n_scenarios(self, i):
        return len(self.values[C.BASELINE][i])

    def mean(self, key, i):
        """Mittel der Kranwartezeit JE AUFTRAG."""
        return statistics.fmean(self.series(key, i)) / self.n_jobs

    def sem(self, key, i):
        v = self.series(key, i)
        return _se(v) / self.n_jobs

    def gains(self, key, i, reference=C.BASELINE):
        """Gewinn je Szenario gegenüber der Referenz (Summe der Kranwartezeit in s): Referenz minus Verfahren, positiv = besser."""
        return tuple(b - s for b, s in zip(self.series(reference, i), self.series(key, i)))

    def paired_diff(self, key, reference, i):
        """(Mittel, Standardfehler) von key - reference je Auftrag über dieselben Szenarien; negativ = key besser."""
        d = [(x - y) / self.n_jobs for x, y in zip(self.series(key, i), self.series(reference, i))]
        return statistics.fmean(d), _se(d)

    def zero_wait_share(self, key, i):
        v = self.series(key, i)
        return sum(1 for x in v if x == 0) / len(v)


def _params_instances(n_cranes, jobs_per_crane, cycle, jitter, blocks, n_instances):
    return [make_instance(n_cranes, jobs_per_crane, seed, cycle, jitter, blocks) for seed in range(n_instances)]


def default_instances(n_cranes, jobs_per_crane):
    return C.SWEEP_INSTANCES_LARGE if n_cranes * jobs_per_crane > C.SWEEP_LARGE_JOBS else C.SWEEP_INSTANCES


def _sweep(axis_name, axis, points, n_cranes, jobs_per_crane, cycle, jitter, blocks, n_instances, n_draws):
    """points: Liste (delta, sigma) je Achsenpunkt."""
    insts = _params_instances(n_cranes, jobs_per_crane, cycle, jitter, blocks, n_instances)
    mf = [min_fleet(inst) for inst in insts]
    n_jobs = n_cranes * jobs_per_crane
    values = {k: [] for k in C.STRATEGY_KEYS}
    for delta, sigma in points:
        cols = {k: [] for k in C.STRATEGY_KEYS}
        draws = 1 if sigma == 0 else n_draws
        for k, inst in enumerate(insts):
            kmin = mf[k][0]
            if kmin + delta < 1:
                continue                                    # Abstand nicht darstellbar (weniger als ein Fahrzeug): Auftragsfolge fällt an diesem Punkt weg
            K = kmin + delta
            for j in range(draws):
                noise = draw_noise(n_jobs, sigma, 1000 * k + j)
                for o in run_strategies(inst, K, noise, mf[k]):
                    if o.available:
                        cols[o.key].append(o.wait_total)
        for key in C.STRATEGY_KEYS:
            values[key].append(tuple(cols[key]))
    return Sweep(axis_name, tuple(axis), n_jobs, {k: tuple(v) for k, v in values.items()}, tuple(m[0] for m in mf))


def fleet_sweep(n_cranes, jobs_per_crane, cycle, jitter, blocks, sigma_pct, deltas=C.FLEET_SWEEP_DELTAS, n_instances=None, n_draws=C.SWEEP_DRAWS):
    """Kranwartezeit über den Abstand zum Minimum (die Kante) beim eingestellten Rauschen."""
    n_instances = n_instances or default_instances(n_cranes, jobs_per_crane)
    return _sweep("delta", deltas, [(d, sigma_pct / 100) for d in deltas], n_cranes, jobs_per_crane, cycle, jitter, blocks, n_instances, n_draws)


def noise_sweep(n_cranes, jobs_per_crane, cycle, jitter, blocks, delta, sigma_pcts=C.NOISE_SWEEP_PCT, n_instances=None, n_draws=C.SWEEP_DRAWS):
    """Kranwartezeit über das Rauschen bei der eingestellten Flotte (Abstand zum Minimum)."""
    n_instances = n_instances or default_instances(n_cranes, jobs_per_crane)
    return _sweep("sigma", sigma_pcts, [(delta, s / 100) for s in sigma_pcts], n_cranes, jobs_per_crane, cycle, jitter, blocks, n_instances, n_draws)


# ---------------------------------------------------------------------------------------------------
# Verteilung, Urteil, Reservebedarf
# ---------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Distribution:
    key: str
    better: float               # Anteile der Szenarien (0..1) gegen die Referenz
    equal: float
    worse: float
    mean_gain: float            # Summe der Kranwartezeit je Szenario (s)
    median_gain: float
    zero_share: float           # Anteil wartefreier Szenarien des Verfahrens
    ref_zero_share: float


def distribution(sweep, key, index, reference=C.BASELINE, tol=C.TIE_TOLERANCE):
    """Wie sich die Gewinne über die Szenarien verteilen (Mittelwerte täuschen bei schiefen Gewinnen)."""
    g = sweep.gains(key, index, reference)
    n = len(g)
    better = sum(1 for x in g if x > tol)
    worse = sum(1 for x in g if x < -tol)
    return Distribution(key, better / n, (n - better - worse) / n, worse / n, statistics.fmean(g), statistics.median(g),
                        sweep.zero_wait_share(key, index), sweep.zero_wait_share(reference, index))


@dataclass(frozen=True)
class Verdict:
    kind: str                   # "better" | "worse" | "unclear"
    diff: float                 # Verfahren minus Referenz, je Auftrag (negativ = besser)
    se: float
    pct: object                 # Unterschied in % der Referenz (negativ = besser); None, wenn die Referenz nie wartet
    worse_share: float          # Anteil der Szenarien, in denen das Verfahren schlechter als die Referenz ist


def verdict(sweep, key, index, reference=C.BASELINE):
    """Bewertung gegen die Referenz. 'Klar' heißt: Unterschied > VERDICT_Z Standardfehler der gepaarten Differenz; sonst 'unclear'."""
    diff, se = sweep.paired_diff(key, reference, index)
    base = sweep.mean(reference, index)
    if se == 0:
        kind = "unclear" if diff == 0 else ("better" if diff < 0 else "worse")
    else:
        kind = "unclear" if abs(diff) <= C.VERDICT_Z * se else ("better" if diff < 0 else "worse")
    return Verdict(kind, diff, se, 100.0 * diff / base if base else None, distribution(sweep, key, index, reference).worse)


def reserve_need(sweep, key, share=C.ZERO_WAIT_SHARE):
    """Kleinster Abstand zum Minimum (auf der Achse), bei dem `key` in mindestens `share` der Szenarien keine Kranwartezeit hat; None, wenn nie im Bereich.
    Nur Punkte, an denen das Verfahren definiert ist."""
    if sweep.axis_name != "delta":
        raise ValueError("Reservebedarf braucht eine Kurve über den Abstand zum Minimum")
    for i, d in enumerate(sweep.axis):
        if sweep.available(key, i) and sweep.zero_wait_share(key, i) >= share:
            return d
    return None


def edge_figures(sweep):
    """Die Kante (Kranwartezeit je Auftrag der Referenz) bei Minimum, Minimum - 1 und Minimum - 2; None, wo die Achse den Punkt nicht hat oder keine Auftragsfolge
    der Stichprobe so viele Fahrzeuge weniger verträgt."""
    out = {}
    for d in (0, -1, -2):
        out[d] = sweep.mean(C.BASELINE, sweep.axis.index(d)) if d in sweep.axis and sweep.available(C.BASELINE, sweep.axis.index(d)) else None
    return out


# ---------------------------------------------------------------------------------------------------
# Trifft Bestfit das Minimum? (gemessen, nicht bewiesen)
# ---------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class HitRates:
    n_instances: int
    bestfit_hits: int               # Auftragsfolgen, in denen Bestfit mit genau dem Minimum auskommt
    bestfit_max_excess: int         # größte Abweichung nach oben (Fahrzeuge)
    earliest_mean_excess: float     # mittlere Zahl zusätzlicher Fahrzeuge für Nächstes freies


def minimum_hit_rates(n_cranes, jobs_per_crane, cycle, jitter, blocks, n_instances=C.SWEEP_INSTANCES):
    insts = _params_instances(n_cranes, jobs_per_crane, cycle, jitter, blocks, n_instances)
    hits, worst, ea = 0, 0, []
    for inst in insts:
        k, _ = min_fleet(inst)
        b = smallest_fleet(inst, make_rule_bestfit)
        e = smallest_fleet(inst, lambda i: rule_earliest)
        hits += b == k
        worst = max(worst, b - k)
        ea.append(e - k)
    return HitRates(n_instances, hits, worst, statistics.fmean(ea))


# ---------------------------------------------------------------------------------------------------
# Abstand zum Optimum bei Flottenmangel
# ---------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class OptimumGap:
    key: str
    wait: int                   # Summe der Kranwartezeit des Verfahrens (nominal)
    excess: object              # Abstand zur besten bekannten Lösung (>= 0, wenn das Optimum bewiesen ist); None, wenn nicht definiert
    ratio: object               # Wartezeit / beste bekannte Lösung; None, wenn die beste Lösung 0 ist
    proven: bool                # das Optimum ist bewiesen (sonst ist der Abstand womöglich zu klein)


def gaps_to_optimum(inst, K, optimum, min_fleet_result=None):
    """Nominale Kranwartezeit der Verfahren gegen das Optimum bei Flottenmangel (fz_exact.WaitOptimum). Optimalplan-Verfahren gibt es unter dem Minimum nicht."""
    out = []
    for o in run_strategies(inst, K, no_noise(len(inst.jobs)), min_fleet_result):
        if not o.available:
            continue
        best = optimum.wait_best
        excess = o.wait_total - best
        out.append(OptimumGap(o.key, o.wait_total, excess if optimum.proven else max(0, excess), o.wait_total / best if best else None, optimum.proven))
    return tuple(out)
