import math
import random

import pytest

import fz_constants as C
import fz_dispatch as D
import fz_scenario as S
from helpers import (brute_force_min_fleet, random_matrix_instance, recursive_max_matching, reference_timeline, small_instances)


def _rules(inst, assign):
    return {"earliest": D.rule_earliest, "bestfit": D.make_rule_bestfit(inst), "plan": D.make_rule_plan(assign),
            "redispatch": D.make_rule_plan_redispatch(inst, assign)}


def _instances():
    return [S.make_instance(4, 12, 1), S.make_instance(3, 15, 2, cycle=60, jitter=20, blocks=4), S.make_instance(2, 20, 3, cycle=100, blocks=8),
            S.make_instance(5, 10, 4, cycle=65)]


# ---------------- Matching ----------------
def test_iterative_matching_agrees_with_the_recursive_reference_on_random_graphs():
    rng = random.Random(1)
    for _ in range(300):
        n = rng.randint(1, 14)
        adj = [[k for k in range(j + 1, n) if rng.random() < 0.35] for j in range(n)]
        size, match_right = D.max_matching(n, adj)
        assert size == recursive_max_matching(n, adj)
        assert sum(1 for u in match_right if u >= 0) == size
        for v, u in enumerate(match_right):                          # jede Matching-Kante ist eine echte Kante, jeder Knoten höchstens einmal links
            if u >= 0:
                assert v in adj[u]
        assert len({u for u in match_right if u >= 0}) == size


def test_matching_needs_no_recursion_on_long_chains():
    n = 5000
    adj = [[j + 1] if j + 1 < n else [] for j in range(n)]
    size, _ = D.max_matching(n, adj)
    assert size == n - 1
    adj_dense = [[k for k in range(j + 1, min(2000, j + 4))] for j in range(2000)]
    assert D.max_matching(2000, adj_dense)[0] == 1999


def test_matching_with_no_edges_and_with_a_single_node():
    assert D.max_matching(0, []) == (0, [])
    assert D.max_matching(3, [[], [], []]) == (0, [-1, -1, -1])
    assert D.max_matching(1, [[]])[0] == 0


# ---------------- Mindestflotte ----------------
def test_min_fleet_equals_the_brute_force_minimum_on_small_geometric_instances():
    for inst in small_instances(120):
        assert D.min_fleet(inst)[0] == brute_force_min_fleet(inst)


def test_min_fleet_equals_the_brute_force_minimum_on_random_travel_matrices():
    rng = random.Random(9)
    for _ in range(200):
        inst = random_matrix_instance(rng, (4, 9))
        assert D.min_fleet(inst)[0] == brute_force_min_fleet(inst)


def test_the_chains_are_a_valid_partition_with_the_minimum_number_of_vehicles():
    for inst in _instances() + small_instances(20):
        k, assign = D.min_fleet(inst)
        n = len(inst.jobs)
        assert len(assign) == n and set(assign) == set(range(k))
        chains = {}
        for j, v in enumerate(assign):
            chains.setdefault(v, []).append(j)
        for jobs in chains.values():
            assert all(S.can_follow(inst, a, b) for a, b in zip(jobs, jobs[1:]))
        firsts = [chains[v][0] for v in range(k)]
        assert firsts == sorted(firsts)                             # Fahrzeuge nach dem ersten Auftrag ihrer Kette nummeriert


def test_the_matching_plan_has_no_crane_wait_and_one_vehicle_less_cannot_avoid_it():
    for inst in _instances():
        k, assign = D.min_fleet(inst)
        assert D.simulate(inst, k, D.make_rule_plan(assign)).wait_total == 0
    for inst in small_instances(60):
        k, _ = D.min_fleet(inst)
        if k > 1:
            best = min(D.simulate(inst, k - 1, D.make_rule_bestfit(inst)).wait_total, D.simulate(inst, k - 1, D.rule_earliest).wait_total)
            assert best > 0                                          # keine unserer Regeln schafft es; das Brute-Force-Minimum belegt, dass es gar keine Zuordnung gibt


