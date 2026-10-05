"""Orakel auf anderem Rechenweg:
* Fahrzeitmatrix in exakter Bruchrechnung (Fraction) statt Gleitkomma: aufgerundet auf ganze Sekunden, für jede Brückenzahl und Blockzahl der Regler.
* Eigene, einfache Ablaufrechnung je Zuordnung (jedes Fahrzeug arbeitet seine Aufträge in Reihenfolge ab) gegen `simulate` mit allen vier Verfahren und Rauschen.
* Mindestflotte und Optimum der Kranwartezeit durch Aufzählen aller Zuordnungen (Fahrzeugnamen in Erstauftritts-Reihenfolge) gegen Matching und CP-SAT."""
import math
import random
from fractions import Fraction

import pytest

import fz_constants as C
import fz_dispatch as D
import fz_exact as X
import fz_scenario as SC


def own_run(inst, assign, noise=None):
    n = len(inst.jobs)
    ne, nl = (noise.empty, noise.loaded) if noise else ([1.0] * n, [1.0] * n)
    pick, wait, done, last_pick, free, pos = [], [], [], {}, {}, {}
    for j, job in enumerate(inst.jobs):
        v = assign[j]
        base = job.r if job.crane not in last_pick else max(job.r, last_pick[job.crane] + C.T_MIN)
        arrival = free[v] + math.ceil(inst.travel[job.crane][pos[v]] * ne[j]) if v in free else -10**9
        p = max(base, arrival)
        d = p + math.ceil(inst.travel[job.crane][job.block] * nl[j]) + C.SERVICE
        pick.append(p), wait.append(p - base), done.append(d)
        last_pick[job.crane], free[v], pos[v] = p, d, job.block
    return pick, wait, done


def brute_min_wait(inst, K):
    n, best = len(inst.jobs), [None]

    def rec(j, used, assign):
        if j == n:
            w = sum(own_run(inst, assign)[1])
            best[0] = w if best[0] is None or w < best[0] else best[0]
            return
        for v in range(min(used + 1, K)):
            rec(j + 1, max(used, v + 1), assign + [v])

    rec(0, 0, [])
    return best[0]


def small_instance(seed):
    rng = random.Random(seed)
    nq, blocks = rng.randint(1, 3), rng.randint(1, 4)
    travel = [[rng.randint(8, 60) for _ in range(blocks)] for _ in range(nq)]
    jobs = []
    for q in range(nq):
        t = rng.randint(0, 40)
        for _ in range(rng.randint(1, 4)):
            jobs.append((t, q, rng.randrange(blocks)))
            t += rng.randint(C.T_MIN, 90)
    return SC.custom_instance(jobs[:7], travel)


def test_travel_times_are_the_exactly_rounded_up_geometry_for_every_slider_combination():
    for n_cranes in range(C.N_CRANES_RANGE[0], C.N_CRANES_RANGE[1] + 1):
        for blocks in range(C.BLOCKS_RANGE[0], C.BLOCKS_RANGE[1] + 1):
            inst = SC.make_instance(n_cranes, 1, 0, blocks=blocks)
            yard = n_cranes * C.CRANE_SPACING + 30
            for q in range(n_cranes):
                for b in range(blocks):
                    x = C.BLOCK_MARGIN + Fraction(b * yard, blocks - 1)
                    y = C.YARD_OFFSET + C.YARD_STAGGER * (b % 2)
                    assert inst.travel[q][b] == math.ceil((abs(Fraction(q * C.CRANE_SPACING) - x) + y) / C.SPEED)


@pytest.mark.parametrize("seed", range(40))
def test_simulation_equals_the_own_run_of_its_assignment_under_noise(seed):
    rng = random.Random(seed)
    inst = SC.make_instance(rng.randint(2, 6), rng.randint(3, 10), rng.randint(0, 9999), cycle=rng.choice(range(60, 151, 15)), jitter=rng.choice([0, 10, 20]), blocks=rng.randint(3, 8))
    kmin, chain = D.min_fleet(inst)
    K = max(1, kmin + rng.randint(-3, 3))
    noise = D.draw_noise(len(inst.jobs), rng.choice([0, 0.1, 0.5]), seed)
    rules = [D.rule_earliest, D.make_rule_bestfit(inst)] + ([D.make_rule_plan(chain), D.make_rule_plan_redispatch(inst, chain)] if K >= kmin else [])
    for rule in rules:
        run = D.simulate(inst, K, rule, noise)
        pick, wait, done = own_run(inst, [t.vehicle for t in run.trips], noise)
        assert [t.pick for t in run.trips] == pick and [t.wait for t in run.trips] == wait and [t.done for t in run.trips] == done


@pytest.mark.parametrize("seed", range(30))
def test_minimum_fleet_and_optimum_wait_equal_the_enumeration_of_all_assignments(seed):
    inst = small_instance(seed)
    kmin, chain = D.min_fleet(inst)
    assert sum(own_run(inst, chain)[1]) == 0 and max(chain) + 1 == kmin
    assert brute_min_wait(inst, kmin) == 0 and (kmin == 1 or brute_min_wait(inst, kmin - 1) > 0)
    assert X.verify_min_fleet_proof(inst, X.prove_min_fleet(inst))[0]
    for K in range(1, kmin):
        res = X.solve_min_wait(inst, K, 20)
        assert res.proven and res.wait_best == brute_min_wait(inst, K) == X.wait_of_assignment(inst, K, res.assign)
