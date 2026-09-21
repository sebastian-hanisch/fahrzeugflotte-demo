"""Abnahmekriterien der Presets (Plan, Abschnitt 7): Welche Geschichte erzählt jedes Beispielszenario, und woran erkennt man, dass sie trägt?

Einzige Quelle für `tools/tune_presets.py` (Abstimmung) und `tests/test_preset_stories.py` (Abnahme). Alle Kriterien sind Aussagen über MITTELWERTE (Kranwartezeit je
Auftrag in Sekunden) und Anteile wartefreier Szenarien; sie werden über ein Messobjekt mit `wait(delta, sigma_pct, key)` und `zero(delta, sigma_pct, key)` abgefragt.
Es gibt zwei Messobjekte: `InstanceMeasure` (eine Auftragsfolge, viele Rausch-Ziehungen) und `PopulationMeasure` (viele Auftragsfolgen aus fz_evaluation.fleet_sweep).
So wird dieselbe Aussage an der gewählten Auftragsfolge UND an der Grundgesamtheit geprüft: das Preset soll typisch sein, nicht der schönste Einzelfall."""

import random
import statistics

import fz_constants as C
import fz_evaluation as E
from fz_dispatch import draw_noise, min_fleet

E_, B_, P_, R_ = C.STRAT_EARLIEST, C.STRAT_BESTFIT, C.STRAT_PLAN, C.STRAT_REDISPATCH

# Preset -> Punkte (Abstand zum Minimum, Rauschen in %), an denen seine Kriterien gemessen werden
POINTS = {
    "Knapp geplant": ((0, 0),),
    "Eins zu wenig": ((-1, 0), (-3, 0)),
    "Zwei zu wenig": ((-2, 0), (-1, 0)),
    "Rauschen 25 %": ((0, 25),),
    "Mit Reserve": ((2, 25),),
}
ALL_POINTS = tuple(sorted({pt for pts in POINTS.values() for pt in pts}))
STABILITY_DRAWS = 100          # Rausch-Ziehungen je Punkt für die Mittelwert-Aussage einer Auftragsfolge
DRAW_SEED_BASE = 1000          # Messziehungen: Seeds 1000 * 1000 + j, getrennt von den Rausch-Seeds der Presets (kleine Seeds)


def criteria(name, m):
    """Mittelwert-Kriterien. m: Messobjekt. Rückgabe: Liste (erfüllt, Text)."""
    w, z = m.wait, m.zero
    if name == "Knapp geplant":
        return [(w(0, 0, P_) == 0, f"Optimalplan wartet nie: {w(0, 0, P_):.2f} s"),
                (z(0, 0, B_) >= 0.99, f"Bestfit ohne Wartezeit in >= 99 %: {z(0, 0, B_) * 100:.0f} %"),
                (w(0, 0, E_) <= 0.5, f"Nächstes freies <= 0,5 s je Auftrag: {w(0, 0, E_):.2f} s")]
    if name == "Eins zu wenig":
        return [(w(-1, 0, E_) <= 1.0, f"Wartezeit bei Minimum-1 <= 1 s je Auftrag: {w(-1, 0, E_):.2f} s"),
                (w(-1, 0, E_) <= 0.05 * w(-3, 0, E_), f"<= 5 % der Wartezeit bei Minimum-3: {w(-1, 0, E_):.2f} s gegen {w(-3, 0, E_):.1f} s")]
    if name == "Zwei zu wenig":
        # Die Kante bei Minimum-2 ist von Auftragsfolge zu Auftragsfolge sehr verschieden (gemessen: Mittel 7,7 s, Median 2,6 s, 10. bis 90. Perzentil 1,4 bis 32 s).
        # Die Schwelle liegt deshalb bei 2 s, damit auch eine Folge nahe am Median sie trägt (der Plan hatte 5 s nach dem Mittel).
        return [(w(-2, 0, E_) >= 2.0, f"Wartezeit bei Minimum-2 >= 2 s je Auftrag: {w(-2, 0, E_):.2f} s"),
                (w(-2, 0, E_) >= 10 * w(-1, 0, E_), f">= 10-mal die bei Minimum-1: {w(-2, 0, E_):.2f} s gegen {w(-1, 0, E_):.2f} s")]
    if name == "Rauschen 25 %":
        e, b, p, r = (w(0, 25, k) for k in (E_, B_, P_, R_))
        return [(p >= 5 * e, f"starrer Optimalplan >= 5-mal Nächstes freies: {p:.2f} s gegen {e:.2f} s"),
                (e < b < p, f"Bestfit dazwischen: {e:.2f} < {b:.2f} < {p:.2f}"),
                (e < r < p, f"Plan + Umdisposition dazwischen: {e:.2f} < {r:.2f} < {p:.2f}")]
    if name == "Mit Reserve":
        return [(z(2, 25, E_) >= 0.95, f"Nächstes freies ohne Wartezeit in >= 95 % der Ziehungen: {z(2, 25, E_) * 100:.0f} %")] + [
            (w(2, 25, k) > 0, f"{C.STRATEGY_LABELS[k]} wartet weiter: {w(2, 25, k):.2f} s") for k in (P_, B_, R_)]
    raise KeyError(name)