def test_min_fleet_of_a_single_job_and_of_widely_spaced_jobs():
    one = S.custom_instance([(0, 0, 0)], [[10]])
    assert D.min_fleet(one) == (1, [0])
    spaced = S.custom_instance([(0, 0, 0), (1000, 0, 0), (2000, 0, 0)], [[10]])
    assert D.min_fleet(spaced) == (1, [0, 0, 0])
    tight = S.custom_instance([(0, 0, 0), (0, 1, 0), (0, 2, 0)], [[10], [10], [10]])
    assert D.min_fleet(tight) == (3, [0, 1, 2])


def test_min_fleet_reproduces_the_measurement_series():
    for args, expected in (((4, 30, 3, 75, 10, 6), 7), ((2, 10, 0, 60, 0, 3), 4), ((6, 40, 11, 150, 20, 8), 7)):
        k, assign = D.min_fleet(S.make_instance(*args))
        assert k == expected
    assert D.min_fleet(S.make_instance(4, 30, 3, 75, 10, 6))[1][:8] == [0, 1, 2, 3, 0, 2, 4, 1]


# ---------------- Rauschen ----------------
def test_noise_is_reproducible_delaying_only_and_has_the_documented_mean():
    a, b = D.draw_noise(500, 0.25, 4), D.draw_noise(500, 0.25, 4)
    assert a == b and a != D.draw_noise(500, 0.25, 5)
    assert min(a.empty + a.loaded) >= 1.0 and max(a.empty + a.loaded) < 1.25
    assert sum(a.empty + a.loaded) / 1000 == pytest.approx(1.125, abs=0.01)


def test_zero_sigma_gives_exact_factors_and_consumes_no_randomness():
    n = D.draw_noise(10, 0.0, 99)
    assert n.empty == (1.0,) * 10 and n.loaded == (1.0,) * 10
    assert D.draw_noise(10, 0.0, 1) == D.draw_noise(10, 0.0, 2)


def test_noise_depends_only_on_seed_sigma_and_count_not_on_the_instance_or_the_fleet():
    n = D.draw_noise(120, 0.3, 7)
    for inst in (S.make_instance(4, 30, 1), S.make_instance(4, 30, 2)):
        assert D.draw_noise(len(inst.jobs), 0.3, 7) == n
    assert D.draw_noise(120, 0.3, 7).empty[:50] == D.draw_noise(60, 0.3, 7).empty[:50]         # gleicher Strom, nur länger


def test_larger_sigma_scales_the_same_uniform_numbers():
    a, b = D.draw_noise(50, 0.1, 3), D.draw_noise(50, 0.4, 3)
    assert all((y - 1) == pytest.approx(4 * (x - 1)) for x, y in zip(a.empty, b.empty))          # gemeinsame Zufallszahlen: mehr sigma = mehr Verspätung


def test_negative_sigma_is_rejected():
    with pytest.raises(ValueError):
        D.draw_noise(5, -0.1, 0)


# ---------------- Simulation: Handfälle ----------------
def _hand():
    """Zwei Brücken (Fahrzeit zum Block 10 s bzw. 30 s), ein Block. Aufträge: (0, Brücke 0), (5, Brücke 1), (45, Brücke 0)."""
    return S.custom_instance([(0, 0, 0), (5, 1, 0), (45, 0, 0)], [[10], [30]])


def test_hand_case_one_vehicle_makes_the_cranes_wait_and_shifts_the_rest_of_the_sequence():
    run = D.simulate(_hand(), 1, D.rule_earliest)
    t0, t1, t2 = run.trips
    assert (t0.pick, t0.done, t0.wait) == (0, 25, 0)                 # 10 s beladen + 15 s absetzen
    assert (t1.pick, t1.wait) == (55, 50)                            # Ende 25 + 30 s Anfahrt zur Brücke 1 = 55, nominal 5: die Brücke wartet 50 s
    assert t1.done == 55 + 30 + 15
    assert (t2.base, t2.pick, t2.wait) == (45, 110, 65)              # 100 + 10 s zurück zur Brücke 0; die Basis 45 ist nicht von t1 abhängig (andere Brücke)
    assert run.wait_total == 115 and run.late_jobs == 2 and run.wait_per_job == pytest.approx(115 / 3)


