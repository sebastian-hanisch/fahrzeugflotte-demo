import math

import pytest

import fz_constants as C
import fz_scenario as S

# Feste Werte, mit dem Code der Vorab-Messreihe (hafen-planung/messreihe_fahrzeug/fahrzeug.py) erzeugt
REFERENCE = [
    # (Q, m, seed, cycle, jitter, blocks): (Aufträge, Summe der Aufnahmezeiten, erste drei Aufträge, letzter Auftrag, Fahrzeitzeile Brücke 0, letzte 3 der letzten Brücke)
    ((4, 30, 3, 75, 10, 6), (120, 135401, [(28, 2, 2), (38, 0, 4), (42, 3, 3)], (2255, 1, 0), [21, 31, 34, 44, 47, 56], [36, 33, 24])),
    ((2, 10, 0, 60, 0, 3), (20, 6000, [(6, 1, 2), (54, 0, 1), (66, 1, 1)], (594, 0, 1), [21, 34, 40], [23, 27, 33])),
    ((6, 40, 11, 150, 20, 8), (240, 721810, [(12, 4, 0), (24, 1, 7), (77, 5, 0)], (5992, 2, 1), [21, 31, 34, 44, 47, 57, 60, 70], [50, 47, 37])),
]


@pytest.mark.parametrize("args,expected", REFERENCE)
def test_instance_reproduces_the_measurement_series(args, expected):
    n, total, first, last, row0, tail = expected
    inst = S.make_instance(*args)
    assert len(inst.jobs) == n and sum(j.r for j in inst.jobs) == total
    assert [(j.r, j.crane, j.block) for j in inst.jobs[:3]] == first
    assert (inst.jobs[-1].r, inst.jobs[-1].crane, inst.jobs[-1].block) == last
    assert list(inst.travel[0]) == row0 and list(inst.travel[-1][:3]) == tail


def _crane_x(q):
    return q * C.CRANE_SPACING


def test_travel_times_follow_the_geometry_and_are_rounded_up():
    inst = S.make_instance(3, 5, 1, blocks=5)
    yard = 3 * C.CRANE_SPACING + 30
    for q in range(3):
        for b in range(5):
            bx, by = C.BLOCK_MARGIN + b * yard / 4, C.YARD_OFFSET + C.YARD_STAGGER * (b % 2)
            exact = (abs(_crane_x(q) - bx) + by) / C.SPEED
            assert inst.travel[q][b] == math.ceil(exact)
            assert inst.travel[q][b] >= exact and inst.travel[q][b] - exact < 1        # aufgerundet, nie gerundet
            assert isinstance(inst.travel[q][b], int)


def test_jobs_are_sorted_respect_the_minimum_gap_per_crane_and_stay_in_range():
    for seed in range(20):
        inst = S.make_instance(4, 12, seed, cycle=60, jitter=20, blocks=4)
        assert [j.r for j in inst.jobs] == sorted(j.r for j in inst.jobs)
        last = {}
        for j in inst.jobs:
            assert 0 <= j.crane < 4 and 0 <= j.block < 4
            if j.crane in last:
                assert j.r - last[j.crane] >= C.T_MIN
            last[j.crane] = j.r
        assert {q: sum(1 for j in inst.jobs if j.crane == q) for q in range(4)} == {0: 12, 1: 12, 2: 12, 3: 12}


def test_same_seed_same_instance_and_the_seed_changes_it():
    assert S.make_instance(4, 10, 5) == S.make_instance(4, 10, 5)
    assert S.make_instance(4, 10, 5) != S.make_instance(4, 10, 6)


def test_every_parameter_has_an_effect():
    base = S.make_instance(4, 10, 5)
    for kw in (dict(n_cranes=3), dict(jobs_per_crane=12), dict(cycle=100), dict(jitter=0), dict(blocks=4)):
        args = dict(n_cranes=4, jobs_per_crane=10, seed=5)
        args.update(kw)
        assert S.make_instance(**args) != base, kw


def test_a_longer_cycle_stretches_the_horizon_and_zero_jitter_gives_regular_gaps():
    short, long_ = S.make_instance(3, 10, 2, cycle=60), S.make_instance(3, 10, 2, cycle=120)
    assert long_.jobs[-1].r > short.jobs[-1].r
    regular = S.make_instance(2, 8, 4, cycle=80, jitter=0)
    for q in range(2):
        rs = [j.r for j in regular.jobs if j.crane == q]
        assert {b - a for a, b in zip(rs, rs[1:])} == {80}


