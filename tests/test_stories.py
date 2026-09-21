"""Tests der Preset-Kriterien selbst (fz_stories.py) an künstlichen Messobjekten: Jedes Kriterium kippt genau bei seiner Schwelle und nur dieses eine. Damit ist gesichert,
dass die Abnahme in test_preset_stories.py nicht zufällig besteht, weil die echten Daten weit von den Schwellen entfernt liegen."""

import pytest

import fz_constants as C
import fz_stories as ST

E_, B_, P_, R_ = C.STRAT_EARLIEST, C.STRAT_BESTFIT, C.STRAT_PLAN, C.STRAT_REDISPATCH


class Fake:
    def __init__(self, waits=None, zeros=None):
        self.w, self.z = waits or {}, zeros or {}

    def wait(self, d, s, k):
        return self.w[(d, s, k)]

    def zero(self, d, s, k):
        return self.z[(d, s, k)]


def flags(name, waits=None, zeros=None):
    return [ok for ok, _ in ST.criteria(name, Fake(waits, zeros))]


# name: (gute Werte, Zero-Anteile, Liste (Änderung, erwartete Flags))
KNAPP = dict(waits={(0, 0, P_): 0.0, (0, 0, E_): 0.3}, zeros={(0, 0, B_): 1.0})
EINS = dict(waits={(-1, 0, E_): 0.5, (-3, 0, E_): 40.0})
ZWEI = dict(waits={(-2, 0, E_): 3.0, (-1, 0, E_): 0.2})
RAUSCH = dict(waits={(0, 25, E_): 0.1, (0, 25, B_): 0.7, (0, 25, P_): 1.4, (0, 25, R_): 0.3})
RESERVE = dict(waits={(2, 25, E_): 0.0, (2, 25, P_): 1.4, (2, 25, B_): 0.6, (2, 25, R_): 0.2}, zeros={(2, 25, E_): 1.0})


def test_good_values_satisfy_every_criterion():
    for name, base in (("Knapp geplant", KNAPP), ("Eins zu wenig", EINS), ("Zwei zu wenig", ZWEI), ("Rauschen 25 %", RAUSCH), ("Mit Reserve", RESERVE)):
        assert all(flags(name, base["waits"], base.get("zeros"))), name


def _flags(name, base, edits):
    e = dict(base["waits"]), dict(base.get("zeros", {}))
    for (table, key), value in edits.items():
        e[0 if table == "w" else 1][key] = value
    return flags(name, e[0], e[1])


def test_knapp_geplant_each_criterion_flips_alone():
    assert _flags("Knapp geplant", KNAPP, {("w", (0, 0, P_)): 0.01}) == [False, True, True]
    assert _flags("Knapp geplant", KNAPP, {("z", (0, 0, B_)): 0.98}) == [True, False, True]
    assert _flags("Knapp geplant", KNAPP, {("z", (0, 0, B_)): 0.99}) == [True, True, True]
    assert _flags("Knapp geplant", KNAPP, {("w", (0, 0, E_)): 0.51}) == [True, True, False]
    assert _flags("Knapp geplant", KNAPP, {("w", (0, 0, E_)): 0.5}) == [True, True, True]


def test_eins_zu_wenig_each_criterion_flips_alone():
    assert _flags("Eins zu wenig", EINS, {("w", (-1, 0, E_)): 1.01, ("w", (-3, 0, E_)): 100.0}) == [False, True]
    assert _flags("Eins zu wenig", EINS, {("w", (-1, 0, E_)): 1.0, ("w", (-3, 0, E_)): 19.9}) == [True, False]
    assert _flags("Eins zu wenig", EINS, {("w", (-1, 0, E_)): 1.0, ("w", (-3, 0, E_)): 20.0}) == [True, True]
    assert _flags("Eins zu wenig", EINS, {("w", (-1, 0, E_)): 0.3, ("w", (-3, 0, E_)): 5.0}) == [True, False]           # 0,3 s sind mehr als 5 % von 5 s


def test_zwei_zu_wenig_each_criterion_flips_alone():
    assert _flags("Zwei zu wenig", ZWEI, {("w", (-2, 0, E_)): 1.99, ("w", (-1, 0, E_)): 0.01}) == [False, True]
    assert _flags("Zwei zu wenig", ZWEI, {("w", (-2, 0, E_)): 3.0, ("w", (-1, 0, E_)): 0.31}) == [True, False]
    assert _flags("Zwei zu wenig", ZWEI, {("w", (-2, 0, E_)): 2.0, ("w", (-1, 0, E_)): 0.2}) == [True, True]


