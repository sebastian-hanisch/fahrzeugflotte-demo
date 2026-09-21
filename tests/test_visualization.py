"""Tests der Diagramme und Panels: Daten im Bild stimmen mit den Ergebnisobjekten überein, Portfolio-Konventionen (fixedrange, kein Plotly-Titel, graue Marker), Panels
laufen über AppTest ohne doppelte Schlüssel."""

import math

import pytest
from streamlit.testing.v1 import AppTest

import fz_constants as C
import fz_evaluation as E
import fz_visualization as V
from fz_dispatch import draw_noise, make_rule_bestfit, min_fleet, rule_earliest, simulate
from fz_scenario import make_instance

E_, B_, P_, R_ = C.STRAT_EARLIEST, C.STRAT_BESTFIT, C.STRAT_PLAN, C.STRAT_REDISPATCH


@pytest.fixture(scope="module")
def inst():
    return make_instance(3, 10, 4)


@pytest.fixture(scope="module")
def mf(inst):
    return min_fleet(inst)


@pytest.fixture(scope="module")
def waiting_run(inst, mf):
    """Eine Ziehung mit Kranwartezeit (ein Fahrzeug unter dem Minimum, Rauschen)."""
    run = simulate(inst, mf[0] - 1, rule_earliest, draw_noise(len(inst.jobs), 0.3, 5))
    assert run.wait_total > 0
    return run


def traces(fig, name):
    return [t for t in fig.data if t.name == name]


def assert_conventions(fig):
    assert fig.layout.title.text in (None, "")
    for ax in (a for a in fig.layout if a.startswith(("xaxis", "yaxis"))):
        assert fig.layout[ax].fixedrange is True, ax


# ---------------------------------------------------------------------------------------------------
# Gantt
# ---------------------------------------------------------------------------------------------------
def test_gantt_conventions_and_axes(inst, waiting_run):
    fig = V.vehicle_gantt(inst, waiting_run)
    assert_conventions(fig)
    K = waiting_run.fleet
    assert list(fig.layout.yaxis.tickvals) == list(range(1, K + 1))
    assert tuple(fig.layout.yaxis.range) == (K + 0.6, 0.4)
    assert tuple(fig.layout.xaxis.range) == (0, V.time_axis_end(waiting_run))
    assert fig.layout.xaxis.range[1] >= max(t.done for t in waiting_run.trips)
    assert V.vehicle_gantt(inst, waiting_run, (100, 300)).layout.xaxis.range == (100, 300)


def test_gantt_legend_switch_and_crane_colour_names(inst, waiting_run):
    assert V.vehicle_gantt(inst, waiting_run).layout.showlegend is True
    quiet = V.vehicle_gantt(inst, waiting_run, legend=False)
    assert quiet.layout.showlegend is False and quiet.layout.margin.t < V.vehicle_gantt(inst, waiting_run).layout.margin.t
    assert len(C.CRANE_COLOR_NAMES) == len(C.CRANE_COLORS) == max(C.N_CRANES_RANGE)     # jede mögliche Brücke hat Farbe und Namen für die Bildunterschrift


def test_gantt_neutral_colours_work_on_light_and_dark_backgrounds(inst, waiting_run):
    """Leerfahrt und Stehzeit sind halbtransparentes Mittelgrau (nichts fast Weißes, das im dunklen Schema blendet); Brückenfarben weder fast schwarz noch fast weiß."""
    fig = V.vehicle_gantt(inst, waiting_run)
    for name in ("Leerfahrt zur Brücke", "Fahrzeug wartet an der Brücke"):
        color = traces(fig, name)[0].marker.color
        assert color.startswith("rgba(128,136,149,") and float(color.rstrip(")").split(",")[-1]) < 1
    for hexcolor in C.CRANE_COLORS:
        r, g, b = (int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))
        assert 40 < (r + g + b) / 3 < 215, hexcolor


def test_gantt_time_axis_end_rounds_up_to_100_and_takes_max():
    class T:
        def __init__(self, done):
            self.done = done

    class R:
        def __init__(self, *d):
            self.trips = [T(x) for x in d]

    assert V.time_axis_end(R(1, 250)) == 300
    assert V.time_axis_end(R(300)) == 300
    assert V.time_axis_end(R(301)) == 400
    assert V.time_axis_end(R(10), R(950)) == 1000
    assert V.time_axis_end(R()) == 100


