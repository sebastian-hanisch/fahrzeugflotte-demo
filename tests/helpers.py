"""Testhilfen: unabhängige Vergleichsimplementierungen (Brute Force, Rekursion, Abhängigkeitsgraph statt Schleife) und Instanz-Generatoren."""
import math
import random
from functools import lru_cache

import fz_constants as C
import fz_scenario as S


def small_instances(n=120, seed0=0):
    """Kleine Instanzen (2 bis 3 Brücken, 3 bis 4 Aufträge je Brücke, verschiedene Takte und Blockzahlen) zum Vergleich mit Brute Force."""
    out = []
    for i in range(n):
        rng = random.Random(seed0 + i)
        q = rng.choice([2, 3])
        out.append(S.make_instance(q, rng.choice([3, 4]) if q == 2 else 3, seed0 + i, cycle=rng.choice([50, 65, 80, 110]),
                                   jitter=rng.choice([0, 10, 20]), blocks=rng.choice([3, 5, 8])))
    return out


def random_matrix_instance(rng, n_jobs=(4, 8)):
    """Nicht geometrische Fahrzeitmatrix (Zufallszahlen), Mindestabstand je Brücke hergestellt."""
    q, b = rng.randint(2, 3), rng.randint(2, 4)
    travel = [[rng.randint(5, 60) for _ in range(b)] for _ in range(q)]
    raw, last = [], {}
    for _ in range(rng.randint(*n_jobs)):
        cq = rng.randrange(q)
        r = max(rng.randint(0, 150), last.get(cq, -10**9) + C.T_MIN)
        last[cq] = r
        raw.append((r, cq, rng.randrange(b)))
    return S.custom_instance(raw, travel)


def brute_force_min_fleet(inst):
    """Kleinste Kettenzahl durch vollständiges Probieren (jeder Auftrag hängt sich an eine bestehende Kette oder beginnt eine neue): unabhängig vom Matching."""
    n = len(inst.jobs)
    best = [n]

    def rec(j, last_of_chain):
        if len(last_of_chain) >= best[0]:
            return
        if j == n:
            best[0] = len(last_of_chain)
            return
        for c, last in enumerate(last_of_chain):
            if S.can_follow(inst, last, j):
                last_of_chain[c] = j
                rec(j + 1, last_of_chain)
                last_of_chain[c] = last
        last_of_chain.append(j)
        rec(j + 1, last_of_chain)
        last_of_chain.pop()

    rec(0, [])
    return best[0]


def recursive_max_matching(n, adj):
    """Klassisches rekursives Kuhn-Verfahren (Vergleichsimplementierung, nur für kleine Graphen)."""
    match_right = [-1] * n

    def aug(u, seen):
        for v in adj[u]:
            if v in seen:
                continue
            seen.add(v)
            if match_right[v] < 0 or aug(match_right[v], seen):
                match_right[v] = u
                return True
        return False

    return sum(aug(u, set()) for u in range(n))


def reference_timeline(inst, choices, noise):
    """KONTROLLMODELL: Aufnahme-, Ende- und Wartezeiten bei gegebener Fahrzeugzuordnung `choices` (Fahrzeug je Auftrag), berechnet über die Abhängigkeiten
    (memoisierte Rekursion über Vorgänger-Auftrag derselben Brücke und desselben Fahrzeugs) statt über eine Schleife in Auftragsreihenfolge."""
    n = len(inst.jobs)
    prev_crane, prev_vehicle = [None] * n, [None] * n
    last_c, last_v = {}, {}
    for j, job in enumerate(inst.jobs):
        prev_crane[j] = last_c.get(job.crane)
        prev_vehicle[j] = last_v.get(choices[j])
        last_c[job.crane] = j
        last_v[choices[j]] = j

    @lru_cache(maxsize=None)
    def pick(j):
        job = inst.jobs[j]
        base = job.r if prev_crane[j] is None else max(job.r, pick(prev_crane[j]) + C.T_MIN)
        if prev_vehicle[j] is None:
            return base
        pj = prev_vehicle[j]
        drive = math.ceil(inst.travel[job.crane][inst.jobs[pj].block] * noise.empty[j])
        return max(base, done(pj) + drive)

    @lru_cache(maxsize=None)
    def done(j):
        job = inst.jobs[j]
        return pick(j) + math.ceil(inst.travel[job.crane][job.block] * noise.loaded[j]) + C.SERVICE

    @lru_cache(maxsize=None)
    def base_of(j):
        job = inst.jobs[j]
        return job.r if prev_crane[j] is None else max(job.r, pick(prev_crane[j]) + C.T_MIN)

    import sys
    sys.setrecursionlimit(20000)
    return [pick(j) for j in range(n)], [done(j) for j in range(n)], [pick(j) - base_of(j) for j in range(n)]
