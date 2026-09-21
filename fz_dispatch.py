"""Fahrzeug-Disposition: exakte Mindestflotte, die vier Verfahren, Simulation mit Kran-Kopplung und Rauschen.

Mindestflotte (exakt): Ein Fahrzeug bedient eine KETTE von Aufträgen j -> k, wenn es nach j rechtzeitig für k unter der Brücke steht. Die kleinste
Kettenzahl ist die minimale Wegeüberdeckung des azyklischen Graphen = n - maximales Matching (Dilworth/Fulkerson).

Simulation: Die Aufträge werden in nominaler Reihenfolge disponiert. Ein Verfahren sieht beim Entscheiden die TATSÄCHLICHEN Ende-Zeiten der Fahrzeuge und
schätzt die Ankunft am nächsten Kran mit der NOMINALEN Fahrzeit. Kran-Kopplung: Wartet eine Brücke, verschiebt sich ihre ganze Restfolge, denn
    Aufnahme p_j = max(Basis_j, Ankunft des Fahrzeugs),   Basis_j = max(nominal r_j, p_{Vorgänger derselben Brücke} + T_MIN),
    Kranwartezeit_j = p_j - Basis_j.
Rauschen: je Auftrag ein Faktor für die Leerfahrt zur Brücke und einer für die Beladenfahrt, VORAB gezogen (`draw_noise`) und damit für alle Verfahren
identisch (gemeinsame Zufallszahlen: die Vergleiche sind gepaart)."""

import math
import random
from dataclasses import dataclass

import fz_constants as C
from fz_scenario import can_follow

NEVER = -10**9      # ein Fahrzeug ohne bisherigen Auftrag steht "irgendwo", also ab -unendlich bereit (sonst künstliche Wartezeit)


# ---------------------------------------------------------------------------------------------------
# Exakte Mindestflotte
# ---------------------------------------------------------------------------------------------------
def max_matching(n, adj):
    """Maximales Matching im zweigeteilten Graphen (links: Vorgänger, rechts: Nachfolger). Iterativ (erweiternde Wege mit eigenem Stapel), damit auch lange
    Ketten keine Rekursionsgrenze treffen. Rückgabe: (Größe, match_right) mit match_right[v] = u, wenn Kante u -> v im Matching, sonst -1."""
    match_right = [-1] * n
    size = 0
    for root in range(n):
        seen = set()
        stack = [(root, iter(adj[root]))]
        path = []                                   # (u, v): u wird auf v abgebildet, wenn der Weg gelingt
        found = False
        while stack and not found:
            u, it = stack[-1]
            advanced = False
            for v in it:
                if v in seen:
                    continue
                seen.add(v)
                path.append((u, v))
                if match_right[v] < 0:
                    found = True
                else:
                    stack.append((match_right[v], iter(adj[match_right[v]])))
                advanced = True
                break
            if found:
                break
            if not advanced:
                stack.pop()
                if path:
                    path.pop()
        if found:
            for u, v in path:
                match_right[v] = u
            size += 1
    return size, match_right


def min_fleet(inst):
    """Exakte Mindestflotte für Kranwartezeit 0 (nominale Zeiten) und die zugehörigen Fahrzeugketten.
    Rückgabe: (Anzahl Fahrzeuge, assign) mit assign[j] = Fahrzeugnummer von Auftrag j (aufsteigend nach dem ersten Auftrag der Kette)."""
    n = len(inst.jobs)
    adj = [[k for k in range(j + 1, n) if can_follow(inst, j, k)] for j in range(n)]
    size, match_right = max_matching(n, adj)
    successor = {u: v for v, u in enumerate(match_right) if u >= 0}
    has_pred = {v for v, u in enumerate(match_right) if u >= 0}
    assign, vehicle = [None] * n, 0
    for j in range(n):
        if j not in has_pred:
            cur = j
            while cur is not None:
                assign[cur] = vehicle
                cur = successor.get(cur)
            vehicle += 1
    return n - size, assign


# ---------------------------------------------------------------------------------------------------
# Rauschen
# ---------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Noise:
    empty: tuple        # Faktor je Auftrag für die Leerfahrt zur Brücke (>= 1: nur Verspätung)
    loaded: tuple       # Faktor je Auftrag für die Beladenfahrt zum Block (>= 1)
    sigma: float = 0.0
    seed: int = 0


def draw_noise(n_jobs, sigma, seed):
    """Fahrzeit-Rauschen: jede Fahrt dauert Fahrzeit x (1 + sigma x U), U gleichverteilt in [0, 1). Eigener Strom (nur `seed`, `sigma` und Auftragszahl);
    ohne Rauschen (sigma = 0) werden keine Zufallszahlen verbraucht."""
    if sigma < 0:
        raise ValueError("sigma darf nicht negativ sein")
    if sigma == 0:
        return no_noise(n_jobs)
    rng = random.Random(seed)
    empty, loaded = [], []
    for _ in range(n_jobs):
        empty.append(1 + sigma * rng.random())
        loaded.append(1 + sigma * rng.random())
    return Noise(tuple(empty), tuple(loaded), sigma, seed)


def no_noise(n_jobs):
    return Noise((1.0,) * n_jobs, (1.0,) * n_jobs, 0.0, 0)


