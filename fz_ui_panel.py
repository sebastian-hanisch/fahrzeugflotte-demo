"""Wiederverwendbare Panels: je Verfahren ein Tab im Methodenvergleich und der selbstständige Exakt-Tab (Mindestflotte mit Beweis, Optimum bei Flottenmangel)."""

import streamlit as st

import fz_constants as C
from fz_dispatch import make_rule_plan, simulate
from fz_evaluation import run_extras
from fz_visualization import vehicle_gantt


def _num(x, digits=2):
    return f"{x:.{digits}f}"


def _delta_seconds(value, is_reference):
    return None if is_reference else f"{value:+.2f} s"


def _delta_color(value, is_reference):
    """Weniger Kranwartezeit ist besser ("inverse"); ein Unterschied, der auf 0,00 s rundet, bleibt grau statt rot."""
    return "off" if is_reference or round(value, 2) == 0 else "inverse"


def render_strategy_panel(prefix, outcome, outcomes, inst, t_range, focus=None):
    """Beschreibung, Kennzahlen (2 x 2) und Fahrzeug-Gantt eines Verfahrens. Deltas lesen sich immer als "dieses Verfahren minus Nächstes freies"
    (delta_color="inverse": weniger Kranwartezeit ist besser). `focus` = FocusStats dieses Verfahrens (Mittel über viele Rausch-Ziehungen) oder None.
    `prefix` macht die Widget-Schlüssel eindeutig."""
    ref = next(o for o in outcomes if o.key == C.BASELINE)
    st.markdown(C.STRATEGY_DESCRIPTIONS[outcome.key])
    if not outcome.available:
        st.info(outcome.reason)
        return
    is_ref = outcome.key == ref.key
    n = len(inst.jobs)
    extras = run_extras(outcome.run, inst)

    top, bottom = st.columns(2), st.columns(2)                      # 2 x 2: vier Spalten schneiden die Namen in schmalen Tabs ab
    m1, m2, m3, m4 = top + bottom
    m1.metric("Kranwartezeit je Auftrag", f"{_num(outcome.wait_per_job)} s", delta=_delta_seconds(outcome.wait_per_job - ref.wait_per_job, is_ref),
              delta_color=_delta_color(outcome.wait_per_job - ref.wait_per_job, is_ref), help="Mittel über alle Aufträge der gezeigten Ziehung: Sekunden, die die Brücke auf das Fahrzeug wartet.")
    m2.metric("Aufträge mit Wartezeit", f"{outcome.late_jobs} von {n}", help="Bei wie vielen Aufträgen die Brücke in der gezeigten Ziehung warten musste.")
    m3.metric("Flottenauslastung", f"{outcome.utilization * 100:.0f} %",
              help="Anteil der Zeit vom ersten Aufnehmen bis zum letzten Absetzen, in dem ein Fahrzeug fährt oder absetzt, gemittelt über die Flotte.")
    m4.metric("Leerfahrten", f"{extras.empty_share * 100:.0f} %", help="Anteil der Fahrzeit, der Leerfahrt zur Brücke ist.")
    st.caption(f"{extras.crane_changes} Fahrzeugwechsel zwischen Brücken, {extras.vehicles_used} von {outcome.run.fleet} Fahrzeugen im Einsatz."
               + ("" if focus is None or not focus.available else
                  f" Über {focus.n_draws} Rausch-Ziehungen: Ø {_num(focus.mean_per_job)} s je Auftrag, ganz ohne Kranwartezeit in {focus.zero_share * 100:.0f} % der Ziehungen."))
    st.plotly_chart(vehicle_gantt(inst, outcome.run, t_range), width="stretch", key=f"{prefix}_gantt_chart")


def render_exact_panel(prefix, inst, K, kmin, proof, proof_check, optimum, gaps, t_range):
    """Exakt-Tab. Ab der Mindestflotte: Beweis (Matching und Überdeckung) und die Fahrzeugketten als Gantt ohne Rauschen. Darunter: Optimum der Kranwartezeit mit
    Kennzeichnung "nicht bewiesen" und Abstand der Verfahren dazu. `proof_check` = (ok, Begründung) aus verify_min_fleet_proof; `optimum` darf None sein
    (noch nicht berechnet)."""
    n = len(inst.jobs)
    ok, reason = proof_check
    st.markdown(f"**Mindestflotte: {kmin} Fahrzeuge.** Größtes Matching {proof.matching_size} von {n} Aufträgen, also {n} − {proof.matching_size} = {kmin} Ketten. "
                f"Eine Knotenüberdeckung aus {proof.cover_size} Aufträgen belegt, dass kein Matching größer sein kann (Satz von König).")
    (st.success if ok else st.error)(f"Prüfung ohne Löser: {reason}")
    if optimum is None:
        return
    if K >= kmin:
        st.caption(f"Mit {K} ≥ {kmin} Fahrzeugen ist die Kranwartezeit ohne Störung 0: die Fahrzeugketten des Matchings zeigen es.")
        run = simulate(inst, K, make_rule_plan(list(optimum.assign)))
        st.plotly_chart(vehicle_gantt(inst, run, t_range), width="stretch", key=f"{prefix}_gantt_chart")
        return

    if optimum.source != "CP-SAT":
        st.warning("Der Löser hat im Zeitlimit nichts Besseres als die Regeln gefunden. Gezeigt ist die beste Regel, das Optimum ist **nicht bewiesen**: "
                   f"die Kranwartezeit liegt zwischen {optimum.wait_lower:.0f} und {optimum.wait_best} s.")
    elif not optimum.proven:
        st.warning(f"Das Zeitlimit lief ab: **nicht bewiesen** optimal, die Kranwartezeit liegt zwischen {optimum.wait_lower:.0f} und {optimum.wait_best} s.")
    else:
        st.caption(f"Bewiesen optimal (CP-SAT, {optimum.wall_ms:.0f} ms).")
    st.metric("Optimum der Kranwartezeit" + ("" if optimum.proven else " (beste bekannte)"), f"{optimum.wait_best} s",
              help="Kleinste Summe der Kranwartezeit ohne Störung mit dieser Flotte (Kenntnis aller Zeiten im Voraus).")
    st.markdown("**Abstand zum Optimum** (Kranwartezeit des Verfahrens minus Optimum, ohne Rauschen):")
    cols = st.columns(2) + st.columns(2)
    for col, g in zip(cols, gaps):
        col.metric(C.STRATEGY_LABELS[g.key], f"{g.excess:+d} s" if g.excess else "0 s")
    run = simulate(inst, K, make_rule_plan(list(optimum.assign)))
    st.plotly_chart(vehicle_gantt(inst, run, t_range), width="stretch", key=f"{prefix}_gantt_chart")
