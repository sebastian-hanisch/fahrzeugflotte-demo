"""Jedes Preset erzählt eine Geschichte (Abnahmekriterien aus dem Plan, Abschnitt 7, in fz_stories.py). Hier wird geprüft, dass sie trägt:

1. in der EINEN Ziehung, die das Preset zeigt (sonst zeigt das Preset das Gegenteil seines Hilfetexts), und dass diese Ziehung typisch ist,
2. im MITTEL der gewählten Auftragsfolge über 100 andere Rausch-Ziehungen, rauschstabil (Bootstrap),
3. im MITTEL über viele Auftragsfolgen (sonst ist das Preset ein Einzelfall, ausgesucht nach dem schönsten Seed),
4. dass die gewählte Folge typisch ist: bei jeder Kennzahl zwischen dem 10. und 90. Perzentil der Folgen (die Kante ist schief verteilt, also gilt der Median als Maß).

Die Abstimmung selbst steht in tools/tune_presets.py."""

import statistics

import pytest

import fz_constants as C
import fz_evaluation as E
import fz_stories as ST
from fz_dispatch import draw_noise, min_fleet
from fz_presets import scenario_instance

E_, B_, P_, R_ = C.STRAT_EARLIEST, C.STRAT_BESTFIT, C.STRAT_PLAN, C.STRAT_REDISPATCH
NAMES = list(C.PRESETS)
TERMINAL = (C._BASE["n_cranes"], C._BASE["jobs_per_crane"], C._BASE["cycle"], C._BASE["jitter"], C._BASE["blocks"])
TYPICAL = [(-1, 0, E_), (-2, 0, E_), (0, 25, E_), (0, 25, B_), (0, 25, P_), (0, 25, R_)]
SAMPLE_SEEDS = range(40)
_cache = {}


def _instance(name):
    p = C.PRESETS[name]
    return scenario_instance(p["n_cranes"], p["jobs_per_crane"], p["cycle"], p["jitter"], p["blocks"], p["seed"])


def _run_draw(name, noise_seed):
    """Kosten je Verfahren in der Rausch-Ziehung 0 des Seeds (wie app.py: Fahrzeuganzahl des Presets, gezeigte Ziehung)."""
    p = C.PRESETS[name]
    inst = _instance(name)
    mf = min_fleet(inst)
    K = E.fleet_size(mf[0], p["fleet_delta"])
    outs = E.run_strategies(inst, K, draw_noise(len(inst.jobs), p["noise_pct"] / 100, E.noise_for(noise_seed, 0)), mf)
    return {o.key: o.wait_total for o in outs if o.available}


def _shown(name):
    return _run_draw(name, C.PRESETS[name]["noise_seed"]), len(_instance(name).jobs)


def _rows(name):
    if ("rows", name) not in _cache:
        _cache[("rows", name)] = ST.instance_rows(_instance(name))
    return _cache[("rows", name)]


def _population():
    if "pop" not in _cache:
        _cache["pop"] = ST.population_measure(TERMINAL)
    return _cache["pop"]


def _sample_values():
    """Kennzahlen (TYPICAL) über viele Auftragsfolgen: {Kennzahl: sortierte Liste}."""
    if "sample" not in _cache:
        vals = {k: [] for k in TYPICAL}
        for s in SAMPLE_SEEDS:
            inst = scenario_instance(*TERMINAL, s)
            rows = ST.instance_rows(inst, points=tuple({(d, sg) for d, sg, _ in TYPICAL}), n_draws=30)
            m = ST.InstanceMeasure(len(inst.jobs), rows)
            for d, sg, k in TYPICAL:
                vals[(d, sg, k)].append(m.wait(d, sg, k))
        _cache["sample"] = {k: sorted(v) for k, v in vals.items()}
    return _cache["sample"]


# ---------------- 1. in der gezeigten Ziehung ----------------
@pytest.mark.parametrize("name", NAMES)
def test_the_story_holds_in_the_single_draw_the_preset_shows(name):
    cost, n = _shown(name)
    assert ST.draw_holds(name, cost, n), (name, cost)


@pytest.mark.parametrize("name", ["Rauschen 25 %", "Mit Reserve"])
def test_the_shown_noise_draw_is_typical_not_extreme(name):
    """Der Abstand zwischen starrem Plan und Nächstes freies liegt in der gezeigten Ziehung zwischen dem 10. und 90. Perzentil der Ziehungen der Folge."""
    gains = []
    for ns in range(100):
        c = _run_draw(name, ns)
        gains.append(c[P_] - c[E_])
    gains.sort()
    cost, _ = _shown(name)
    assert gains[9] <= cost[P_] - cost[E_] <= gains[-10], (name, cost, gains[9], gains[-10])


# ---------------- 2. im Mittel der gewählten Auftragsfolge ----------------
@pytest.mark.parametrize("name", NAMES)
def test_the_story_holds_on_the_mean_of_the_preset_instance(name):
    m = ST.InstanceMeasure(len(_instance(name).jobs), _rows(name))
    for ok, text in ST.criteria(name, m):
        assert ok, (name, text)


@pytest.mark.parametrize("name", NAMES)
def test_the_mean_statement_is_noise_stable_under_bootstrap(name):
    assert ST.bootstrap_stability(name, _rows(name), len(_instance(name).jobs)) >= 0.9