def draw_holds(name, cost, n_jobs):
    """Gilt die Geschichte in EINER Ziehung (die das Preset zeigt)? cost: {Verfahren: Summe der Kranwartezeit}; Optimalpläne dürfen fehlen (unter dem Minimum)."""
    if name == "Knapp geplant":
        return cost[P_] == 0 and cost[B_] == 0 and cost[E_] <= 0.5 * n_jobs
    if name == "Eins zu wenig":
        return cost[E_] <= 1.0 * n_jobs
    if name == "Zwei zu wenig":
        return cost[E_] >= 2.0 * n_jobs
    if name == "Rauschen 25 %":
        return cost[P_] >= 3 * max(cost[E_], 1) and cost[E_] <= min(cost[B_], cost[R_])
    if name == "Mit Reserve":
        return cost[E_] == 0 and min(cost[P_], cost[B_], cost[R_]) > 0
    raise KeyError(name)


# ---------------------------------------------------------------------------------------------------
# Messobjekte
# ---------------------------------------------------------------------------------------------------
class InstanceMeasure:
    """Eine Auftragsfolge: `rows[(delta, sigma_pct)]` = Liste (je Rausch-Ziehung) von {Verfahren: Summe der Kranwartezeit}. `pick` wählt eine Teilmenge der
    Ziehungen (Bootstrap): Liste von Indizes je Punkt, sonst alle."""

    def __init__(self, n_jobs, rows, pick=None):
        self.n_jobs, self.rows, self.pick = n_jobs, rows, pick or {}

    def _values(self, delta, sigma, key):
        rows = self.rows[(delta, sigma)]
        idx = self.pick.get((delta, sigma))
        rows = rows if idx is None else [rows[i] for i in idx]
        return [r[key] for r in rows if r.get(key) is not None]

    def wait(self, delta, sigma, key):
        return statistics.fmean(self._values(delta, sigma, key)) / self.n_jobs

    def zero(self, delta, sigma, key):
        v = self._values(delta, sigma, key)
        return sum(1 for x in v if x == 0) / len(v)


class PopulationMeasure:
    """Viele Auftragsfolgen: `sweeps[sigma_pct]` = fz_evaluation.Sweep über den Abstand zum Minimum bei diesem Rauschen."""

    def __init__(self, sweeps):
        self.sweeps = sweeps

    def wait(self, delta, sigma, key):
        sw = self.sweeps[sigma]
        return sw.mean(key, sw.axis.index(delta))

    def zero(self, delta, sigma, key):
        sw = self.sweeps[sigma]
        return sw.zero_wait_share(key, sw.axis.index(delta))


def instance_rows(inst, points=ALL_POINTS, n_draws=STABILITY_DRAWS, mf=None):
    """Rohzeilen einer Auftragsfolge für alle Messpunkte (ohne Rauschen eine einzige, exakte Ziehung)."""
    mf = mf or min_fleet(inst)
    n = len(inst.jobs)
    rows = {}
    for delta, sigma in points:
        K = E.fleet_size(mf[0], delta)
        draws = 1 if sigma == 0 else n_draws
        rows[(delta, sigma)] = [
            {o.key: o.wait_total for o in E.run_strategies(inst, K, draw_noise(n, sigma / 100, DRAW_SEED_BASE * 1000 + j), mf) if o.available}
            for j in range(draws)]
    return rows


def population_measure(terminal, n_instances=C.SWEEP_INSTANCES, n_draws=C.SWEEP_DRAWS):
    """Grundgesamtheit eines Terminals (terminal = (Q, m, Takt, Streuung, Blöcke)): Auftragsfolgen mit den Seeds 0.. gegen die Rausch-Ziehungen."""
    sweeps = {}
    for sigma in sorted({s for _, s in ALL_POINTS}):
        sweeps[sigma] = E.fleet_sweep(*terminal, sigma, deltas=tuple(sorted({d for d, s in ALL_POINTS if s == sigma})), n_instances=n_instances, n_draws=n_draws)
    return PopulationMeasure(sweeps)


def bootstrap_stability(name, measure_rows, n_jobs, n_boot=300, seed=4711):
    """Rauschstabilität der MITTELWERT-Aussage: Anteil der Neuziehungen (Bootstrap über die Rausch-Ziehungen), bei denen alle Kriterien des Presets gelten. Einzelne
    Ziehungen halten die Geschichte bewusst nicht immer; Stabilität gilt deshalb der Mittelwert-Aussage."""
    rng = random.Random(seed)
    hits = 0
    for _ in range(n_boot):
        pick = {}
        for pt in POINTS[name]:
            n = len(measure_rows[pt])
            pick[pt] = [rng.randrange(n) for _ in range(n)]
        hits += all(ok for ok, _ in criteria(name, InstanceMeasure(n_jobs, measure_rows, pick)))
    return hits / n_boot