def test_gantt_bars_match_trips(inst, waiting_run):
    fig = V.vehicle_gantt(inst, waiting_run)
    seen = set()
    for q in range(inst.n_cranes):
        for tr in traces(fig, f"Brücke {q + 1}"):
            for base, dur, y in zip(tr.base, tr.x, tr.y):
                match = [t for t in waiting_run.trips if t.pick == base and t.loaded_time == dur and t.vehicle + 1 == y and inst.jobs[t.job].crane == q]
                assert match
                seen.add(match[0].job)
    assert seen == set(range(len(inst.jobs)))                                         # jeder Auftrag genau als Beladenfahrt
    empty = traces(fig, "Leerfahrt zur Brücke")[0]
    assert sum(empty.x) == sum(t.empty_time for t in waiting_run.trips)
    assert all(x > 0 for x in empty.x)


def test_gantt_crane_wait_markers_match_waits(inst, waiting_run):
    fig = V.vehicle_gantt(inst, waiting_run)
    waits = [t for t in waiting_run.trips if t.wait > 0]
    bar = traces(fig, "Brücke wartet (Kranwartezeit)")[0]
    assert len(bar.x) == len(waits) and sum(bar.x) == waiting_run.wait_total
    assert sorted(bar.base) == sorted(t.base for t in waits)
    marks = [t for t in fig.data if getattr(t, "mode", None) == "markers" and t.marker.symbol == "x"][0]
    assert sorted(marks.x) == sorted(t.pick for t in waits)
    for x, y in zip(bar.base, bar.y):                                                 # Marker liegt in der Zeile des Fahrzeugs (knapp darüber)
        assert abs(y - round(y)) == pytest.approx(0.44) or abs(y - round(y)) == pytest.approx(0.56)


def test_gantt_without_waits_has_no_red_traces(inst, mf):
    run = simulate(inst, mf[0] + 1, rule_earliest)
    assert run.wait_total == 0
    fig = V.vehicle_gantt(inst, run)
    assert not traces(fig, "Brücke wartet (Kranwartezeit)")
    assert not [t for t in fig.data if getattr(t, "mode", None) == "markers"]


def test_gantt_idle_bars_only_where_vehicle_stands(inst, waiting_run):
    fig = V.vehicle_gantt(inst, waiting_run)
    idle = traces(fig, "Fahrzeug wartet an der Brücke")
    n_idle = sum(1 for t in waiting_run.trips if t.empty_start != t.pick and t.pick > t.empty_start + t.empty_time)
    got = len(idle[0].x) if idle else 0
    assert got == n_idle
    if idle:
        assert all(x > 0 for x in idle[0].x)
        spans = sorted((t.empty_start + t.empty_time, t.pick - t.empty_start - t.empty_time) for t in waiting_run.trips
                       if t.empty_start != t.pick and t.pick > t.empty_start + t.empty_time)
        assert sorted(zip(idle[0].base, idle[0].x)) == spans          # das Fahrzeug steht ab der Ankunft an der Brücke, nicht ab dem Ende der letzten Fahrt


def test_gantt_hover_texts_are_never_drawn_into_bars(inst, waiting_run):
    """`text` dient nur dem Hover; ohne textposition="none" würde Plotly ihn als Schrift in die Balken malen."""
    fig = V.vehicle_gantt(inst, waiting_run)
    for name in ("Leerfahrt zur Brücke", "Fahrzeug wartet an der Brücke"):
        assert all(tr.textposition == "none" for tr in traces(fig, name))
    big = make_instance(4, 20, 1)
    fig2 = V.vehicle_gantt(big, simulate(big, 12, rule_earliest))
    assert all(tr.textposition == "none" for tr in fig2.data if tr.name and tr.name.startswith("Brücke ") and "wartet" not in tr.name)
    assert all(tr.textposition == "inside" for tr in fig.data if tr.name and tr.name.startswith("Brücke ") and "wartet" not in tr.name)


