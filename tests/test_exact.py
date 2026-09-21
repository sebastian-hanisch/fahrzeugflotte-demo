import dataclasses
import itertools
import random

import pytest

import fz_constants as C
import fz_dispatch as D
import fz_exact as X
import fz_scenario as S
from helpers import brute_force_min_fleet, random_matrix_instance, small_instances


def brute_force_min_wait(inst, K):
    """Kleinste Summe der Kranwartezeit über ALLE Fahrzeugzuordnungen (Symmetriebruch: Fahrzeuge werden der Reihe nach eröffnet), mit der Simulation bewertet."""
    n = len(inst.jobs)
    best = [None]

    def rec(j, used, assign):
        if j == n:
            w = D.simulate(inst, K, D.make_rule_plan(assign)).wait_total
            if best[0] is None or w < best[0]:
                best[0] = w
            return
        for v in range(min(used + 1, K)):
            assign.append(v)
            rec(j + 1, max(used, v + 1), assign)
            assign.pop()

    rec(0, 0, [])
    return best[0]


def brute_force_min_cover(inst):
    """Kleinste Knotenüberdeckung des Graphen 'j kann von k gefolgt werden' durch Probieren aller Teilmengen (nur kleine Instanzen)."""
    n = len(inst.jobs)
    edges = [(j, k) for j in range(n) for k in range(j + 1, n) if S.can_follow(inst, j, k)]
    nodes = [("L", j) for j in range(n)] + [("R", j) for j in range(n)]
    for size in range(0, 2 * n + 1):
        for subset in itertools.combinations(nodes, size):
            chosen = set(subset)
            if all(("L", j) in chosen or ("R", k) in chosen for j, k in edges):
                return size
    return 2 * n


def _mid_instances():
    return [S.make_instance(4, 12, 1), S.make_instance(3, 15, 2, cycle=60, jitter=20, blocks=4), S.make_instance(2, 20, 3, cycle=100, blocks=8),
            S.make_instance(4, 30, 3, cycle=75)]


# ---------------- Beweis der Mindestflotte ----------------
def test_the_proof_verifies_and_matches_the_minimum_fleet_on_many_instances():
    rng = random.Random(4)
    insts = _mid_instances() + small_instances(60) + [random_matrix_instance(rng, (4, 12)) for _ in range(80)]
    for inst in insts:
        proof = X.prove_min_fleet(inst)
        ok, why = X.verify_min_fleet_proof(inst, proof)
        assert ok, why
        assert proof.fleet == D.min_fleet(inst)[0] and proof.cover_size == proof.matching_size == len(inst.jobs) - proof.fleet


def test_the_cover_is_a_minimum_vertex_cover_by_brute_force():
    for inst in small_instances(40):
        if len(inst.jobs) <= 9:
            proof = X.prove_min_fleet(inst)
            assert proof.cover_size == brute_force_min_cover(inst)
            assert proof.fleet == brute_force_min_fleet(inst)


def test_the_chains_belong_to_the_proof_and_are_ordered_by_first_job():
    inst = S.make_instance(4, 12, 1)
    proof = X.prove_min_fleet(inst)
    assert sorted(j for c in proof.chains for j in c) == list(range(len(inst.jobs)))
    assert [c[0] for c in proof.chains] == sorted(c[0] for c in proof.chains)
    assert all(list(c) == sorted(c) for c in proof.chains)
    assert D.simulate(inst, proof.fleet, D.make_rule_plan(D.min_fleet(inst)[1])).wait_total == 0