def test_hand_case_two_vehicles_remove_all_waiting():
    run = D.simulate(_hand(), 2, D.rule_earliest)
    assert [t.pick for t in run.trips] == [0, 5, 45] and run.wait_total == 0
    assert [t.vehicle for t in run.trips] == [0, 1, 0]               # das erste Fahrzeug ist bei 25 + 10 = 35 <= 45 wieder da


def test_hand_case_crane_coupling_delays_the_next_job_of_the_same_crane():
    inst = S.custom_instance([(0, 0, 0), (40, 0, 0), (80, 1, 0)], [[10], [10]])
    # ein Fahrzeug: Auftrag 0 fertig bei 25, zurück zur Brücke 0 bei 35 <= 40; Auftrag 1 fertig bei 65, zur Brücke 1 bei 75 <= 80
    assert D.simulate(inst, 1, D.rule_earliest).wait_total == 0
    slow = D.draw_noise(3, 0.0, 0)
    noisy = D.Noise((1.0, 3.0, 1.0), (1.0, 1.0, 1.0), 1.0, 0)     # Leerfahrt zu Auftrag 1 dauert 30 s statt 10
    run = D.simulate(inst, 1, D.rule_earliest, noisy)
    assert run.trips[1].pick == 55 and run.trips[1].wait == 15        # 25 + 30
    assert run.trips[1].done == 55 + 10 + 15                          # 80
    assert run.trips[2].pick == 90 and run.trips[2].wait == 10        # 80 + 10 zurück; Basis 80
    assert slow == D.no_noise(3)


def test_a_new_vehicle_is_available_from_minus_infinity():
    inst = S.custom_instance([(-100, 0, 0)], [[10]])                # nominale Zeit vor 0: das Fahrzeug darf trotzdem sofort dort sein
    run = D.simulate(inst, 1, D.rule_earliest)
    assert run.trips[0].pick == -100 and run.wait_total == 0


def test_rounding_up_of_noisy_travel_times():
    inst = S.custom_instance([(0, 0, 0), (100, 0, 0)], [[10]])
    noisy = D.Noise((1.0, 1.01), (1.001, 1.0), 0.0, 0)
    run = D.simulate(inst, 1, D.rule_earliest, noisy)
    assert run.trips[0].loaded_time == 11 + C.SERVICE                # 10,01 -> 11
    assert run.trips[1].empty_time == 11                             # 10,1 -> 11


# ---------------- Simulation: Invarianten ----------------
def test_invariants_hold_for_every_rule_fleet_size_and_noise():
    n_runs = 0
    for inst in _instances():
        k, assign = D.min_fleet(inst)
        n = len(inst.jobs)
        for sigma in (0.0, 0.2, 0.5):
            noise = D.draw_noise(n, sigma, 11)
            for K in range(max(1, k - 2), k + 3):
                for name, rule in _rules(inst, assign).items():
                    if name in ("plan", "redispatch") and K < k:
                        continue
                    run = D.simulate(inst, K, rule, noise)
                    n_runs += 1
                    assert len(run.trips) == n and [t.job for t in run.trips] == list(range(n))
                    last_done, last_pick_crane = {}, {}
                    for t in run.trips:
                        job = inst.jobs[t.job]
                        assert t.wait >= 0 and t.pick >= job.r and t.pick >= t.base
                        if job.crane in last_pick_crane:
                            assert t.pick >= last_pick_crane[job.crane] + C.T_MIN
                        last_pick_crane[job.crane] = t.pick
                        if t.vehicle in last_done:                    # ein Fahrzeug macht nie zwei Dinge gleichzeitig und braucht die Leerfahrt
                            assert t.empty_start == last_done[t.vehicle] and t.pick >= t.empty_start + t.empty_time
                        else:
                            assert t.empty_time == 0 and t.empty_start == t.pick
                        assert t.done == t.pick + t.loaded_time and 0 <= t.vehicle < K
                        last_done[t.vehicle] = t.done
                    assert run.fleet == K and 0 <= run.utilization <= 1.0
    assert n_runs > 150


