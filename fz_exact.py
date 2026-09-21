"""Exakte Ergebnisse: Beweis der Mindestflotte und Optimum der Kranwartezeit bei Flottenmangel.

1. Mindestflotte mit BEWEIS. Die Fahrzeugketten kommen aus einem maximalen Matching. Dass kein Matching größer sein kann, belegt eine Knotenüberdeckung gleicher
   Größe (Satz von König): Jede Kante des Graphen "Auftrag j kann von k gefolgt werden" hat einen Endpunkt in der Überdeckung, und die Überdeckung ist so groß wie das
   Matching. `verify_min_fleet_proof` prüft das ohne den Löser: es gibt keine bessere Zuordnung.
2. Optimum bei Flottenmangel (weniger Fahrzeuge als das Minimum): kleinste Summe der Kranwartezeit bei nominalen Zeiten mit Kran-Kopplung, als CP-SAT-Modell
   (ein Kreis je Fahrzeug, die Kopplung als max-Gleichung). Zeitlimit; ohne Beweis liefert das Ergebnis ein INTERVALL [untere Schranke, beste bekannte Lösung]
   und `proven` ist False, nie ein unbewiesener Wert als Optimum."""

import os
import time
from dataclasses import dataclass

import fz_constants as C
from fz_dispatch import (make_rule_bestfit, make_rule_plan, max_matching, min_fleet, rule_earliest, simulate)
from fz_scenario import can_follow

NUM_SEARCH_WORKERS = min(8, os.cpu_count() or 1)


# ---------------------------------------------------------------------------------------------------
# Mindestflotte mit Beweis
# ---------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class MinFleetProof:
    fleet: int              # Mindestflotte = n - Matching
    chains: tuple           # eine Kette (Tupel von Auftragsnummern) je Fahrzeug
    matching_size: int
    cover_left: frozenset   # Knotenüberdeckung: linke Knoten (Vorgänger) ...
    cover_right: frozenset  # ... und rechte Knoten (Nachfolger); |Überdeckung| == matching_size

    @property
    def cover_size(self):
        return len(self.cover_left) + len(self.cover_right)


def _adjacency(inst):
    n = len(inst.jobs)
    return [[k for k in range(j + 1, n) if can_follow(inst, j, k)] for j in range(n)]


def prove_min_fleet(inst):
    """Mindestflotte, Fahrzeugketten und die Überdeckung, die ihre Optimalität beweist (König: kleinste Überdeckung = größtes Matching)."""
    n = len(inst.jobs)
    adj = _adjacency(inst)
    size, match_right = max_matching(n, adj)
    match_left = {u: v for v, u in enumerate(match_right) if u >= 0}
    # Alternierende Wege ab den ungematchten linken Knoten: links -> rechts über beliebige Kanten, rechts -> links über Matching-Kanten
    reach_left = {u for u in range(n) if u not in match_left}
    reach_right = set()
    stack = list(reach_left)
    while stack:
        u = stack.pop()
        for v in adj[u]:
            if v not in reach_right:
                reach_right.add(v)
                w = match_right[v]
                if w >= 0 and w not in reach_left:
                    reach_left.add(w)
                    stack.append(w)
    cover_left = frozenset(u for u in range(n) if u not in reach_left)
    cover_right = frozenset(reach_right)
    fleet, assign = min_fleet(inst)
    chains = {}
    for j, v in enumerate(assign):
        chains.setdefault(v, []).append(j)
    return MinFleetProof(fleet, tuple(tuple(chains[v]) for v in range(fleet)), size, cover_left, cover_right)


def verify_min_fleet_proof(inst, proof):
    """Prüft den Beweis ohne den Löser: (1) die Ketten sind eine zulässige Partition, (2) jede Kante ist überdeckt, (3) |Überdeckung| = n - Kettenzahl.
    Dann gibt es keine Überdeckung des Auftragsstroms mit weniger Ketten (Matching-Größe <= Überdeckung für jedes Matching). Gibt (ok, Begründung) zurück."""
    n = len(inst.jobs)
    seen = sorted(j for chain in proof.chains for j in chain)
    if seen != list(range(n)):
        return False, "die Ketten sind keine Partition der Aufträge"
    for chain in proof.chains:
        if any(not can_follow(inst, a, b) for a, b in zip(chain, chain[1:])):
            return False, "eine Kette enthält einen Übergang, der nicht rechtzeitig möglich ist"
    if len(proof.chains) != proof.fleet:
        return False, "Flottengröße passt nicht zur Kettenzahl"
    adj = _adjacency(inst)
    for j in range(n):
        for k in adj[j]:
            if j not in proof.cover_left and k not in proof.cover_right:
                return False, f"die Kante {j} -> {k} ist nicht überdeckt"
    if proof.cover_size != n - proof.fleet:
        return False, "die Überdeckung ist nicht so groß wie das Matching"
    return True, "bewiesen: keine Zuordnung mit weniger Fahrzeugen ohne Kranwartezeit"