def test_rauschen_each_criterion_flips_alone():
    assert _flags("Rauschen 25 %", RAUSCH, {("w", (0, 25, E_)): 0.3, ("w", (0, 25, B_)): 0.5, ("w", (0, 25, R_)): 0.4}) == [False, True, True]      # 1,4 < 5 x 0,3
    assert _flags("Rauschen 25 %", RAUSCH, {("w", (0, 25, B_)): 1.5}) == [True, False, True]           # Bestfit über dem Plan
    assert _flags("Rauschen 25 %", RAUSCH, {("w", (0, 25, B_)): 0.05}) == [True, False, True]          # Bestfit unter Nächstes freies
    assert _flags("Rauschen 25 %", RAUSCH, {("w", (0, 25, R_)): 1.5}) == [True, True, False]
    assert _flags("Rauschen 25 %", RAUSCH, {("w", (0, 25, R_)): 0.05}) == [True, True, False]
    assert _flags("Rauschen 25 %", RAUSCH, {("w", (0, 25, P_)): 0.5}) == [True, False, True]          # Plan (0,5) unter Bestfit (0,7): nur "Bestfit dazwischen" kippt
    assert _flags("Rauschen 25 %", RAUSCH, {("w", (0, 25, E_)): 0.3, ("w", (0, 25, P_)): 1.5, ("w", (0, 25, R_)): 0.4}) == [True, True, True]      # 1,5 = 5 x 0,3 genau an der Schwelle


def test_mit_reserve_each_criterion_flips_alone():
    assert _flags("Mit Reserve", RESERVE, {("z", (2, 25, E_)): 0.94}) == [False, True, True, True]
    assert _flags("Mit Reserve", RESERVE, {("z", (2, 25, E_)): 0.95}) == [True, True, True, True]
    assert _flags("Mit Reserve", RESERVE, {("w", (2, 25, P_)): 0.0}) == [True, False, True, True]
    assert _flags("Mit Reserve", RESERVE, {("w", (2, 25, B_)): 0.0}) == [True, True, False, True]
    assert _flags("Mit Reserve", RESERVE, {("w", (2, 25, R_)): 0.0}) == [True, True, True, False]


def test_unknown_preset_is_a_key_error():
    with pytest.raises(KeyError):
        ST.criteria("Nope", Fake())
    with pytest.raises(KeyError):
        ST.draw_holds("Nope", {}, 1)


# ---------------------------------------------------------------------------------------------------
# Einzelziehung: jede Bedingung einzeln
# ---------------------------------------------------------------------------------------------------
def test_draw_rules_each_condition_alone():
    n = 100
    assert ST.draw_holds("Knapp geplant", {E_: 0, B_: 0, P_: 0, R_: 0}, n)
    assert not ST.draw_holds("Knapp geplant", {E_: 0, B_: 1, P_: 0, R_: 0}, n)               # Bestfit wartet
    assert not ST.draw_holds("Knapp geplant", {E_: 0, B_: 0, P_: 1, R_: 0}, n)               # Optimalplan wartet
    assert not ST.draw_holds("Knapp geplant", {E_: 51, B_: 0, P_: 0, R_: 0}, n)
    assert ST.draw_holds("Rauschen 25 %", {E_: 2, B_: 30, P_: 100, R_: 10}, n)
    assert not ST.draw_holds("Rauschen 25 %", {E_: 2, B_: 1, P_: 100, R_: 10}, n)            # Bestfit besser als Nächstes freies
    assert not ST.draw_holds("Rauschen 25 %", {E_: 2, B_: 30, P_: 100, R_: 1}, n)            # Umdisposition besser als Nächstes freies
    assert not ST.draw_holds("Rauschen 25 %", {E_: 40, B_: 50, P_: 100, R_: 60}, n)          # Plan nur 2,5-mal
    assert ST.draw_holds("Rauschen 25 %", {E_: 0, B_: 5, P_: 3, R_: 5}, n)                   # E = 0: Untergrenze 1 verhindert eine Division/Schwelle 0
    assert ST.draw_holds("Mit Reserve", {E_: 0, B_: 1, P_: 1, R_: 1}, n)
    for k in (B_, P_, R_):
        cost = {E_: 0, B_: 1, P_: 1, R_: 1}
        cost[k] = 0
        assert not ST.draw_holds("Mit Reserve", cost, n), k
    assert ST.draw_holds("Eins zu wenig", {E_: 100, B_: 0}, n) and not ST.draw_holds("Eins zu wenig", {E_: 101, B_: 0}, n)
    assert ST.draw_holds("Zwei zu wenig", {E_: 200, B_: 0}, n) and not ST.draw_holds("Zwei zu wenig", {E_: 199, B_: 0}, n)


