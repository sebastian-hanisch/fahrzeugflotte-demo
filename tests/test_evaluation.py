"""Tests der Auswertung: Verteilung, Urteil, Reservebedarf an künstlichen Kurven; Form, Auslassungen, Determinismus und Gegenprobe an echten Läufen."""

import math
import statistics

import pytest

import fz_constants as C
import fz_evaluation as E
from fz_dispatch import draw_noise, make_rule_bestfit, make_rule_plan_redispatch, min_fleet, no_noise, rule_earliest, simulate
from fz_exact import WaitOptimum
from fz_scenario import make_instance

E_, B_, P_, R_ = C.STRAT_EARLIEST, C.STRAT_BESTFIT, C.STRAT_PLAN, C.STRAT_REDISPATCH


def fake_sweep(earliest, other, key=B_, n_jobs=10, axis=(0,), axis_name="delta"):
    """Eine Kurve mit einem Achsenpunkt und vorgegebenen Szenario-Summen."""
    vals = {k: ((),) * len(axis) for k in C.STRATEGY_KEYS}
    vals[E_] = (tuple(earliest),) * len(axis)
    vals[key] = (tuple(other),) * len(axis)
    return E.Sweep(axis_name, tuple(axis), n_jobs, vals, (3,))


# ---------------------------------------------------------------------------------------------------
# Kleine Hilfen
# ---------------------------------------------------------------------------------------------------
def test_fleet_size_is_at_least_one():
    assert E.fleet_size(5, 2) == 7
    assert E.fleet_size(5, -4) == 1
    assert E.fleet_size(2, -4) == 1
    assert E.fleet_size(1, -1) == 1


def test_noise_seed_draw_zero_is_shown_draw():
    assert E.noise_for(3, 0) == 3000
    assert E.noise_for(3, 7) == 3007
    assert E.noise_for(4, 0) != E.noise_for(3, 0)


# ---------------------------------------------------------------------------------------------------
# Verteilung
# ---------------------------------------------------------------------------------------------------
def test_distribution_shares_and_gains():
    ref = (10, 10, 10, 10, 10)
    mine = (5, 10, 20, 10.3, 0)        # Gewinne: 5, 0, -10, -0.3, 10
    d = E.distribution(fake_sweep(ref, mine), B_, 0)
    assert d.better == pytest.approx(2 / 5)
    assert d.worse == pytest.approx(1 / 5)
    assert d.equal == pytest.approx(2 / 5)
    assert d.better + d.equal + d.worse == pytest.approx(1)
    assert d.mean_gain == pytest.approx(statistics.fmean([5, 0, -10, -0.3, 10]))
    assert d.median_gain == pytest.approx(0)
    assert d.zero_share == pytest.approx(1 / 5)
    assert d.ref_zero_share == 0


def test_distribution_tie_tolerance_boundary():
    ref = (10, 10, 10)
    mine = (10 - C.TIE_TOLERANCE, 10 + C.TIE_TOLERANCE, 10 - C.TIE_TOLERANCE - 0.01)
    d = E.distribution(fake_sweep(ref, mine), B_, 0)
    assert d.equal == pytest.approx(2 / 3)
    assert d.better == pytest.approx(1 / 3)
    assert d.worse == 0


def test_distribution_skewed_median_far_from_mean():
    ref = (100,) * 10
    mine = (100,) * 9 + (0,)
    d = E.distribution(fake_sweep(ref, mine), B_, 0)
    assert d.median_gain == 0 and d.mean_gain == pytest.approx(10)
    assert d.better == pytest.approx(0.1) and d.equal == pytest.approx(0.9)


# ---------------------------------------------------------------------------------------------------
# Urteil (drei Zustände)
# ---------------------------------------------------------------------------------------------------
def test_verdict_better_worse_unclear():
    ref = tuple(10 + (i % 3) for i in range(30))
    better = fake_sweep(ref, tuple(x - 5 - (i % 2) for i, x in enumerate(ref)))
    worse = fake_sweep(ref, tuple(x + 5 + (i % 2) for i, x in enumerate(ref)))
    noisy = fake_sweep(ref, tuple(x + (1 if i % 2 else -1) for i, x in enumerate(ref)))
    vb, vw, vu = E.verdict(better, B_, 0), E.verdict(worse, B_, 0), E.verdict(noisy, B_, 0)
    assert vb.kind == "better" and vb.diff < 0 and vb.pct < 0
    assert vw.kind == "worse" and vw.diff > 0 and vw.pct > 0
    assert vu.kind == "unclear" and abs(vu.diff) <= C.VERDICT_Z * vu.se