def test_gantt_labels_only_for_small_instances(inst):
    small = simulate(inst, 6, rule_earliest)
    fig = V.vehicle_gantt(inst, small)
    loaded = [t for t in fig.data if t.name and t.name.startswith("Brücke ") and "wartet" not in t.name][0]
    assert loaded.texttemplate == "%{customdata}"
    edge = make_instance(4, 15, 1)                                                    # genau GANTT_LABEL_MAX_JOBS = 60: noch beschriftet
    assert len(edge.jobs) == C.GANTT_LABEL_MAX_JOBS
    loaded_edge = [t for t in V.vehicle_gantt(edge, simulate(edge, 12, rule_earliest)).data if t.name == "Brücke 1"][0]
    assert loaded_edge.texttemplate == "%{customdata}"
    big = make_instance(4, 20, 1)                                                     # 80 Aufträge > GANTT_LABEL_MAX_JOBS
    fig2 = V.vehicle_gantt(big, simulate(big, 12, rule_earliest))
    loaded2 = [t for t in fig2.data if t.name and t.name.startswith("Brücke ") and "wartet" not in t.name][0]
    assert loaded2.texttemplate is None


# ---------------------------------------------------------------------------------------------------
# Kurven
# ---------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def fleet_curve():
    return E.fleet_sweep(3, 10, 75, 10, 6, 25, n_instances=5, n_draws=3)


def test_fleet_curve_log_axis_floor_and_hover_true_values(fleet_curve):
    fig = V.fleet_curve_figure(fleet_curve, 0)
    assert_conventions(fig)
    assert fig.layout.yaxis.type == "log"
    assert tuple(fig.layout.yaxis.ticktext)[0] == "0"
    line = traces(fig, C.STRATEGY_LABELS[E_])[0]
    assert min(line.y) >= C.LOG_FLOOR
    for y, cd, i in zip(line.y, line.customdata, range(len(line.y))):
        assert y == pytest.approx(max(cd[0], C.LOG_FLOOR))                            # Hover zeigt den wahren Wert, die Linie den gekappten
    # kein Plan unter dem Minimum: die Spur beginnt erst bei Abstand 0
    plan = traces(fig, C.STRATEGY_LABELS[P_])[0]
    assert min(plan.x) == 0 and max(plan.x) == 4
    assert min(traces(fig, C.STRATEGY_LABELS[B_])[0].x) == min(x for x in fleet_curve.axis if fleet_curve.available(B_, fleet_curve.axis.index(x)))


def test_fleet_curve_marker_lines_gray_and_reserve(fleet_curve):
    fig = V.fleet_curve_figure(fleet_curve, 1, reserve=2)
    lines = [s for s in fig.layout.shapes if s.type == "line"]
    assert len(lines) == 2
    xs = sorted(s.x0 for s in lines)
    assert xs == [1, 2]
    gray = [s for s in lines if s.x0 == 1][0]
    assert gray.line.color == C.MARKER_LINE_COLOR
    assert len(V.fleet_curve_figure(fleet_curve, 1).layout.shapes) == 1


def test_fleet_curve_x_range_hugs_the_axis(fleet_curve):
    fig = V.fleet_curve_figure(fleet_curve, 0)
    assert tuple(fig.layout.xaxis.range) == (min(fleet_curve.axis) - 0.5, max(fleet_curve.axis) + 0.5)


def test_fleet_curve_axis_top_above_largest_value(fleet_curve):
    top = max(fleet_curve.mean(k, i) for k in C.STRATEGY_KEYS for i in range(len(fleet_curve.axis)) if fleet_curve.available(k, i))
    fig = V.fleet_curve_figure(fleet_curve, 0)
    assert fig.layout.yaxis.range[1] > math.log10(top)
    assert fig.layout.yaxis.range[0] < math.log10(C.LOG_FLOOR)


def test_noise_curve_linear_and_marker():
    sw = E.noise_sweep(3, 10, 75, 10, 6, 0, sigma_pcts=(0, 25, 50), n_instances=4, n_draws=3)
    fig = V.noise_curve_figure(sw, 25)
    assert_conventions(fig)
    assert fig.layout.yaxis.type in (None, "linear")
    line = traces(fig, C.STRATEGY_LABELS[E_])[0]
    assert list(line.x) == [0, 25, 50]
    assert list(line.y) == pytest.approx([sw.mean(E_, i) for i in range(3)])
    assert [s.x0 for s in fig.layout.shapes if s.type == "line"] == [25]