def test_control_model_matches_the_simulation_pick_done_and_wait_for_arbitrary_choices():
    rng = random.Random(3)
    for inst in _instances() + small_instances(15):
        n = len(inst.jobs)
        noise = D.draw_noise(n, 0.4, rng.randrange(1000))
        K = rng.randint(1, 6)
        for rule in (D.rule_earliest, D.make_rule_bestfit(inst), lambda j, pred, free_at, K_: rng.randrange(K_)):   # auch zufällige Zuordnungen
            run = D.simulate(inst, K, rule, noise)
            pick, done, wait = reference_timeline(inst, [t.vehicle for t in run.trips], noise)
            assert pick == [t.pick for t in run.trips] and done == [t.done for t in run.trips] and wait == [t.wait for t in run.trips]


def test_all_rules_see_the_same_noise_per_leg():
    inst = S.make_instance(4, 12, 1)
    noise = D.draw_noise(len(inst.jobs), 0.3, 5)
    k, assign = D.min_fleet(inst)
    for name, rule in _rules(inst, assign).items():
        run = D.simulate(inst, k, rule, noise)
        last_block = {}
        for t in run.trips:
            job = inst.jobs[t.job]
            assert t.loaded_time == math.ceil(inst.travel[job.crane][job.block] * noise.loaded[t.job]) + C.SERVICE, name
            if t.vehicle in last_block:
                assert t.empty_time == math.ceil(inst.travel[job.crane][last_block[t.vehicle]] * noise.empty[t.job]), name
            last_block[t.vehicle] = job.block


def test_simulation_is_deterministic_and_does_not_mutate_its_inputs():
    inst = S.make_instance(4, 12, 1)
    noise = D.draw_noise(len(inst.jobs), 0.3, 5)
    k, assign = D.min_fleet(inst)
    a = D.simulate(inst, k, D.rule_earliest, noise)
    assert a == D.simulate(inst, k, D.rule_earliest, noise)
    assert inst == S.make_instance(4, 12, 1) and noise == D.draw_noise(len(inst.jobs), 0.3, 5)


def test_without_noise_argument_the_run_is_nominal():
    inst = S.make_instance(4, 12, 1)
    k, _ = D.min_fleet(inst)
    assert D.simulate(inst, k, D.rule_earliest) == D.simulate(inst, k, D.rule_earliest, D.no_noise(len(inst.jobs)))


def test_invalid_simulation_arguments():
    inst = S.make_instance(2, 5, 1)
    with pytest.raises(ValueError):
        D.simulate(inst, 0, D.rule_earliest)
    with pytest.raises(ValueError):
        D.simulate(inst, 2, D.rule_earliest, D.draw_noise(3, 0.1, 0))              # falsche Auftragszahl
    with pytest.raises(ValueError):
        D.simulate(inst, 1, lambda j, p, f, K: 5)                                    # ungültiges Fahrzeug
    k, assign = D.min_fleet(inst)
    if k > 1:
        with pytest.raises(ValueError):
            D.simulate(inst, k - 1, D.make_rule_plan(assign))                        # der Plan braucht mehr Fahrzeuge


# ---------------- Verfahren ----------------
def test_earliest_takes_the_vehicle_with_the_smallest_predicted_arrival_and_the_lowest_index_on_ties():
    assert D.rule_earliest(0, [50, 30, 30, 90], [0] * 4, 4) == 1
    assert D.rule_earliest(0, [D.NEVER, 5, D.NEVER], [0] * 3, 3) == 0


def test_bestfit_takes_the_latest_timely_vehicle_else_the_earliest_arrival():
    inst = S.custom_instance([(100, 0, 0)], [[10]])
    rule = D.make_rule_bestfit(inst)
    assert rule(0, [40, 90, 100, 130], [0] * 4, 4) == 2               # rechtzeitig: 40, 90, 100; das späteste ist 100
    assert rule(0, [D.NEVER, 60, 60], [0] * 3, 3) == 1                # unter den gleich späten der niedrigere Index
    assert rule(0, [130, 120, 120], [0] * 3, 3) == 1                  # keins rechtzeitig: das früheste, bei Gleichstand der niedrigere Index