def test_verdict_diff_is_per_job_and_paired():
    ref = (10, 20, 30, 40)
    mine = (12, 21, 33, 44)             # Differenzen 2, 1, 3, 4 -> Mittel 2.5 -> je Auftrag (10 Aufträge) 0.25
    v = E.verdict(fake_sweep(ref, mine, n_jobs=10), B_, 0)
    assert v.diff == pytest.approx(0.25)
    assert v.se == pytest.approx(statistics.stdev([2, 1, 3, 4]) / 2 / 10)
    assert v.pct == pytest.approx(100 * 0.25 / 2.5)
    assert v.worse_share == 1.0


def test_verdict_identical_series_is_unclear_and_pct_none_when_reference_never_waits():
    v = E.verdict(fake_sweep((0, 0, 0), (0, 0, 0)), B_, 0)
    assert v.kind == "unclear" and v.diff == 0 and v.pct is None
    v2 = E.verdict(fake_sweep((0, 0, 0), (5, 5, 5)), B_, 0)       # Streuung 0, Unterschied klar
    assert v2.kind == "worse" and v2.pct is None
    v3 = E.verdict(fake_sweep((5, 5, 5), (0, 0, 0)), B_, 0)
    assert v3.kind == "better"


def test_verdict_z_threshold_is_two_standard_errors():
    ref = tuple([0] * 40)
    d = [1.0 if i % 2 else -1.0 for i in range(40)]              # Mittel 0
    mine_small = tuple(x + 0.0 for x in d)
    mean_shift = 0.0
    se = statistics.stdev(d) / math.sqrt(40)
    just_inside = tuple(x + 1.9 * se for x in d)
    just_outside = tuple(x + 2.1 * se for x in d)
    assert E.verdict(fake_sweep(ref, just_inside, n_jobs=1), B_, 0).kind == "unclear"
    assert E.verdict(fake_sweep(ref, just_outside, n_jobs=1), B_, 0).kind == "worse"
    assert mean_shift == 0 and len(mine_small) == 40


# ---------------------------------------------------------------------------------------------------
# Kurven-Zugriffe und Reservebedarf
# ---------------------------------------------------------------------------------------------------
def make_axis_sweep(zero_shares, key=B_, axis=None, n=100):
    """Achse über Abstände; an jedem Punkt hat `key` in Anteil zero_shares[i] der Szenarien Kranwartezeit 0, sonst 100."""
    axis = axis or tuple(range(-len(zero_shares) + 3, 3))
    vals = {k: ((),) * len(axis) for k in C.STRATEGY_KEYS}
    cols = []
    for s in zero_shares:
        z = round(s * n)
        cols.append(tuple([0] * z + [100] * (n - z)))
    vals[key] = tuple(cols)
    vals[E_] = tuple(tuple([100] * n) for _ in axis)
    return E.Sweep("delta", axis, 10, vals, (3,))


def test_reserve_need_first_axis_point_reaching_share():
    sw = make_axis_sweep([0.0, 0.5, 0.94, 0.95, 1.0], axis=(-1, 0, 1, 2, 3))
    assert E.reserve_need(sw, B_) == 2
    assert E.reserve_need(sw, B_, share=1.0) == 3
    assert E.reserve_need(sw, B_, share=0.5) == 0


def test_reserve_need_none_if_never_and_skips_unavailable_points():
    assert E.reserve_need(make_axis_sweep([0.0, 0.2, 0.9], axis=(0, 1, 2)), B_) is None
    sw = make_axis_sweep([1.0, 1.0, 1.0], axis=(-1, 0, 1))
    vals = dict(sw.values)
    vals[B_] = ((), sw.values[B_][1], sw.values[B_][2])         # an Punkt -1 nicht definiert
    sw2 = E.Sweep("delta", sw.axis, sw.n_jobs, vals, sw.kmins)
    assert E.reserve_need(sw2, B_) == 0


def test_reserve_need_requires_fleet_axis():
    sw = fake_sweep((1,), (1,), axis_name="sigma")
    with pytest.raises(ValueError):
        E.reserve_need(sw, B_)