# ---------------------------------------------------------------------------------------------------
# Messobjekte
# ---------------------------------------------------------------------------------------------------
def test_instance_measure_means_zero_shares_and_missing_strategies():
    rows = {(0, 25): [{E_: 0, P_: 10}, {E_: 30, P_: 20}, {E_: 1, P_: 0}, {E_: 0}]}          # der letzte Lauf hat keinen Plan (nicht definiert)
    m = ST.InstanceMeasure(10, rows)
    assert m.wait(0, 25, E_) == pytest.approx(31 / 4 / 10)
    assert m.wait(0, 25, P_) == pytest.approx(30 / 3 / 10)                                   # nur die 3 Läufe mit Plan zählen
    assert m.zero(0, 25, E_) == pytest.approx(2 / 4)                                        # exakt 0 zählt, 1 nicht
    assert m.zero(0, 25, P_) == pytest.approx(1 / 3)
    picked = ST.InstanceMeasure(10, rows, {(0, 25): [1, 1]})
    assert picked.wait(0, 25, E_) == pytest.approx(3.0) and picked.zero(0, 25, E_) == 0


def test_instance_rows_shapes_and_units():
    from fz_presets import scenario_instance

    inst = scenario_instance(3, 10, 75, 10, 6, 4)
    rows = ST.instance_rows(inst, points=((0, 0), (0, 25), (-1, 0)), n_draws=7)
    assert len(rows[(0, 0)]) == 1 and len(rows[(-1, 0)]) == 1 and len(rows[(0, 25)]) == 7          # ohne Rauschen eine einzige, exakte Ziehung
    assert set(rows[(0, 0)][0]) == set(C.STRATEGY_KEYS) and set(rows[(-1, 0)][0]) == {E_, B_}
    assert all(r[P_] == 0 for r in rows[(0, 0)])
    assert any(r[E_] > 0 for r in rows[(0, 25)]) or any(r[P_] > 0 for r in rows[(0, 25)])         # Rauschen in Prozent, nicht als Anteil 25 (dann wäre alles riesig)
    assert max(r[P_] for r in rows[(0, 25)]) < 60 * len(inst.jobs)


def test_bootstrap_stability_is_a_share_between_zero_and_one():
    good = {(0, 0): [{E_: 0, P_: 0, B_: 0, R_: 0}]}
    assert ST.bootstrap_stability("Knapp geplant", {(0, 0): [{E_: 0, P_: 0, B_: 0, R_: 0}] * 3}, 10) == 1.0
    assert ST.bootstrap_stability("Knapp geplant", {(0, 0): [{E_: 100, P_: 5, B_: 5, R_: 5}] * 3}, 10) == 0.0
    del good
    # Zwei Zeilen: eine gute, eine schlechte. Das Mittel besteht nur, wenn die gute überwiegt: der Anteil liegt echt zwischen 0 und 1
    mixed = {(2, 25): [{E_: 0, P_: 1, B_: 1, R_: 1}] * 9 + [{E_: 9, P_: 1, B_: 1, R_: 1}]}          # Neuziehung besteht, wenn keine schlechte gezogen wird: ~0,9^10
    share = ST.bootstrap_stability("Mit Reserve", mixed, 10)
    assert 0.2 < share < 0.8
    # Zwei Kriterien, eines hält immer: 'alle' verlangt beide, 'irgendeines' würde 1.0 liefern
    only_one = {(2, 25): [{E_: 5, P_: 1, B_: 1, R_: 1}] * 4}
    assert ST.bootstrap_stability("Mit Reserve", only_one, 10) == 0.0
    a = ST.bootstrap_stability("Mit Reserve", mixed, 10, seed=1)
    assert a == ST.bootstrap_stability("Mit Reserve", mixed, 10, seed=1)                      # gleicher Seed, gleiches Ergebnis


def test_population_measure_reads_the_right_sweep_and_axis():
    pop = ST.population_measure((3, 10, 75, 10, 6), n_instances=4, n_draws=2)
    assert set(pop.sweeps) == {0, 25}
    assert pop.sweeps[0].axis == (-3, -2, -1, 0) and pop.sweeps[25].axis == (0, 2)
    assert pop.wait(2, 25, C.STRAT_EARLIEST) == pop.sweeps[25].mean(C.STRAT_EARLIEST, 1)
    assert pop.zero(0, 0, C.STRAT_PLAN) == 1.0 and pop.wait(0, 0, C.STRAT_PLAN) == 0
    assert pop.sweeps[25].n_scenarios(0) == 4 * 2 and pop.sweeps[0].n_scenarios(0) == 4       # ohne Rauschen eine Ziehung je Folge