@pytest.mark.parametrize("tamper", ["drop_cover_node", "drop_job", "swap_jobs", "wrong_fleet", "extra_cover_node", "empty_cover"])
def test_tampered_proofs_are_rejected(tamper):
    inst = S.make_instance(4, 12, 1)
    proof = X.prove_min_fleet(inst)
    if tamper == "drop_cover_node":
        node = next(iter(proof.cover_left or proof.cover_right))
        bad = dataclasses.replace(proof, cover_left=proof.cover_left - {node}, cover_right=proof.cover_right - {node})
    elif tamper == "drop_job":
        chains = [list(c) for c in proof.chains]
        chains[0] = chains[0][:-1]
        bad = dataclasses.replace(proof, chains=tuple(tuple(c) for c in chains if c))
    elif tamper == "swap_jobs":
        long_chain = next(i for i, c in enumerate(proof.chains) if len(c) >= 2)
        chains = [list(c) for c in proof.chains]
        chains[long_chain][0], chains[long_chain][1] = chains[long_chain][1], chains[long_chain][0]
        bad = dataclasses.replace(proof, chains=tuple(tuple(c) for c in chains))
    elif tamper == "wrong_fleet":
        bad = dataclasses.replace(proof, fleet=proof.fleet - 1)
    elif tamper == "extra_cover_node":
        missing = next(j for j in range(len(inst.jobs)) if j not in proof.cover_left)
        bad = dataclasses.replace(proof, cover_left=proof.cover_left | {missing})
    else:
        bad = dataclasses.replace(proof, cover_left=frozenset(), cover_right=frozenset())
    ok, why = X.verify_min_fleet_proof(inst, bad)
    assert not ok
    expected = {"drop_cover_node": "nicht überdeckt", "drop_job": "keine Partition", "swap_jobs": "nicht rechtzeitig", "wrong_fleet": "Flottengröße passt nicht",
                "extra_cover_node": "nicht so groß", "empty_cover": "nicht überdeckt"}
    assert expected[tamper] in why, why


def test_the_proof_of_a_single_job_and_of_a_fully_parallel_stream():
    one = S.custom_instance([(0, 0, 0)], [[10]])
    p = X.prove_min_fleet(one)
    assert p.fleet == 1 and p.cover_size == 0 and X.verify_min_fleet_proof(one, p)[0]
    tight = S.custom_instance([(0, 0, 0), (0, 1, 0), (0, 2, 0)], [[10], [10], [10]])
    p = X.prove_min_fleet(tight)
    assert p.fleet == 3 and p.chains == ((0,), (1,), (2,)) and X.verify_min_fleet_proof(tight, p)[0]


# ---------------- Optimum bei Flottenmangel ----------------
def test_from_the_minimum_fleet_up_the_optimum_is_zero_and_proven_by_the_matching():
    inst = S.make_instance(3, 10, 2)
    k, _ = D.min_fleet(inst)
    for K in (k, k + 1, k + 5):
        r = X.solve_min_wait(inst, K)
        assert (r.wait_best, r.wait_lower, r.proven, r.source) == (0, 0.0, True, "Matching")
        assert X.wait_of_assignment(inst, K, r.assign) == 0


def test_cp_sat_equals_brute_force_on_small_instances_for_one_and_two_vehicles_short():
    checked = 0
    for T in (80, 110):
        for dk in (1, 2):
            for seed in range(14):
                q = 2 if seed % 2 else 3
                inst = S.make_instance(q, 4 if q == 2 else 3, seed, cycle=T)
                k, _ = D.min_fleet(inst)
                K = k - dk
                if K < 1:
                    continue
                r = X.solve_min_wait(inst, K, time_limit_seconds=20)
                assert r.proven and r.source == "CP-SAT" and r.wait_lower == r.wait_best
                assert r.wait_best == brute_force_min_wait(inst, K), (T, dk, seed)
                assert X.wait_of_assignment(inst, K, r.assign) == r.wait_best
                checked += 1
    assert checked >= 40


def test_cp_sat_equals_brute_force_on_random_travel_matrices():
    rng = random.Random(21)
    checked = 0
    for _ in range(60):
        inst = random_matrix_instance(rng, (5, 8))
        k, _ = D.min_fleet(inst)
        for K in range(max(1, k - 2), k):
            r = X.solve_min_wait(inst, K, time_limit_seconds=20)
            assert r.proven and r.wait_best == brute_force_min_wait(inst, K)
            checked += 1
    assert checked > 25