def test_sweep_mean_sem_gains_and_index_of():
    sw = fake_sweep((10, 20, 30), (0, 10, 40), n_jobs=10, axis=(-1, 0, 1))
    assert sw.mean(E_, 0) == pytest.approx(2.0)
    assert sw.sem(E_, 0) == pytest.approx(statistics.stdev([10, 20, 30]) / math.sqrt(3) / 10)
    assert sw.gains(B_, 0) == (10, 10, -10)
    assert sw.paired_diff(B_, E_, 0)[0] == pytest.approx(-10 / 3 / 10)
    assert sw.index_of(0) == 1 and sw.index_of(5) == 2 and sw.index_of(-9) == 0
    assert sw.zero_wait_share(B_, 0) == pytest.approx(1 / 3)
    assert sw.n_scenarios(0) == 3


# ---------------------------------------------------------------------------------------------------
# Ein Szenario, alle Verfahren
# ---------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def inst():
    return make_instance(3, 12, 5)


@pytest.fixture(scope="module")
def mf(inst):
    return min_fleet(inst)


def test_run_strategies_matches_direct_simulation(inst, mf):
    kmin, assign = mf
    noise = draw_noise(len(inst.jobs), 0.25, 42)
    outs = E.run_strategies(inst, kmin, noise, mf)
    assert tuple(o.key for o in outs) == C.STRATEGY_KEYS
    assert outs[0].wait_total == simulate(inst, kmin, rule_earliest, noise).wait_total
    assert outs[1].wait_total == simulate(inst, kmin, make_rule_bestfit(inst), noise).wait_total
    assert outs[3].wait_total == simulate(inst, kmin, make_rule_plan_redispatch(inst, assign), noise).wait_total
    assert all(o.available for o in outs)
    assert outs[0].wait_per_job == pytest.approx(outs[0].wait_total / len(inst.jobs))


def test_plan_strategies_unavailable_below_minimum(inst, mf):
    kmin, _ = mf
    outs = E.run_strategies(inst, kmin - 1, None, mf)
    avail = {o.key: o.available for o in outs}
    assert avail == {E_: True, B_: True, P_: False, R_: False}
    for o in outs:
        if not o.available:
            assert o.wait_total is None and o.late_jobs is None and o.utilization is None and "Mindestflotte" in o.reason
    assert E.run_strategies(inst, kmin, None, mf)[2].available


def test_nominal_plan_at_minimum_has_no_wait(inst, mf):
    kmin, _ = mf
    outs = E.run_strategies(inst, kmin, no_noise(len(inst.jobs)), mf)
    assert E.outcome_of(outs, P_).wait_total == 0
    assert E.outcome_of(outs, R_).wait_total == 0


def test_comparison_rows_delta_against_baseline(inst, mf):
    kmin, _ = mf
    outs = E.run_strategies(inst, kmin, draw_noise(len(inst.jobs), 0.3, 1), mf)
    rows = E.comparison_rows(outs)
    ref = outs[0].wait_total
    assert rows[0].delta_vs_baseline == 0
    for r, o in zip(rows, outs):
        assert r.delta_vs_baseline == o.wait_total - ref
    below = E.comparison_rows(E.run_strategies(inst, kmin - 1, None, mf))
    assert below[2].delta_vs_baseline is None and below[2].reason
    other = E.comparison_rows(outs, baseline=B_)
    assert other[1].delta_vs_baseline == 0


# ---------------------------------------------------------------------------------------------------
# Eigene Auftragsfolge über viele Ziehungen
# ---------------------------------------------------------------------------------------------------
def test_focus_stats_without_noise_is_single_exact_draw(inst, mf):
    kmin, _ = mf
    stats = E.focus_stats(inst, kmin, 0.0, 3, n_draws=50, min_fleet_result=mf)
    assert all(s.n_draws == 1 for s in stats)
    plan = next(s for s in stats if s.key == P_)
    assert plan.mean_per_job == 0 and plan.zero_share == 1.0
    assert plan.se_per_job == 0