# ---------------------------------------------------------------------------------------------------
# Verteilung, Vergleich
# ---------------------------------------------------------------------------------------------------
def test_distribution_and_gain_figures(fleet_curve):
    i = fleet_curve.axis.index(0)
    dists = [E.distribution(fleet_curve, k, i) for k in (B_, P_, R_)]
    fig = V.distribution_figure(dists)
    assert_conventions(fig)
    assert len(fig.data) == 3
    for j, d in enumerate(dists):
        assert [t.x[j] for t in fig.data] == pytest.approx([d.better * 100, d.equal * 100, d.worse * 100])
        assert sum(t.x[j] for t in fig.data) == pytest.approx(100)
    g = V.gain_figure(dists)
    assert list(g.data[0].y) == pytest.approx([d.median_gain for d in dists])
    assert list(g.data[1].y) == pytest.approx([d.mean_gain for d in dists])


def test_comparison_figure_marks_unavailable(inst, mf):
    kmin, _ = mf
    stats = E.focus_stats(inst, kmin - 1, 0.2, 3, n_draws=4, min_fleet_result=mf)
    fig = V.comparison_figure(stats)
    assert_conventions(fig)
    assert len(fig.data[0].x) == 2 and len(fig.data[1].x) == 2
    assert any("erst ab der Mindestflotte" in (a.text or "") for a in fig.layout.annotations)
    assert any("–" in c for c in fig.layout.xaxis.categoryarray)
    full_stats = E.focus_stats(inst, kmin, 0.2, 3, n_draws=4, min_fleet_result=mf)
    full = V.comparison_figure(full_stats)
    assert list(full.data[0].error_y.array) == pytest.approx([s.se_per_job for s in full_stats])
    assert list(full.data[1].y) == pytest.approx([s.zero_share * 100 for s in full_stats])
    assert len(full.data[0].x) == 4
    assert not any("erst ab der Mindestflotte" in (a.text or "") for a in full.layout.annotations)
    assert list(full.data[0].y) == pytest.approx([s.mean_per_job for s in E.focus_stats(inst, kmin, 0.2, 3, n_draws=4, min_fleet_result=mf)])


# ---------------------------------------------------------------------------------------------------
# Panels über AppTest
# ---------------------------------------------------------------------------------------------------
def _strategy_app(delta, sigma, exact_case):
    import fz_constants as C
    import fz_evaluation as E
    import fz_ui_panel as P
    import fz_visualization as V
    import streamlit as st
    from fz_dispatch import draw_noise
    from fz_exact import prove_min_fleet, solve_min_wait, verify_min_fleet_proof
    from fz_scenario import make_instance

    inst = make_instance(3, 10, 4)
    proof = prove_min_fleet(inst)
    kmin = proof.fleet
    K = E.fleet_size(kmin, delta)
    outcomes = E.run_strategies(inst, K, draw_noise(len(inst.jobs), sigma, 7))
    t_range = (0, V.time_axis_end(*[o.run for o in outcomes if o.available]))
    focus = {s.key: s for s in E.focus_stats(inst, K, sigma, 3, n_draws=5)}
    if exact_case:
        opt = solve_min_wait(inst, K, time_limit_seconds=5)
        if exact_case == "rule":
            import dataclasses
            opt = dataclasses.replace(opt, source="Regel", proven=False, wait_lower=1.0)
        elif exact_case == "unproven":
            import dataclasses
            opt = dataclasses.replace(opt, source="CP-SAT", proven=False, wait_lower=1.0)
        gaps = E.gaps_to_optimum(inst, K, opt)
        P.render_exact_panel("ex", inst, K, kmin, proof, verify_min_fleet_proof(inst, proof), opt, gaps, t_range)
    else:
        for o in outcomes:
            with st.container():
                P.render_strategy_panel(f"s_{o.key}", o, outcomes, inst, t_range, focus[o.key])