def test_shape_properties():
    inst = S.make_instance(5, 7, 0, blocks=3)
    assert inst.n_cranes == 5 and inst.n_blocks == 3 and len(inst.jobs) == 35


def test_invalid_arguments_are_rejected():
    for args in ((0, 5, 0), (3, 0, 0)):
        with pytest.raises(ValueError):
            S.make_instance(*args)
    with pytest.raises(ValueError):
        S.make_instance(3, 5, 0, blocks=0)


# ---------------- Rohdaten-Instanz ----------------
def test_custom_instance_sorts_and_keeps_the_data():
    inst = S.custom_instance([(100, 1, 0), (0, 0, 1), (50, 0, 0)], [[10, 20], [30, 40]])
    assert [(j.r, j.crane, j.block) for j in inst.jobs] == [(0, 0, 1), (50, 0, 0), (100, 1, 0)]
    assert inst.travel == ((10, 20), (30, 40)) and inst.n_cranes == 2 and inst.n_blocks == 2


@pytest.mark.parametrize("jobs,travel", [
    ([], [[10]]),                                                   # kein Auftrag
    ([(0, 0, 0), (20, 0, 0)], [[10]]),                              # Mindestabstand verletzt
    ([(0, 1, 0)], [[10]]),                                          # Brücke fehlt in der Matrix
    ([(0, 0, 1)], [[10]]),                                          # Block fehlt in der Matrix
    ([(0, 0, 0)], [[10], [10, 20]]),                                # nicht rechteckig
    ([(0, 0, 0)], [[0]]),                                           # Fahrzeit < 1
    ([(0, 0, 0)], [[10.5]]),                                        # keine ganze Sekunde
    ([(0, 0, 0)], []),                                              # leere Matrix
])
def test_custom_instance_rejects_invalid_data(jobs, travel):
    with pytest.raises(ValueError):
        S.custom_instance(jobs, travel)


def test_exactly_the_minimum_gap_is_allowed():
    S.custom_instance([(0, 0, 0), (C.T_MIN, 0, 0)], [[10]])
    with pytest.raises(ValueError):
        S.custom_instance([(0, 0, 0), (C.T_MIN - 1, 0, 0)], [[10]])


# ---------------- can_follow ----------------
def test_can_follow_uses_loaded_trip_service_and_the_way_back_to_the_next_crane():
    # Auftrag 0: Brücke 0 -> Block 0 (10 s), Absetzen 15 s, dann zurück zur Brücke 1 (Block 0 -> Brücke 1: 30 s): frühestens r + 10 + 15 + 30 = 55
    inst = S.custom_instance([(0, 0, 0), (55, 2, 0), (54, 1, 0)], [[10], [30], [30]])
    assert [(j.r, j.crane) for j in inst.jobs] == [(0, 0), (54, 1), (55, 2)]
    assert not S.can_follow(inst, 0, 1)                            # 54 < 55
    assert S.can_follow(inst, 0, 2)                                # genau 55 reicht


def test_can_follow_is_not_symmetric_and_depends_on_the_block_of_the_first_job():
    inst = S.custom_instance([(0, 0, 0), (100, 0, 1)], [[10, 90]])
    assert S.can_follow(inst, 0, 1)                                # Block 0 -> Brücke 0: 10 s
    assert not S.can_follow(inst, 1, 0)


def test_validation_messages_name_the_problem():
    with pytest.raises(ValueError, match="mindestens 1"):
        S.make_instance(3, 5, 0, blocks=0)
    with pytest.raises(ValueError, match="mindestens 1"):
        S.make_instance(0, 5, 0)
    with pytest.raises(ValueError, match="mindestens 1"):
        S.make_instance(3, 0, 0)
    for travel in ([], [[]], [[10], [10, 20]]):
        with pytest.raises(ValueError, match="rechteckig"):
            S.custom_instance([(0, 0, 0)], travel)
    with pytest.raises(ValueError, match="ganze Sekunden"):
        S.custom_instance([(0, 0, 0)], [[0]])
    with pytest.raises(ValueError, match="mindestens ein Auftrag"):
        S.custom_instance([], [[10]])
    with pytest.raises(ValueError, match="Mindestabstand"):
        S.custom_instance([(0, 0, 0), (10, 0, 0)], [[10]])
    with pytest.raises(ValueError, match="außerhalb"):
        S.custom_instance([(0, 3, 0)], [[10]])