def test_plan_ignores_the_situation_and_redispatch_follows_it_unless_the_vehicle_is_late():
    inst = S.custom_instance([(100, 0, 0)], [[10]])
    plan = D.make_rule_plan([2])
    assert plan(0, [0, 0, 999], [0] * 3, 3) == 2
    redispatch = D.make_rule_plan_redispatch(inst, [2])
    assert redispatch(0, [0, 0, 100], [0] * 3, 3) == 2                # rechtzeitig (genau bei 100)
    assert redispatch(0, [0, 5, 101], [0] * 3, 3) == 0                # zu spät: frühestes Fahrzeug, niedrigster Index bei Gleichstand


def test_without_noise_the_matching_plan_bestfit_and_redispatch_all_reach_zero_wait_at_the_minimum():
    for inst in _instances():
        k, assign = D.min_fleet(inst)
        assert D.simulate(inst, k, D.make_rule_plan(assign)).wait_total == 0
        assert D.simulate(inst, k, D.make_rule_plan_redispatch(inst, assign)).wait_total == 0
        assert D.simulate(inst, k, D.make_rule_bestfit(inst)).wait_total == 0


def test_more_vehicles_never_hurt_earliest_without_noise_beyond_the_minimum():
    for inst in _instances():
        k, _ = D.min_fleet(inst)
        for K in range(k + 1, k + 4):
            assert D.simulate(inst, K, D.rule_earliest).wait_total == 0


# ---------------- Feste Werte und Befunde der Messreihe ----------------
def test_fixed_values_of_the_measurement_series_without_noise():
    for args, (bf6, ea6) in (((4, 30, 3, 75, 10, 6), ((13, 1), (14, 2))), ((2, 10, 0, 60, 0, 3), ((47, 7), (47, 7))), ((6, 40, 11, 150, 20, 8), ((17, 2), (17, 2)))):
        inst = S.make_instance(*args)
        k, _ = D.min_fleet(inst)
        b = D.simulate(inst, k - 1, D.make_rule_bestfit(inst))
        e = D.simulate(inst, k - 1, D.rule_earliest)
        assert (b.wait_total, b.late_jobs) == bf6 and (e.wait_total, e.late_jobs) == ea6


def test_the_edge_of_the_crane_wait_curve_over_the_fleet_size():
    """Kante der Messreihe (4 Brücken x 30 Aufträge, Takt 75, 60 Instanzen, Bestfit, kein Rauschen): Wartezeit je Auftrag über dem Abstand zum Minimum."""
    per_job = {d: [] for d in range(-5, 2)}
    for seed in range(60):
        inst = S.make_instance(4, 30, seed, cycle=75)
        k, _ = D.min_fleet(inst)
        for d in per_job:
            per_job[d].append(D.simulate(inst, k + d, D.make_rule_bestfit(inst)).wait_per_job)
    mean = {d: sum(v) / len(v) for d, v in per_job.items()}
    expected = {-5: 144.2, -4: 73.1, -3: 38.0, -2: 7.9, -1: 0.4, 0: 0.0, 1: 0.0}
    for d, e in expected.items():
        assert mean[d] == pytest.approx(e, abs=0.06), d
    assert mean[-1] < 1 and mean[-2] > 5 and mean[-3] > 4 * mean[-2]         # ein Fahrzeug weniger fast gratis, zwei weniger nicht


def test_bestfit_almost_always_reaches_the_minimum_and_is_never_more_than_one_vehicle_off():
    """Gemessen, nicht bewiesen: über 99 % der geometrischen Instanzen, nie mehr als +1 (Vorab-Messung: 3 von 432 großen Instanzen, immer +1)."""
    off = total = 0
    for inst in small_instances(150) + _instances():
        k, _ = D.min_fleet(inst)
        b = D.smallest_fleet(inst, D.make_rule_bestfit)
        assert k <= b <= k + 1
        off += b > k
        total += 1
    assert off / total <= 0.01 + 1e-9


