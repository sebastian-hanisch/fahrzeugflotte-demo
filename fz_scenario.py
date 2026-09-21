"""Auftragsstrom und Fahrzeitmatrix.

Modell: Q Brücken am Kai, B Blöcke im Yard. Jede Brücke hat eine Folge von Aufträgen im Takt `cycle` (mit Streuung), jeder Auftrag bringt einen
Container vom Schiff zu einem zufälligen Block. Fahrzeiten sind ganzzahlige Sekunden aus Weg / Geschwindigkeit, AUFGERUNDET (nie gerundet: eine zu
kurze Fahrzeit macht Pläne zulässig, die es nicht sind)."""

import math
import random
from dataclasses import dataclass

import fz_constants as C


@dataclass(frozen=True)
class Job:
    r: int          # nominale Aufnahmezeit (s)
    crane: int
    block: int


@dataclass(frozen=True)
class Instance:
    jobs: tuple     # aufsteigend nach nominaler Aufnahmezeit (Index = Reihenfolge, in der die Verfahren entscheiden)
    travel: tuple   # travel[crane][block] = Fahrzeit in Sekunden (gleich hin und zurück)

    @property
    def n_cranes(self):
        return len(self.travel)

    @property
    def n_blocks(self):
        return len(self.travel[0])


def make_instance(n_cranes, jobs_per_crane, seed, cycle=C.CYCLE_DEFAULT, jitter=C.JITTER_DEFAULT, blocks=C.BLOCKS_DEFAULT):
    """Auftragsstrom mit eigenem Zufallsstrom (`seed` bestimmt Takt-Versatz, Streuung und Zielblöcke, nie das Rauschen)."""
    if n_cranes < 1 or jobs_per_crane < 1 or blocks < 1:
        raise ValueError("Brücken, Aufträge und Blöcke müssen mindestens 1 sein")
    rng = random.Random(seed)
    crane_x = [q * C.CRANE_SPACING for q in range(n_cranes)]
    yard = n_cranes * C.CRANE_SPACING + 30
    block_pos = [(C.BLOCK_MARGIN + b * yard / max(1, blocks - 1), C.YARD_OFFSET + C.YARD_STAGGER * (b % 2)) for b in range(blocks)]
    travel = tuple(tuple(math.ceil((abs(crane_x[q] - bx) + by) / C.SPEED) for (bx, by) in block_pos) for q in range(n_cranes))
    jobs = []
    for q in range(n_cranes):
        last, offset = -10**9, rng.randrange(cycle)
        for k in range(jobs_per_crane):
            r = max(offset + k * cycle + rng.randint(-jitter, jitter), last + C.T_MIN)
            last = r
            jobs.append(Job(r, q, rng.randrange(blocks)))
    jobs.sort(key=lambda j: (j.r, j.crane))
    return Instance(tuple(jobs), travel)


def custom_instance(jobs, travel):
    """Instanz aus Rohdaten: jobs = [(r, crane, block), ...], travel[crane][block]. Der Mindestabstand je Brücke wird NICHT stillschweigend hergestellt,
    sondern geprüft; die Aufträge werden nach nominaler Zeit sortiert."""
    travel = tuple(tuple(row) for row in travel)
    if not travel or not travel[0] or any(len(row) != len(travel[0]) for row in travel):
        raise ValueError("Fahrzeitmatrix muss rechteckig und nicht leer sein")
    if any(t < 1 or t != int(t) for row in travel for t in row):
        raise ValueError("Fahrzeiten müssen ganze Sekunden >= 1 sein")
    js = sorted((Job(int(r), int(q), int(b)) for r, q, b in jobs), key=lambda j: (j.r, j.crane))
    if not js:
        raise ValueError("mindestens ein Auftrag")
    last = {}
    for j in js:
        if not (0 <= j.crane < len(travel) and 0 <= j.block < len(travel[0])):
            raise ValueError("Brücke oder Block außerhalb der Fahrzeitmatrix")
        if j.crane in last and j.r < last[j.crane] + C.T_MIN:
            raise ValueError("zwei Aufnahmen derselben Brücke liegen näher als der Mindestabstand")
        last[j.crane] = j.r
    return Instance(tuple(js), travel)


def can_follow(inst, j, k):
    """Kann dasselbe Fahrzeug nach Auftrag j rechtzeitig unter der Brücke von Auftrag k stehen (nominale Zeiten)?"""
    a, b = inst.jobs[j], inst.jobs[k]
    return a.r + inst.travel[a.crane][a.block] + C.SERVICE + inst.travel[b.crane][a.block] <= b.r