def test_focus_stats_equals_manual_average(inst, mf):
    kmin, _ = mf
    n = len(inst.jobs)
    sigma, draws = 0.5, 12
    stats = {s.key: s for s in E.focus_stats(inst, kmin, sigma, 3, n_draws=draws, min_fleet_result=mf)}
    rules = {E_: rule_earliest, B_: make_rule_bestfit(inst)}
    runs = {k: [simulate(inst, kmin, r, draw_noise(n, sigma, E.noise_for(3, j))) for j in range(draws)] for k, r in rules.items()}
    tot = {k: [r.wait_total for r in rs] for k, rs in runs.items()}
    assert len(set(tot[B_])) > 1 and any(tot[B_])                      # die Ziehungen unterscheiden sich wirklich
    for key in rules:
        s = stats[key]
        assert s.mean_per_job == pytest.approx(statistics.fmean(tot[key]) / n)
        assert s.se_per_job == pytest.approx(statistics.stdev(tot[key]) / math.sqrt(draws) / n)
        assert s.zero_share == pytest.approx(sum(1 for t in tot[key] if t == 0) / draws)
        assert s.mean_utilization == pytest.approx(statistics.fmean(r.utilization for r in runs[key]))
    assert stats[E_].paired_diff == (0.0, 0.0)
    d = [(b - a) / n for a, b in zip(tot[E_], tot[B_])]
    assert stats[B_].paired_diff[0] == pytest.approx(statistics.fmean(d))
    assert stats[B_].paired_diff[1] == pytest.approx(statistics.stdev(d) / math.sqrt(draws))
    assert stats[B_].paired_diff[0] > 0                                # Bestfit wartet bei Rauschen mehr als Nächstes freies


def test_focus_stats_below_minimum_marks_plan_unavailable(inst, mf):
    kmin, _ = mf
    stats = {s.key: s for s in E.focus_stats(inst, kmin - 1, 0.2, 3, n_draws=5, min_fleet_result=mf)}
    assert not stats[P_].available and stats[P_].mean_per_job is None
    assert stats[E_].available


def test_focus_stats_deterministic(inst, mf):
    kmin, _ = mf
    a = E.focus_stats(inst, kmin, 0.2, 3, n_draws=6, min_fleet_result=mf)
    b = E.focus_stats(inst, kmin, 0.2, 3, n_draws=6, min_fleet_result=mf)
    assert a == b
    c = E.focus_stats(inst, kmin, 0.2, 4, n_draws=6, min_fleet_result=mf)
    assert a != c


# ---------------------------------------------------------------------------------------------------
# Kurven an echten Läufen
# ---------------------------------------------------------------------------------------------------
PARAMS = dict(n_cranes=3, jobs_per_crane=10, cycle=75, jitter=10, blocks=6)


@pytest.fixture(scope="module")
def fleet_curve():
    return E.fleet_sweep(sigma_pct=25, n_instances=6, n_draws=4, **PARAMS)


def test_fleet_sweep_shape_and_plan_absent_below_minimum(fleet_curve):
    sw = fleet_curve
    assert sw.axis == C.FLEET_SWEEP_DELTAS and sw.axis_name == "delta" and sw.n_jobs == 30
    assert len(sw.kmins) == 6
    for i, d in enumerate(sw.axis):
        for key in C.PLAN_KEYS:
            assert sw.available(key, i) == (d >= 0)
        for key in (E_, B_):                        # leer nur, wenn keine Auftragsfolge so viele Fahrzeuge weniger verträgt
            assert sw.available(key, i) == any(k + d >= 1 for k in sw.kmins)
    i0 = sw.axis.index(0)
    assert sw.n_scenarios(i0) == 6 * 4
    assert all(len(sw.values[k][i0]) == 24 for k in C.STRATEGY_KEYS)


def test_fleet_sweep_skip_rule_drops_instances_below_one_vehicle(fleet_curve):
    sw = fleet_curve
    for i, d in enumerate(sw.axis):
        expected = sum(1 for k in sw.kmins if k + d >= 1) * 4
        assert sw.n_scenarios(i) == expected


def test_fleet_sweep_cross_check_against_direct_simulation():
    sw = E.fleet_sweep(sigma_pct=25, n_instances=3, n_draws=2, deltas=(-1, 0, 2), **PARAMS)
    n = 30
    for ai, d in enumerate(sw.axis):
        got = {k: [] for k in C.STRATEGY_KEYS}
        for k in range(3):
            inst = make_instance(3, 10, k, 75, 10, 6)
            kmin, assign = min_fleet(inst)
            if kmin + d < 1:
                continue
            rules = {E_: rule_earliest, B_: make_rule_bestfit(inst), R_: make_rule_plan_redispatch(inst, assign)}
            for j in range(2):
                noise = draw_noise(n, 0.25, 1000 * k + j)
                for key, rule in rules.items():
                    if key == R_ and d < 0:
                        continue
                    got[key].append(simulate(inst, kmin + d, rule, noise).wait_total)
        for key in (E_, B_, R_):
            assert list(sw.series(key, ai)) == got[key]