def test_the_optimum_never_exceeds_any_rule_and_never_increases_with_more_vehicles():
    for inst in small_instances(25):
        k, _ = D.min_fleet(inst)
        previous = None
        for K in range(1, k + 1):
            r = X.solve_min_wait(inst, K, time_limit_seconds=20)
            assert r.proven
            for rule in (D.make_rule_bestfit(inst), D.rule_earliest):
                assert r.wait_best <= D.simulate(inst, K, rule).wait_total
            if previous is not None:
                assert r.wait_best <= previous                       # eine Zuordnung mit K-1 Fahrzeugen lässt sich mit K Fahrzeugen nachbilden
            previous = r.wait_best
        assert previous == 0


def test_symmetry_breaking_does_not_change_the_optimum():
    for inst in small_instances(12):
        k, _ = D.min_fleet(inst)
        if k > 1:
            a = X.solve_min_wait(inst, k - 1, 20, symmetry_breaking=True)
            b = X.solve_min_wait(inst, k - 1, 20, symmetry_breaking=False)
            assert a.proven and b.proven and a.wait_best == b.wait_best


def test_fixed_optima_of_two_regression_instances():
    a = S.make_instance(3, 6, 1, cycle=75)
    b = S.make_instance(3, 8, 1, cycle=75)
    ka, kb = D.min_fleet(a)[0], D.min_fleet(b)[0]
    ra = X.solve_min_wait(a, ka - 1, 30)
    rb = X.solve_min_wait(b, kb - 1, 30)
    assert (ra.proven, ra.wait_best) == (True, 106)
    assert (rb.proven, rb.wait_best) == (True, 5)


# ---------------- Zeitlimit und Rückfall ----------------
def test_a_tiny_time_limit_keeps_the_invariants_and_never_claims_a_wrong_optimum():
    inst = S.make_instance(4, 12, 1)
    k, _ = D.min_fleet(inst)
    K = k - 2
    quick = X.solve_min_wait(inst, K, time_limit_seconds=0.01)
    assert 0 <= quick.wait_lower <= quick.wait_best
    assert all(0 <= v < K for v in quick.assign) and len(quick.assign) == len(inst.jobs)
    assert X.wait_of_assignment(inst, K, quick.assign) == quick.wait_best
    if quick.proven:
        assert quick.wait_lower == quick.wait_best
    rules = min(D.simulate(inst, K, r).wait_total for r in (D.make_rule_bestfit(inst), D.rule_earliest))
    assert quick.wait_best <= rules


class _FakeSolver:
    """Ersatz für CpSolver: findet nichts im Zeitlimit."""
    def __init__(self):
        self.parameters = type("P", (), {})()

    def Solve(self, model):
        from ortools.sat.python import cp_model
        return cp_model.UNKNOWN

    def BestObjectiveBound(self):
        return 7.5


def test_without_a_solution_in_time_the_rule_result_is_returned_flagged_not_proven(monkeypatch):
    from ortools.sat.python import cp_model
    monkeypatch.setattr(cp_model, "CpSolver", _FakeSolver)
    inst = S.make_instance(4, 12, 1)
    k, _ = D.min_fleet(inst)
    r = X.solve_min_wait(inst, k - 1, 1.0)
    rules = min(D.simulate(inst, k - 1, rule).wait_total for rule in (D.make_rule_bestfit(inst), D.rule_earliest))
    assert (r.source, r.proven, r.wait_best, r.wait_lower) == ("Regel", False, rules, 7.5)
    assert X.wait_of_assignment(inst, k - 1, r.assign) == rules