def run_app(delta, sigma, exact_case=False):
    at = AppTest.from_function(_strategy_app, args=(delta, sigma, exact_case), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def test_strategy_panels_at_minimum():
    at = run_app(0, 0.25)
    labels = [m.label for m in at.metric]
    assert labels.count("Kranwartezeit je Auftrag") == 4
    assert labels.count("Aufträge mit Wartezeit") == 4 and labels.count("Flottenauslastung") == 4 and labels.count("Leerfahrten") == 4
    ref = at.metric[0]
    assert ref.delta in (None, "") or ref.delta == ""                                 # die Referenz hat kein Delta
    deltas = [m.delta for m in at.metric if m.label == "Kranwartezeit je Auftrag"]
    assert all(d and ("+" in d or "-" in d or "−" in d) for d in deltas[1:])
    assert not at.info


def test_strategy_panels_below_minimum_explain_missing_plan():
    at = run_app(-1, 0.2)
    labels = [m.label for m in at.metric]
    assert labels.count("Kranwartezeit je Auftrag") == 2                              # nur die beiden ohne Plan
    assert len(at.info) == 2 and all("Mindestflotte" in i.value for i in at.info)


def test_exact_panel_at_and_below_minimum():
    above = run_app(0, 0.0, exact_case=True)
    assert any("Mindestflotte" in m.value for m in above.markdown)
    assert any("Prüfung ohne Löser" in s.value for s in above.success)
    below = run_app(-1, 0.0, exact_case=True)
    assert any(m.label.startswith("Optimum der Kranwartezeit") for m in below.metric)
    assert len([m for m in below.metric if m.label in (C.STRATEGY_LABELS[E_], C.STRATEGY_LABELS[B_])]) == 2
    assert not below.exception


def test_panels_use_distinct_chart_keys():
    at = run_app(0, 0.25)
    assert len(at.get("plotly_chart")) == 4


def test_panel_metric_values_delta_sign_and_color():
    from streamlit.proto.Metric_pb2 import Metric as MetricProto

    at = run_app(0, 0.25)
    inst = make_instance(3, 10, 4)
    K = E.fleet_size(min_fleet(inst)[0], 0)
    outs = E.run_strategies(inst, K, draw_noise(len(inst.jobs), 0.25, 7))
    per_job = [m for m in at.metric if m.label == "Kranwartezeit je Auftrag"]
    util = [m for m in at.metric if m.label == "Flottenauslastung"]
    empty = [m for m in at.metric if m.label == "Leerfahrten"]
    for m, u, e, o in zip(per_job, util, empty, outs):
        assert m.value == f"{o.wait_per_job:.2f} s"
        assert u.value == f"{o.utilization * 100:.0f} %"
        assert e.value == f"{E.run_extras(o.run, inst).empty_share * 100:.0f} %"
    ref = outs[0].wait_per_job
    for m, o in zip(per_job[1:], outs[1:]):
        diff = o.wait_per_job - ref
        assert m.delta == f"{diff:+.2f} s"
        expected = MetricProto.GRAY if round(diff, 2) == 0 else (MetricProto.RED if diff > 0 else MetricProto.GREEN)     # weniger ist besser: "inverse"
        assert m.proto.color == expected
    assert any(round(o.wait_per_job - ref, 2) > 0 for o in outs[1:])


def test_delta_color_rules():
    import fz_ui_panel as P

    assert P._delta_color(0.5, False) == "inverse" and P._delta_color(-0.5, False) == "inverse"
    assert P._delta_color(0.004, False) == "off" and P._delta_color(-0.004, False) == "off" and P._delta_color(0.0, False) == "off"
    assert P._delta_color(0.006, False) == "inverse"
    assert P._delta_color(5.0, True) == "off"


def test_exact_panel_caption_at_exact_minimum_and_gap_values():
    at = run_app(0, 0.0, exact_case=True)
    assert any("ohne Störung 0" in c.value for c in at.caption)
    below = run_app(-1, 0.0, exact_case=True)
    assert not any("ohne Störung 0" in c.value for c in below.caption)
    inst = make_instance(3, 10, 4)
    kmin, _ = min_fleet(inst)
    from fz_exact import solve_min_wait
    opt = solve_min_wait(inst, kmin - 1, time_limit_seconds=5)
    gaps = {g.key: g for g in E.gaps_to_optimum(inst, kmin - 1, opt)}
    for key, g in gaps.items():
        m = [x for x in below.metric if x.label == C.STRATEGY_LABELS[key]][0]
        assert m.value == (f"{g.excess:+d} s" if g.excess else "0 s")
    assert any(m.value == f"{opt.wait_best} s" for m in below.metric)


def test_exact_panel_warns_when_not_proven():
    rule = run_app(-1, 0.0, exact_case="rule")
    assert any("nicht bewiesen" in w.value and "Löser hat im Zeitlimit nichts Besseres" in w.value for w in rule.warning)
    unproven = run_app(-1, 0.0, exact_case="unproven")
    assert any("Zeitlimit lief ab" in w.value for w in unproven.warning)
    assert any("beste bekannte" in m.label for m in unproven.metric)
    proven = run_app(-1, 0.0, exact_case=True)
    assert not proven.warning