# ---------------------------------------------------------------------------------------------------
# Optimum der Kranwartezeit bei Flottenmangel
# ---------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class WaitOptimum:
    fleet: int
    wait_best: int          # beste bekannte Summe der Kranwartezeit (nominal): Optimum, wenn proven
    wait_lower: float       # bewiesene untere Schranke
    proven: bool
    assign: tuple           # Fahrzeug je Auftrag der besten bekannten Zuordnung
    source: str             # "CP-SAT" oder "Regel" (Rückfall, wenn CP-SAT im Zeitlimit nichts Besseres fand)
    wall_ms: float


def _best_rule_assignment(inst, K):
    """Beste unserer Regeln bei nominalen Zeiten: Rückfall und Hint. Rückgabe: (Summe Kranwartezeit, Zuordnung)."""
    best = None
    for rule in (make_rule_bestfit(inst), rule_earliest):
        run = simulate(inst, K, rule)
        if best is None or run.wait_total < best[0]:
            best = (run.wait_total, tuple(t.vehicle for t in run.trips))
    return best


def solve_min_wait(inst, K, time_limit_seconds=C.EXACT_TIME_LIMIT_SECONDS, symmetry_breaking=True):
    """Kleinste Summe der Kranwartezeit mit K Fahrzeugen bei nominalen Zeiten (Kran-Kopplung). Ab der Mindestflotte ist das Optimum 0 (bewiesen durch das
    Matching, kein Löserlauf nötig)."""
    from ortools.sat.python import cp_model

    t0 = time.perf_counter()
    n = len(inst.jobs)
    if K < 1:
        raise ValueError("mindestens ein Fahrzeug")
    kmin, chain_assign = min_fleet(inst)
    if K >= kmin:
        assign = tuple(chain_assign)
        return WaitOptimum(K, 0, 0.0, True, assign, "Matching", (time.perf_counter() - t0) * 1000)

    rule_wait, rule_assign = _best_rule_assignment(inst, K)
    horizon = max(j.r for j in inst.jobs) + n * (2 * max(max(row) for row in inst.travel) + C.SERVICE + C.T_MIN) + 1000
    m = cp_model.CpModel()
    p = [m.NewIntVar(inst.jobs[j].r, horizon, f"p{j}") for j in range(n)]
    base = [m.NewIntVar(inst.jobs[j].r, horizon, f"b{j}") for j in range(n)]
    last_of_crane, wait_terms = {}, []
    for j, job in enumerate(inst.jobs):
        prev = last_of_crane.get(job.crane)
        if prev is None:
            m.Add(base[j] == job.r)
        else:
            m.AddMaxEquality(base[j], [m.NewConstant(job.r), p[prev] + C.T_MIN])
        m.Add(p[j] >= base[j])
        wait_terms.append(p[j] - base[j])
        last_of_crane[job.crane] = j
    present = [[m.NewBoolVar(f"y{v}_{j}") for j in range(n)] for v in range(K)]
    for v in range(K):
        arcs = [(0, 0, m.NewBoolVar(f"idle{v}"))]
        for j in range(n):
            arcs.append((0, j + 1, m.NewBoolVar(f"s{v}_{j}")))
            arcs.append((j + 1, 0, m.NewBoolVar(f"e{v}_{j}")))
            arcs.append((j + 1, j + 1, present[v][j].Not()))
            a = inst.jobs[j]
            for k in range(j + 1, n):
                b = inst.jobs[k]
                lit = m.NewBoolVar(f"a{v}_{j}_{k}")
                arcs.append((j + 1, k + 1, lit))
                m.Add(p[k] >= p[j] + inst.travel[a.crane][a.block] + C.SERVICE + inst.travel[b.crane][a.block]).OnlyEnforceIf(lit)
        m.AddCircuit(arcs)
    for j in range(n):
        m.AddExactlyOne(present[v][j] for v in range(K))
    for v in range(1, K) if symmetry_breaking else ():      # Symmetriebruch (Fahrzeuge sind gleich): v darf erst dienen, wenn v-1 vorher schon diente
        for j in range(n):
            m.Add(sum(present[v - 1][i] for i in range(j)) >= present[v][j])
    m.Minimize(sum(wait_terms))
    for v in range(K):                                      # Startlösung: beste Regel
        for j in range(n):
            m.AddHint(present[v][j], int(rule_assign[j] == v))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = NUM_SEARCH_WORKERS
    status = solver.Solve(m)
    lower = solver.BestObjectiveBound()
    wall = (time.perf_counter() - t0) * 1000
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        value = int(round(solver.ObjectiveValue()))
        # Zuordnung aus den Kreisen: Fahrzeuge nummerieren wie in `present`
        assign = tuple(next(v for v in range(K) if solver.Value(present[v][j])) for j in range(n))
        if value <= rule_wait:
            return WaitOptimum(K, value, float(value) if status == cp_model.OPTIMAL else lower, status == cp_model.OPTIMAL, assign, "CP-SAT", wall)
    return WaitOptimum(K, rule_wait, max(0.0, lower), False, rule_assign, "Regel", wall)


def wait_of_assignment(inst, K, assign):
    """Kranwartezeit (nominal) einer festen Fahrzeugzuordnung, mit der Simulation ausgeführt: Gegenprobe für die Ergebnisse des Lösers."""
    return simulate(inst, K, make_rule_plan(list(assign))).wait_total