# ---------------- 3. im Mittel über die Grundgesamtheit ----------------
@pytest.mark.parametrize("name", NAMES)
def test_the_story_holds_on_average_over_many_instances(name):
    for ok, text in ST.criteria(name, _population()):
        assert ok, (name, text)


def test_the_edge_grows_steeply_and_is_right_skewed_across_instances():
    """Gemessen: Min-1 kostet im Mittel unter 1 s, Min-3 über 30 s; bei Min-2 liegt der Mittelwert weit über dem Median (wenige Folgen tragen ihn)."""
    pop = _population()
    assert pop.wait(-3, 0, E_) >= 50 * pop.wait(-1, 0, E_)
    vals = _sample_values()[(-2, 0, E_)]
    assert statistics.fmean(vals) > 2 * statistics.median(vals)


def test_noise_preset_shows_the_plan_worse_than_the_simple_rule_in_almost_every_scenario():
    sweep = _population().sweeps[25]
    d = E.distribution(sweep, P_, sweep.axis.index(0))
    assert d.worse >= 0.9 and d.better <= 0.05


def test_reserve_does_not_help_the_static_plan():
    pop = _population()
    assert pop.wait(2, 25, P_) == pytest.approx(pop.wait(0, 25, P_), rel=0.05)         # das starre Verfahren benutzt die zusätzlichen Fahrzeuge nicht
    assert pop.wait(2, 25, E_) < 0.1 * pop.wait(0, 25, E_) + 1e-9


# ---------------- 4. typisch ----------------
@pytest.mark.parametrize("d,sg,key", TYPICAL)
def test_the_preset_instance_is_typical_for_every_metric(d, sg, key):
    """Die gewählte Folge liegt bei jeder Kennzahl zwischen dem 10. und 90. Perzentil der Folgen (Median als Maß, denn die Kante ist schief)."""
    vals = _sample_values()[(d, sg, key)]
    name = next(n for n, pts in ST.POINTS.items() if (d, sg) in pts)
    mine = ST.InstanceMeasure(len(_instance(name).jobs), _rows(name)).wait(d, sg, key)
    lo, hi = vals[len(vals) // 10], vals[-len(vals) // 10 - 1]
    assert lo <= mine <= hi, (d, sg, key, mine, lo, hi)


# ---------------- Aufbau ----------------
def test_all_presets_share_one_terminal_and_one_instance_seed_only_fleet_and_noise_change():
    base = C.PRESETS[NAMES[0]]
    for p in C.PRESETS.values():
        for field in ("n_cranes", "jobs_per_crane", "cycle", "jitter", "blocks", "seed"):
            assert p[field] == base[field]
    assert base["seed"] == C.SEED_DEFAULT


def test_no_two_presets_are_the_same_scenario():
    keys = [tuple(sorted(p.items())) for p in C.PRESETS.values()]
    assert len(set(keys)) == len(keys)


@pytest.mark.parametrize("name", [n for n in NAMES if C.PRESETS[n]["noise_pct"] == 0])
def test_presets_without_noise_do_not_depend_on_the_noise_seed(name):
    assert _run_draw(name, 0) == _run_draw(name, 9999)


def test_criteria_and_draw_rules_reject_wrong_stories():
    """Die Kriterien unterscheiden: ein Bild, in dem die Verfahren vertauscht sind, erfüllt 'Rauschen 25 %' nicht; die Grenzen der Einzelziehungen sitzen genau."""

    class Fake:
        def __init__(self, table, zero=None):
            self.table, self.zero_t = table, zero or {}

        def wait(self, d, s, k):
            return self.table[(d, s, k)]

        def zero(self, d, s, k):
            return self.zero_t.get((d, s, k), 0.0)

    good = Fake({(0, 25, E_): 0.1, (0, 25, B_): 0.7, (0, 25, P_): 1.4, (0, 25, R_): 0.3})
    bad = Fake({(0, 25, E_): 1.4, (0, 25, B_): 0.7, (0, 25, P_): 0.1, (0, 25, R_): 0.3})
    assert all(ok for ok, _ in ST.criteria("Rauschen 25 %", good))
    assert not any(ok for ok, _ in ST.criteria("Rauschen 25 %", bad))
    assert ST.draw_holds("Rauschen 25 %", {E_: 2, B_: 30, P_: 100, R_: 10}, 120)
    assert not ST.draw_holds("Rauschen 25 %", {E_: 50, B_: 30, P_: 100, R_: 10}, 120)
    assert ST.draw_holds("Mit Reserve", {E_: 0, B_: 1, P_: 1, R_: 1}, 120) and not ST.draw_holds("Mit Reserve", {E_: 1, B_: 1, P_: 1, R_: 1}, 120)
    assert ST.draw_holds("Zwei zu wenig", {E_: 240, B_: 240}, 120) and not ST.draw_holds("Zwei zu wenig", {E_: 239, B_: 240}, 120)
    assert ST.draw_holds("Eins zu wenig", {E_: 120, B_: 0}, 120) and not ST.draw_holds("Eins zu wenig", {E_: 121, B_: 0}, 120)
    assert ST.draw_holds("Knapp geplant", {E_: 60, B_: 0, P_: 0, R_: 0}, 120) and not ST.draw_holds("Knapp geplant", {E_: 61, B_: 0, P_: 0, R_: 0}, 120)
    with pytest.raises(KeyError):
        ST.criteria("Unbekannt", good)
    with pytest.raises(KeyError):
        ST.draw_holds("Unbekannt", {}, 1)