def test_the_time_limit_and_worker_settings_reach_the_solver(monkeypatch):
    from ortools.sat.python import cp_model
    seen = {}

    class Spy(_FakeSolver):
        def Solve(self, model):
            seen["limit"] = self.parameters.max_time_in_seconds
            seen["workers"] = self.parameters.num_search_workers
            return cp_model.UNKNOWN

    monkeypatch.setattr(cp_model, "CpSolver", Spy)
    inst = S.make_instance(3, 6, 1)
    k, _ = D.min_fleet(inst)
    X.solve_min_wait(inst, k - 1, 3.5)
    assert seen == {"limit": 3.5, "workers": X.NUM_SEARCH_WORKERS}
    X.solve_min_wait(inst, k - 1)
    assert seen["limit"] == C.EXACT_TIME_LIMIT_SECONDS


def test_invalid_fleet_size():
    with pytest.raises(ValueError):
        X.solve_min_wait(S.make_instance(2, 4, 1), 0)


def test_wait_of_assignment_matches_the_simulation_of_the_plan_rule():
    inst = S.make_instance(3, 8, 2)
    k, assign = D.min_fleet(inst)
    assert X.wait_of_assignment(inst, k, assign) == 0
    bad = [0] * len(inst.jobs)
    assert X.wait_of_assignment(inst, 1, bad) == D.simulate(inst, 1, D.rule_earliest).wait_total


def test_a_valid_but_wasteful_chain_split_is_rejected_because_the_cover_is_smaller_than_the_matching_claims():
    inst = S.make_instance(4, 12, 1)
    proof = X.prove_min_fleet(inst)
    long_chain = next(i for i, c in enumerate(proof.chains) if len(c) >= 2)
    chains = [list(c) for c in proof.chains]
    tail = chains[long_chain].pop()
    chains.append([tail])                                           # gültige Partition mit einem Fahrzeug MEHR
    bad = dataclasses.replace(proof, chains=tuple(tuple(c) for c in chains), fleet=proof.fleet + 1)
    ok, why = X.verify_min_fleet_proof(inst, bad)
    assert not ok and "nicht so groß" in why


class _FeasibleSolver(_FakeSolver):
    """Ersatz für CpSolver: findet eine Lösung (so gut wie die Regel), beweist sie aber nicht."""
    rule_wait = 0

    def Solve(self, model):
        from ortools.sat.python import cp_model
        return cp_model.FEASIBLE

    def ObjectiveValue(self):
        return float(self.rule_wait)

    def BestObjectiveBound(self):
        return 3.0

    def Value(self, var):
        return 1


def test_a_feasible_but_unproven_solution_carries_the_solver_bound_not_the_value(monkeypatch):
    from ortools.sat.python import cp_model
    inst = S.make_instance(4, 12, 1)
    k, _ = D.min_fleet(inst)
    rules = min(D.simulate(inst, k - 1, rule).wait_total for rule in (D.make_rule_bestfit(inst), D.rule_earliest))
    _FeasibleSolver.rule_wait = rules
    monkeypatch.setattr(cp_model, "CpSolver", _FeasibleSolver)
    r = X.solve_min_wait(inst, k - 1, 1.0)
    assert (r.source, r.proven, r.wait_best, r.wait_lower) == ("CP-SAT", False, rules, 3.0)
    assert r.wait_lower < r.wait_best


def test_the_rule_fallback_takes_the_better_of_bestfit_and_earliest():
    inst = S.make_instance(4, 8, 0, cycle=75)                       # Flotte 5 von Minimum 7: earliest 109 s, Bestfit 131 s
    k, _ = D.min_fleet(inst)
    assert (k, D.simulate(inst, 5, D.make_rule_bestfit(inst)).wait_total, D.simulate(inst, 5, D.rule_earliest).wait_total) == (7, 131, 109)
    wait, assign = X._best_rule_assignment(inst, 5)
    assert wait == 109 and X.wait_of_assignment(inst, 5, assign) == 109
    assert X._best_rule_assignment(S.make_instance(3, 6, 172, cycle=75), 3)[0] == min(
        D.simulate(S.make_instance(3, 6, 172, cycle=75), 3, r).wait_total for r in (D.make_rule_bestfit(S.make_instance(3, 6, 172, cycle=75)), D.rule_earliest))