def test_sweeps_are_deterministic_and_independent_of_set_seed():
    a = E.fleet_sweep(sigma_pct=20, n_instances=3, n_draws=2, deltas=(0, 1), **PARAMS)
    b = E.fleet_sweep(sigma_pct=20, n_instances=3, n_draws=2, deltas=(0, 1), **PARAMS)
    assert a == b
    n = E.noise_sweep(delta=0, n_instances=3, n_draws=2, sigma_pcts=(0, 20), **PARAMS)
    assert n == E.noise_sweep(delta=0, n_instances=3, n_draws=2, sigma_pcts=(0, 20), **PARAMS)


def test_noise_sweep_sigma_zero_is_single_draw_and_common_random_numbers():
    sw = E.noise_sweep(delta=0, n_instances=4, n_draws=5, sigma_pcts=(0, 10, 30), **PARAMS)
    assert sw.axis_name == "sigma"
    assert sw.n_scenarios(0) == 4 and sw.n_scenarios(1) == 20 and sw.n_scenarios(2) == 20
    # ohne Rauschen wartet der Plan bei der Mindestflotte nie
    assert all(x == 0 for x in sw.series(P_, 0)) and all(x == 0 for x in sw.series(R_, 0))
    # gemeinsame Zufallszahlen: mehr Rauschen kann die Wartezeit von Nächstes freies im Mittel nicht senken
    means = [sw.mean(E_, i) for i in range(3)]
    assert means[0] <= means[1] <= means[2]


def test_default_instance_count_shrinks_for_large_jobs():
    assert E.default_instances(4, 30) == C.SWEEP_INSTANCES
    assert E.default_instances(4, 31) == C.SWEEP_INSTANCES_LARGE
    assert E.default_instances(6, 20) == C.SWEEP_INSTANCES        # genau 120: nicht "groß"


def test_edge_figures_and_measured_order_at_minimum():
    sw = E.fleet_sweep(4, 30, 75, 10, 6, 25, deltas=(-2, -1, 0, 1), n_instances=10, n_draws=5)
    edge = E.edge_figures(sw)
    assert edge[-1] > edge[0] and edge[-2] > edge[-1]
    assert 0 < edge[-1] < 10 and 5 < edge[-2] < 40           # AP-0-Werte: Min-1 ~ 0.4-1.8 s, Min-2 ~ 8-16 s je Auftrag
    i0 = sw.axis.index(0)
    m = {k: sw.mean(k, i0) for k in C.STRATEGY_KEYS}
    assert m[E_] < m[R_] < m[B_] < m[P_]
    assert E.edge_figures(E.fleet_sweep(sigma_pct=0, n_instances=2, n_draws=1, deltas=(0,), **PARAMS)) == {
        0: E.edge_figures(E.fleet_sweep(sigma_pct=0, n_instances=2, n_draws=1, deltas=(0,), **PARAMS))[0], -1: None, -2: None}


def test_reserve_need_on_real_curve_is_monotone_in_share():
    sw = E.fleet_sweep(4, 20, 75, 10, 6, 25, deltas=tuple(range(-2, 5)), n_instances=8, n_draws=4)
    loose = E.reserve_need(sw, E_, share=0.5)
    strict = E.reserve_need(sw, E_, share=0.95)
    assert loose is not None and (strict is None or strict >= loose)


# ---------------------------------------------------------------------------------------------------
# Trifft Bestfit das Minimum? / Abstand zum Optimum
# ---------------------------------------------------------------------------------------------------
def test_minimum_hit_rates_counts():
    h = E.minimum_hit_rates(3, 10, 75, 10, 6, n_instances=8)
    assert h.n_instances == 8 and 0 <= h.bestfit_hits <= 8
    assert h.bestfit_max_excess >= 0 and h.earliest_mean_excess >= 0
    assert (h.bestfit_hits == 8) == (h.bestfit_max_excess == 0)
    total = 0
    for k in range(8):
        inst = make_instance(3, 10, k, 75, 10, 6)
        from fz_dispatch import smallest_fleet
        total += smallest_fleet(inst, make_rule_bestfit) == min_fleet(inst)[0]
    assert h.bestfit_hits == total


