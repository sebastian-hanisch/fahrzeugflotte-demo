"""Preset-Abstimmung per Sweep: traegt die Aussage jedes Presets im MITTEL ueber viele Auftragsfolgen und Rausch-Ziehungen, nicht nur bei den gewaehlten Seeds?

Aufruf (im Projektordner): ./venv/Scripts/python.exe tools/tune_presets.py <modus>
  population   Grundgesamtheit des Standard-Terminals (20 Auftragsfolgen x 10 Ziehungen): Kriterien aller Presets
  seeds        je Auftrags-Seed 0..79: Kriterien aller Presets an der Folge (100 Ziehungen), Rauschstabilitaet, Abstand zum Median
  pick         waehlt den Auftrags-Seed (alle fuenf Presets tragen, stabil, typisch) und je Rausch-Preset den Rausch-Seed; gibt die PRESETS-Zeilen aus

Grundsaetze (aus Stapelplanung und Kaiplatz-Demo): Seeds nicht nach dem schoensten Einzelfall waehlen, sondern nahe an der Grundgesamtheit und rauschstabil
(die Mittelwert-Aussage haelt bei mindestens 90 % der Bootstrap-Neuziehungen); Kriterien an der Grundgesamtheit messen. Alle Presets teilen sich EINE Auftragsfolge,
damit die Geschichte 'gleiches Terminal, Flotte und Rauschen aendern sich' bleibt."""
import math
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, ".")
import fz_constants as C
import fz_evaluation as E
import fz_stories as ST
from fz_dispatch import draw_noise, min_fleet
from fz_presets import scenario_instance

E_, B_, P_, R_ = C.STRAT_EARLIEST, C.STRAT_BESTFIT, C.STRAT_PLAN, C.STRAT_REDISPATCH
TERMINAL = (C._BASE["n_cranes"], C._BASE["jobs_per_crane"], C._BASE["cycle"], C._BASE["jitter"], C._BASE["blocks"])
SEEDS = range(80)
NAMES = list(C.PRESETS)
# Kennzahlen fuer 'typisch': (Abstand, Rauschen, Verfahren)
TYPICAL = [(-1, 0, E_), (-2, 0, E_), (0, 25, E_), (0, 25, B_), (0, 25, P_), (0, 25, R_)]


def _delta_of(m):
    return {k: m.wait(*k[:2], k[2]) for k in TYPICAL}


def typical_score(inst_vals, pop_vals):
    """Summe der Abstaende im Logarithmus (0,05 s Sockel): 0 = alle Kennzahlen genau beim MEDIAN der Auftragsfolgen (die Kante ist schief verteilt,
    der Mittelwert wird von wenigen Folgen getragen)."""
    return sum(abs(math.log(inst_vals[k] + 0.05) - math.log(pop_vals[k] + 0.05)) for k in TYPICAL)


def _seed_job(seed):
    inst = scenario_instance(*TERMINAL, seed)
    mf = min_fleet(inst)
    if mf[0] < 4:                                          # Minimum-3 muss darstellbar sein
        return seed, None
    rows = ST.instance_rows(inst, mf=mf)
    n = len(inst.jobs)
    m = ST.InstanceMeasure(n, rows)
    res = {name: (criteria_ok := all(ok for ok, _ in ST.criteria(name, m)), ST.bootstrap_stability(name, rows, n) if criteria_ok else 0.0) for name in NAMES}
    return seed, (res, _delta_of(m), mf[0])


def cmd_population():
    pop = ST.population_measure(TERMINAL)
    print(f"Grundgesamtheit {TERMINAL}: {C.SWEEP_INSTANCES} Folgen x {C.SWEEP_DRAWS} Ziehungen")
    for name in NAMES:
        print(f"\n### {name}")
        for ok, text in ST.criteria(name, pop):
            print(("  OK   " if ok else "  FAIL ") + text)
    vals = _delta_of(pop)
    print("\nKennzahlen:", {f"{d:+d}/{s}%/{k}": round(v, 2) for (d, s, k), v in vals.items()})


def _table():
    pop = ST.population_measure(TERMINAL)
    with ProcessPoolExecutor() as ex:
        rows = [r for r in ex.map(_seed_job, SEEDS) if r[1] is not None]
    return pop, rows


def _median_target(rows):
    return {k: statistics.median(v[k] for _, (_, v, _) in rows) for k in TYPICAL}


def cmd_seeds():
    pop, rows = _table()
    pv = _median_target(rows)
    print(f"{len(rows)} Auftragsfolgen (Minimum >= 4) von {len(SEEDS)}")
    for name in NAMES:
        good = [(s, res[name][1], typical_score(v, pv)) for s, (res, v, _) in rows if res[name][0] and res[name][1] >= 0.9]
        print(f"\n### {name}: Kriterien erfuellt und stabil bei {len(good)} von {len(rows)}")
        for s, st_, ts in sorted(good, key=lambda x: x[2])[:6]:
            print(f"  seed {s:3d} | stabil {st_:.0%} | Abstand zum Median {ts:.2f}")


def _shown_draw(inst, mf, name, nseed):
    p = C.PRESETS[name]
    n = len(inst.jobs)
    K = E.fleet_size(mf[0], p["fleet_delta"])
    return {o.key: o.wait_total for o in E.run_strategies(inst, K, draw_noise(n, p["noise_pct"] / 100, E.noise_for(nseed, 0)), mf) if o.available}


def cmd_pick():
    pop, rows = _table()
    pv = _median_target(rows)
    cands = [(typical_score(v, pv), s, res) for s, (res, v, _) in rows if all(res[n][0] and res[n][1] >= 0.9 for n in NAMES)]
    if not cands:
        print("KEINE Auftragsfolge traegt alle fuenf Presets stabil.")
        return
    cands.sort(key=lambda c: c[0])
    print("Kandidaten (Abstand, Seed):", [(round(a, 2), s) for a, s, _ in cands[:6]])
    score, seed, res = cands[0]
    inst = scenario_instance(*TERMINAL, seed)
    mf = min_fleet(inst)
    print(f"\nAuftrags-Seed {seed} (Abstand zum Median {score:.2f}, Minimum {mf[0]})")
    for name in NAMES:
        p = C.PRESETS[name]
        if p["noise_pct"] == 0:
            print(f"{name}: noise_seed={C.NOISE_SEED_DEFAULT} (ohne Rauschen ohne Wirkung), Ziehung: {_shown_draw(inst, mf, name, C.NOISE_SEED_DEFAULT)}")
            continue
        draws = {ns: _shown_draw(inst, mf, name, ns) for ns in range(200)}
        n = len(inst.jobs)
        ok = [ns for ns, c in draws.items() if ST.draw_holds(name, c, n)]
        gains = [c[P_] - c[E_] for c in draws.values()]
        med = statistics.median(gains)
        best = min(ok, key=lambda ns: abs(draws[ns][P_] - draws[ns][E_] - med)) if ok else None
        print(f"{name}: noise_seed={best} ({len(ok)} von 200 Ziehungen tragen die Geschichte; Ziehung {draws.get(best)})")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "population"
    {"population": cmd_population, "seeds": cmd_seeds, "pick": cmd_pick}.get(mode, lambda: sys.exit(__doc__))()