def test_known_counterexample_bestfit_needs_one_vehicle_more_than_the_minimum():
    """Kleinstes gefundenes Gegenbeispiel (AP 0, zufällige Fahrzeitmatrix): 6 Aufträge, 3 Brücken, 3 Blöcke, Minimum 2, Bestfit braucht 3."""
    inst = S.custom_instance([(29, 1, 1), (55, 0, 0), (69, 1, 1), (95, 0, 0), (135, 0, 0), (138, 2, 0)], [[5, 28, 31], [34, 7, 43], [6, 60, 50]])
    assert D.min_fleet(inst)[0] == brute_force_min_fleet(inst) == 2
    assert D.smallest_fleet(inst, D.make_rule_bestfit) == 3


def test_earliest_needs_the_minimum_or_more_and_never_beats_it():
    for inst in small_instances(80) + _instances():
        assert D.smallest_fleet(inst, lambda i: D.rule_earliest) >= D.min_fleet(inst)[0]


def test_under_noise_the_static_plan_is_worse_than_the_earliest_rule_at_the_minimum():
    """Robustheits-Befund (Kern der Demo): Flotte = Minimum, Rauschen bis +25 %, Mittel je Auftrag über 40 Instanzen und Ziehungen."""
    plan_w, bf_w, ea_w, rd_w = [], [], [], []
    for seed in range(40):
        inst = S.make_instance(4, 30, seed, cycle=75)
        k, assign = D.min_fleet(inst)
        noise = D.draw_noise(len(inst.jobs), 0.25, seed * 7 + 1)
        plan_w.append(D.simulate(inst, k, D.make_rule_plan(assign), noise).wait_per_job)
        bf_w.append(D.simulate(inst, k, D.make_rule_bestfit(inst), noise).wait_per_job)
        ea_w.append(D.simulate(inst, k, D.rule_earliest, noise).wait_per_job)
        rd_w.append(D.simulate(inst, k, D.make_rule_plan_redispatch(inst, assign), noise).wait_per_job)
    mean = lambda v: sum(v) / len(v)
    assert mean(ea_w) < mean(rd_w) < mean(bf_w) < mean(plan_w)         # gemessen: 0,12 < 0,32 < 0,68 < 1,38 s je Auftrag
    assert mean(plan_w) > 5 * mean(ea_w)


def test_with_two_spare_vehicles_the_earliest_rule_waits_almost_never_but_the_static_plan_does_not_use_them():
    ea, plan = [], []
    for seed in range(40):
        inst = S.make_instance(4, 30, seed, cycle=75)
        k, assign = D.min_fleet(inst)
        noise = D.draw_noise(len(inst.jobs), 0.25, seed * 7 + 1)
        ea.append(D.simulate(inst, k + 2, D.rule_earliest, noise).wait_per_job)
        plan.append(D.simulate(inst, k + 2, D.make_rule_plan(assign), noise).wait_per_job)
    assert sum(ea) / 40 < 0.02 and sum(plan) / 40 > 1.0


def test_smallest_fleet_returns_none_when_kmax_is_too_small():
    inst = S.make_instance(4, 12, 1)
    k, _ = D.min_fleet(inst)
    assert D.smallest_fleet(inst, D.make_rule_bestfit, kmax=k - 1) is None
    assert D.smallest_fleet(inst, D.make_rule_bestfit, kmax=k + 3) == D.smallest_fleet(inst, D.make_rule_bestfit)


def test_run_metrics_on_a_hand_built_run():
    run = D.Run((D.Trip(0, 0, 0, 0, 25, 0, 0, 25), D.Trip(1, 1, 5, 5, 40, 5, 0, 35), D.Trip(2, 0, 25, 60, 90, 45, 10, 30)), 2)
    assert run.wait_total == 15 and run.late_jobs == 1 and run.wait_per_job == pytest.approx(5.0)
    assert run.utilization == pytest.approx((25 + 35 + 10 + 30 + 0 + 0) / (2 * (90 - 0)))
    assert run.trips[2].wait == 15