def test_gaps_to_optimum_proven_and_unproven(inst, mf):
    kmin, _ = mf
    K = kmin - 1
    best = min(simulate(inst, K, rule_earliest).wait_total, simulate(inst, K, make_rule_bestfit(inst)).wait_total)
    opt = WaitOptimum(K, best, float(best), True, (0,) * len(inst.jobs), "CP-SAT", 1.0)
    gaps = E.gaps_to_optimum(inst, K, opt, mf)
    assert [g.key for g in gaps] == [E_, B_]                   # kein Plan unter dem Minimum
    assert min(g.excess for g in gaps) == 0
    assert all(g.excess >= 0 and g.proven for g in gaps)
    for g in gaps:
        assert (g.ratio is None) if best == 0 else g.ratio == pytest.approx(g.wait / best)
    unproven = WaitOptimum(K, best, 0.0, False, (0,) * len(inst.jobs), "Regel", 1.0)
    assert all(not g.proven for g in E.gaps_to_optimum(inst, K, unproven, mf))


def test_gaps_to_optimum_zero_optimum_gives_no_ratio(inst, mf):
    kmin, _ = mf
    opt = WaitOptimum(kmin, 0, 0.0, True, (0,) * len(inst.jobs), "Matching", 0.0)
    gaps = E.gaps_to_optimum(inst, kmin, opt, mf)
    assert [g.key for g in gaps] == list(C.STRATEGY_KEYS)      # ab dem Minimum sind alle vier definiert
    assert all(g.ratio is None for g in gaps)
    assert next(g for g in gaps if g.key == P_).excess == 0


# ---------------------------------------------------------------------------------------------------
# Nachgeschärft nach der Fehler-Einbau-Prüfung
# ---------------------------------------------------------------------------------------------------
def test_zero_wait_share_counts_only_exact_zero():
    sw = fake_sweep((5, 5, 5, 5), (0, 1, 0, 2))
    assert sw.zero_wait_share(B_, 0) == pytest.approx(0.5)


def test_verdict_boundary_exactly_two_standard_errors_is_unclear():
    v = E.verdict(fake_sweep((0, 0), (3, 1), n_jobs=1), B_, 0)          # Differenz 2, Standardfehler 1
    assert v.diff == pytest.approx(2.0) and v.se == pytest.approx(1.0)
    assert v.kind == "unclear"
    assert E.verdict(fake_sweep((0, 0), (3.2, 1.2), n_jobs=1), B_, 0).kind == "worse"       # 2.2 gegen 2 x 1.0: klar
    assert E.verdict(fake_sweep((0, 0), (4, 0), n_jobs=1), B_, 0).kind == "unclear"         # 2.0 gegen 2 x 2.0


def test_noise_sweep_cross_check_against_direct_simulation():
    sw = E.noise_sweep(delta=-1, n_instances=3, n_draws=2, sigma_pcts=(0, 20, 40), **PARAMS)
    n = 30
    for ai, pct in enumerate(sw.axis):
        got, gotb = [], []
        for k in range(3):
            inst = make_instance(3, 10, k, 75, 10, 6)
            kmin, _ = min_fleet(inst)
            K = kmin - 1
            if K < 1:
                continue
            for j in range(1 if pct == 0 else 2):
                noise = draw_noise(n, pct / 100, 1000 * k + j)
                got.append(simulate(inst, K, rule_earliest, noise).wait_total)
                gotb.append(simulate(inst, K, make_rule_bestfit(inst), noise).wait_total)
        assert list(sw.series(E_, ai)) == got
        assert list(sw.series(B_, ai)) == gotb


def test_minimum_hit_rates_with_controlled_results(monkeypatch):
    insts = [object()] * 4
    monkeypatch.setattr(E, "_params_instances", lambda *a: insts)
    ks = iter([5, 5, 6, 7])
    monkeypatch.setattr(E, "min_fleet", lambda inst: (next(ks), None))
    fleets = {"b": iter([5, 6, 8, 7]), "e": iter([6, 7, 6, 10])}

    def fake_smallest(inst, factory):
        return next(fleets["b" if factory is make_rule_bestfit else "e"])

    monkeypatch.setattr(E, "smallest_fleet", fake_smallest)
    h = E.minimum_hit_rates(3, 10, 75, 10, 6, n_instances=4)
    assert h.n_instances == 4
    assert h.bestfit_hits == 2                                  # Instanzen 0 und 3 (5=5, 7=7)
    assert h.bestfit_max_excess == 2                            # 8 - 6
    assert h.earliest_mean_excess == pytest.approx((1 + 2 + 0 + 3) / 4)