# ---------------------------------------------------------------------------------------------------
# Verfahren: rule(j, pred, free_at, K) -> Fahrzeugnummer
#   pred[v]    voraussichtliche Ankunft von Fahrzeug v unter der Brücke von Auftrag j (tatsächliches Ende + NOMINALE Fahrzeit; NEVER, wenn es noch nichts getan hat)
#   free_at[v] tatsächliches Ende des letzten Auftrags von Fahrzeug v
# ---------------------------------------------------------------------------------------------------
def rule_earliest(j, pred, free_at, K):
    """Nächstes freies Fahrzeug: das, das am frühesten unter der Brücke stehen kann."""
    return min(range(K), key=lambda v: (pred[v], v))


def make_rule_bestfit(inst):
    """Bestfit: unter den rechtzeitigen Fahrzeugen das späteste (kleinste Leerlaufzeit), sonst das frühest ankommende."""
    def rule(j, pred, free_at, K):
        r = inst.jobs[j].r
        timely = [v for v in range(K) if pred[v] <= r]
        if timely:
            return max(timely, key=lambda v: (pred[v], -v))
        return min(range(K), key=lambda v: (pred[v], v))
    return rule


def make_rule_plan(assign):
    """Starrer Plan: jedes Fahrzeug bedient genau seine Kette, egal was passiert."""
    return lambda j, pred, free_at, K: assign[j]


def make_rule_plan_redispatch(inst, assign):
    """Plan mit Umdisposition: dem Plan folgen, solange das zugeordnete Fahrzeug voraussichtlich rechtzeitig ist; sonst das voraussichtlich früheste."""
    def rule(j, pred, free_at, K):
        v = assign[j]
        if pred[v] <= inst.jobs[j].r:
            return v
        return min(range(K), key=lambda w: (pred[w], w))
    return rule


# ---------------------------------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Trip:
    job: int
    vehicle: int
    empty_start: int    # Beginn der Leerfahrt zur Brücke (= Ende des letzten Auftrags; bei der ersten Fahrt = pick)
    pick: int           # tatsächliche Aufnahmezeit
    done: int           # Ende: abgesetzt am Block
    base: int           # früheste Aufnahme ohne Fahrzeugwartezeit
    empty_time: int
    loaded_time: int

    @property
    def wait(self):
        """Kranwartezeit dieses Auftrags."""
        return self.pick - self.base


@dataclass(frozen=True)
class Run:
    trips: tuple            # je Auftrag (Index = Auftragsnummer)
    fleet: int

    @property
    def wait_total(self):
        return sum(t.wait for t in self.trips)

    @property
    def wait_per_job(self):
        return self.wait_total / len(self.trips)

    @property
    def late_jobs(self):
        """Anzahl Aufträge, bei denen die Brücke warten musste."""
        return sum(1 for t in self.trips if t.wait > 0)

    @property
    def utilization(self):
        """Anteil der Zeit (vom ersten Aufnehmen bis zum letzten Absetzen), in der ein Fahrzeug fährt oder absetzt, gemittelt über die Flotte."""
        busy = sum(t.empty_time + t.loaded_time for t in self.trips)
        span = max(t.done for t in self.trips) - min(t.pick for t in self.trips)
        return busy / (self.fleet * span) if span > 0 else 0.0


def simulate(inst, K, rule, noise=None):
    """Führt den Auftragsstrom mit K Fahrzeugen und dem Verfahren `rule` aus. Rückgabe: Run mit allen Fahrten."""
    if K < 1:
        raise ValueError("mindestens ein Fahrzeug")
    n = len(inst.jobs)
    noise = noise or no_noise(n)
    if len(noise.empty) != n:
        raise ValueError("Rauschen passt nicht zur Auftragszahl")
    p_prev = [NEVER] * inst.n_cranes
    free_at = [0] * K
    pos = [None] * K
    trips = []
    for j, job in enumerate(inst.jobs):
        q, b = job.crane, job.block
        pred = [NEVER if pos[v] is None else free_at[v] + inst.travel[q][pos[v]] for v in range(K)]
        v = rule(j, pred, free_at, K)
        if not 0 <= v < K:
            raise ValueError(f"Verfahren wählte Fahrzeug {v}, es gibt nur {K}")
        empty = 0 if pos[v] is None else math.ceil(inst.travel[q][pos[v]] * noise.empty[j])
        arrival = NEVER if pos[v] is None else free_at[v] + empty
        base = max(job.r, p_prev[q] + C.T_MIN)
        pick = max(base, arrival)
        loaded = math.ceil(inst.travel[q][b] * noise.loaded[j]) + C.SERVICE
        empty_start = pick if pos[v] is None else free_at[v]
        trips.append(Trip(j, v, empty_start, pick, pick + loaded, base, empty, loaded))
        p_prev[q] = pick
        free_at[v] = pick + loaded
        pos[v] = b
    return Run(tuple(trips), K)


def smallest_fleet(inst, rule_factory, kmax=None):
    """Kleinste Flotte, mit der ein Verfahren bei nominalen Zeiten keine Kranwartezeit hat. rule_factory(inst) -> rule."""
    for K in range(1, (kmax or len(inst.jobs)) + 1):
        if simulate(inst, K, rule_factory(inst)).wait_total == 0:
            return K
    return None