def test_gaps_exact_excess_and_ratio(inst, mf):
    kmin, _ = mf
    K = kmin - 1
    outs = {o.key: o for o in E.run_strategies(inst, K, None, mf) if o.available}
    best = min(o.wait_total for o in outs.values()) - 10
    opt = WaitOptimum(K, best, float(best), True, (0,) * len(inst.jobs), "CP-SAT", 1.0)
    for g in E.gaps_to_optimum(inst, K, opt, mf):
        assert g.wait == outs[g.key].wait_total
        assert g.excess == outs[g.key].wait_total - best and g.excess >= 10
        assert g.ratio == pytest.approx(outs[g.key].wait_total / best)


def test_gaps_unproven_never_negative_but_proven_shows_contradiction(inst, mf):
    kmin, _ = mf
    K = kmin - 1
    big = 10 ** 6
    unproven = WaitOptimum(K, big, 0.0, False, (0,) * len(inst.jobs), "Regel", 1.0)
    assert all(g.excess == 0 for g in E.gaps_to_optimum(inst, K, unproven, mf))
    proven = WaitOptimum(K, big, float(big), True, (0,) * len(inst.jobs), "CP-SAT", 1.0)
    assert all(g.excess < 0 for g in E.gaps_to_optimum(inst, K, proven, mf))    # ein "bewiesenes" Optimum über der Regel wäre ein Widerspruch: sichtbar bleiben


# ---------------------------------------------------------------------------------------------------
# Zusatzkennzahlen eines Ablaufs
# ---------------------------------------------------------------------------------------------------
def test_run_extras_hand_case():
    from fz_dispatch import Run, Trip
    from fz_scenario import Instance, Job

    inst2 = Instance((Job(0, 0, 0), Job(100, 1, 0), Job(200, 1, 0), Job(300, 1, 0), Job(400, 0, 0)), ((10, 10), (10, 10)))
    trips = (Trip(0, 0, 0, 0, 40, 0, 0, 40), Trip(1, 1, 0, 100, 140, 100, 30, 40), Trip(2, 1, 140, 200, 240, 200, 20, 40),
             Trip(3, 1, 240, 300, 340, 300, 10, 40), Trip(4, 1, 340, 400, 440, 400, 40, 40))
    ex = E.run_extras(Run(trips, 2), inst2)
    assert ex.empty_share == pytest.approx((0 + 30 + 20 + 10 + 40) / (5 * 40 + 100))
    assert ex.crane_changes == 1                                    # Fahrzeug 1 fährt 1, 1, 1 und wechselt dann auf Brücke 0; Fahrzeug 0 fährt nur Brücke 0
    assert ex.vehicles_used == 2


def test_run_extras_real_run_bounds(inst, mf):
    kmin, _ = mf
    run = simulate(inst, kmin + 2, rule_earliest)
    ex = E.run_extras(run, inst)
    assert 0 <= ex.empty_share < 1 and 1 <= ex.vehicles_used <= kmin + 2
    assert ex.empty_share == pytest.approx(sum(t.empty_time for t in run.trips) / sum(t.empty_time + t.loaded_time for t in run.trips))
    single = E.run_extras(simulate(inst, 1, rule_earliest), inst)
    assert single.vehicles_used == 1 and single.crane_changes <= len(inst.jobs) - 1


def test_edge_figures_none_for_empty_points():
    """Kleine Terminals: kein Auftragsstrom der Stichprobe verträgt Minimum - 2 (weniger als ein Fahrzeug), der Punkt bleibt leer statt zu stürzen."""
    sw = E.fleet_sweep(2, 10, 150, 10, 3, 0, deltas=(-2, -1, 0), n_instances=3, n_draws=1)
    assert max(sw.kmins) <= 3
    edge = E.edge_figures(sw)
    for d in (0, -1, -2):
        i = sw.axis.index(d)
        assert (edge[d] is None) == (not sw.available(E_, i))
    assert edge[0] is not None
