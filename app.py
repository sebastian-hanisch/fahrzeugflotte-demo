"""
Fahrzeugflotte am Kai – interaktive Fall-Demo
Sebastian Hanisch - Operations Research und Machine Learning

Welle 2 der Hafen-Linie (Kran <-> Block, unter der Kaiplatz- und der Kran-Demo): Wie viele Fahrzeuge braucht eine Containerbrücke, damit sie nie auf ein Fahrzeug wartet,
und was passiert, wenn die Fahrzeiten streuen? Die Mindestflotte ist exakt berechenbar; gezeigt wird, wie knapp diese Antwort ist und ob sie hält.

Lauffähig mit: streamlit run app.py
"""

import pandas as pd
import streamlit as st

import fz_constants as C
import fz_evaluation as E
import fz_visualization as V
from fz_dispatch import draw_noise, make_rule_bestfit, min_fleet, smallest_fleet
from fz_exact import prove_min_fleet, solve_min_wait, verify_min_fleet_proof
from fz_presets import (apply_preset, bounds, init_session_state_defaults, load_permalink_settings, randomize_noise_seed, randomize_seed,
                        scenario_instance, SETTING_SPECS, sync_query_params)
from fz_pdf_export import generate_fz_pdf
from fz_ui_panel import render_exact_panel, render_strategy_panel

st.set_page_config(page_title="Fahrzeugflotte am Kai – Sebastian Hanisch", layout="wide")

SCENARIO_KEYS = list(SETTING_SPECS)
E_, B_, P_, R_ = C.STRAT_EARLIEST, C.STRAT_BESTFIT, C.STRAT_PLAN, C.STRAT_REDISPATCH
LABEL, SHORT = C.STRATEGY_LABELS, {k: v.replace("<br>", " ") for k, v in C.STRATEGY_SHORT.items()}


@st.cache_data(show_spinner=False, max_entries=32)
def _compute_scenario(key):
    """Eine Ziehung (gezeigt) und die Kennzahlen über viele Rausch-Ziehungen der eigenen Auftragsfolge."""
    n_cranes, jobs_per_crane, cycle, jitter, blocks, seed, delta, noise_pct, noise_seed = key
    inst = scenario_instance(n_cranes, jobs_per_crane, cycle, jitter, blocks, seed)
    mf = min_fleet(inst)
    K = E.fleet_size(mf[0], delta)
    sigma = noise_pct / 100
    outcomes = E.run_strategies(inst, K, draw_noise(len(inst.jobs), sigma, E.noise_for(noise_seed, 0)), mf)
    focus = E.focus_stats(inst, K, sigma, noise_seed, min_fleet_result=mf)
    return inst, mf, K, outcomes, focus, smallest_fleet(inst, make_rule_bestfit)


@st.cache_data(show_spinner=False, max_entries=8)
def _compute_fleet_sweep(terminal, noise_pct):
    return E.fleet_sweep(*terminal, noise_pct)


@st.cache_data(show_spinner=False, max_entries=8)
def _compute_noise_sweep(terminal, delta):
    return E.noise_sweep(*terminal, delta)


@st.cache_data(show_spinner=False, max_entries=8)
def _compute_hit_rates(terminal):
    return E.minimum_hit_rates(*terminal)


@st.cache_data(show_spinner=False, max_entries=8)
def _compute_exact(key):
    """Optimum der Kranwartezeit bei Flottenmangel: läuft nur auf Klick (im eigenen Tab), ab der Mindestflotte ist es sofort da."""
    n_cranes, jobs_per_crane, cycle, jitter, blocks, seed, delta = key
    inst = scenario_instance(n_cranes, jobs_per_crane, cycle, jitter, blocks, seed)
    return solve_min_wait(inst, E.fleet_size(min_fleet(inst)[0], delta), C.EXACT_TIME_LIMIT_SECONDS)


st.title("🚜 Wie viele Fahrzeuge braucht eine Containerbrücke?")
st.markdown(
    """
Jede Containerbrücke braucht für jeden Container ein Fahrzeug zur richtigen Zeit. Zu wenige Fahrzeuge lassen die **Brücke warten** (Kranwartezeit), zu viele kosten Geld.
Die **Mindestflotte** lässt sich exakt und sofort berechnen. Diese Demo zeigt, wie **knapp** diese Antwort ist (ein Fahrzeug weniger kostet kaum etwas, zwei weniger
schon ein Vielfaches) und ob sie hält, wenn die Fahrzeiten schwanken: Dann hilft **Reserve** oder eine Regel, die sich anpasst. Wie das Modell funktioniert, steht im Expander
"Wie funktioniert diese Demo?" weiter unten, die formale Herleitung im Expander "📐 Mathematische Formulierung".
"""
)

st.caption("🎯 Schnellstart – ein Beispielszenario laden:")
PRESET_HELP = {
    "Knapp geplant": "Das exakte Minimum reicht: ohne Störung laufen alle Brücken ohne Wartezeit.",
    "Eins zu wenig": "Fast gratis: ein Fahrzeug weniger kostet kaum Kranwartezeit.",
    "Zwei zu wenig": "Die Kante: jetzt merkt man es.",
    "Rauschen 25 %": "Das Minimum ist nicht robust: Bei bis zu 25 % längeren Fahrzeiten wartet der starre Optimalplan am meisten.",
    "Mit Reserve": "Zwei Reservefahrzeuge machen die schlichte Regel wartefrei; der starre Plan profitiert nicht davon.",
}
# Je Zeile drei Schaltflächen: bei fünf in einer Zeile werden die Namen in schmalen Fenstern abgeschnitten.
preset_names = list(C.PRESETS.keys())
for row_start in range(0, len(preset_names), 3):
    row = st.columns(3)
    for col, name in zip(row, preset_names[row_start:row_start + 3]):
        with col:
            st.button(name, width="stretch", on_click=apply_preset, args=(name,), help=PRESET_HELP[name])

st.caption(
    "🔗 Die Adresszeile oben spiegelt Ihre aktuelle Konfiguration wider – einfach kopieren, "
    "um ein Szenario zu teilen."
)

load_permalink_settings()
init_session_state_defaults()

with st.sidebar:
    st.header("⚙️ Einstellungen")
    n_cranes = st.slider("Anzahl Brücken", *bounds("n_cranes_slider"), key="n_cranes_slider", help="Containerbrücken am Kai, je 40 m auseinander.")
    jobs_per_crane = st.slider("Aufträge je Brücke", *bounds("jobs_per_crane_slider"), key="jobs_per_crane_slider",
                               help="Container, die jede Brücke nacheinander abgibt (Q x m Aufträge insgesamt, höchstens 240).")
    cycle = st.slider("Takt je Brücke (s)", *bounds("cycle_slider"), step=C.CYCLE_STEP, key="cycle_slider",
                      help="Im Mittel alle so viele Sekunden will eine Brücke einen Container haben. Kleiner = mehr Verkehr = größere Mindestflotte.")
    jitter = st.slider("Streuung des Takts (s)", *bounds("jitter_slider"), key="jitter_slider",
                       help="Jeder Abruf weicht um bis zu so viele Sekunden vom Takt ab. Zwischen zwei Aufnahmen derselben Brücke liegen immer mindestens 40 s.")
    blocks = st.slider("Anzahl Blöcke", *bounds("blocks_slider"), key="blocks_slider",
                       help="Stapelblöcke, zu denen die Container gebracht werden. Die Fahrzeit hängt von Brücke und Block ab (6 m/s, aufgerundet auf ganze Sekunden).")
    seed = st.number_input("Seed der Aufträge", *bounds("seed_input"), key="seed_input", step=1,
                           help="Bestimmt Takt-Versatz, Streuung und Zielblöcke der Aufträge. Unabhängig vom Seed des Rauschens.")
    st.caption(f"= {n_cranes * jobs_per_crane} Aufträge")

    st.markdown("**Flotte und Störung**")
    fleet_delta = st.slider("Flotte gegenüber dem Minimum", *bounds("fleet_delta_slider"), format="%+d", key="fleet_delta_slider",
                            help="0 = genau die exakte Mindestflotte. -1 = ein Fahrzeug weniger, +2 = zwei Reservefahrzeuge. Die Flotte hat mindestens ein Fahrzeug. "
                            "Die Optimalpläne gibt es erst ab 0.")
    noise_pct = st.slider("Fahrzeit-Rauschen (%)", *bounds("noise_pct_slider"), step=C.NOISE_PCT_STEP, format="%d%%", key="noise_pct_slider",
                          help="Jede Fahrt dauert bis zu so viel länger als nominal (gleichverteilt, nie kürzer). 0 = alle Fahrzeuge fahren exakt nominal.")
    noise_seed = st.number_input("Seed des Rauschens", *bounds("noise_seed_input"), key="noise_seed_input", step=1,
                                 help="Bestimmt die gezeigte Ziehung der Fahrzeiten; die Kennzahlen mitteln über 100 Ziehungen ab diesem Seed. Unabhängig vom Seed der Aufträge.")
    st.button("🎲 Neue Aufträge", width="stretch", on_click=randomize_seed, help="Würfelt einen neuen Seed für die Aufträge.")
    st.button("🎲 Neues Rauschen", width="stretch", on_click=randomize_noise_seed, help="Würfelt einen neuen Seed für das Rauschen.")

sync_query_params({key: st.session_state[key] for key in SCENARIO_KEYS})

terminal = (int(n_cranes), int(jobs_per_crane), int(cycle), int(jitter), int(blocks))
fleet_delta, noise_pct = int(fleet_delta), int(noise_pct)
scenario_key = terminal + (int(seed), fleet_delta, noise_pct, int(noise_seed))

with st.spinner("Führe die Verfahren aus..."):
    inst, (kmin, assign), K, outcomes, focus, bestfit_min = _compute_scenario(scenario_key)
stats = {s.key: s for s in focus}
n_jobs = len(inst.jobs)
eff_delta = K - kmin
runs = [o.run for o in outcomes if o.available]
t_range = (0, V.time_axis_end(*runs))
ref = E.outcome_of(outcomes, E_)
delta_txt = "Minimum" + (f" {'+' if eff_delta > 0 else '−'} {abs(eff_delta)}" if eff_delta else "")

# ---------------------------------------------------------------------------------------------------
# Hauptansicht
# ---------------------------------------------------------------------------------------------------
st.markdown("## 🎯 Was kostet die Flottengröße die Brücken?")
st.caption("Kranwartezeit je Auftrag: wie viele Sekunden die Brücke im Mittel auf ihr Fahrzeug wartet. Mittel über 100 Rausch-Ziehungen der eigenen Auftragsfolge; "
           "alle Verfahren sehen dieselben Fahrzeiten.")

metric_rows = [st.columns(2), st.columns(2)]                  # 2 x 2: vier Spalten schneiden die Namen bei 800 px ab
for col, o in zip(metric_rows[0] + metric_rows[1], outcomes):
    s = stats[o.key]
    if not s.available:
        col.metric(o.label, "–", help=o.reason)
        continue
    diff = s.paired_diff[0]
    same = round(diff, 2) == 0
    col.metric(o.label, f"{s.mean_per_job:.2f} s",
               delta=None if o.key == E_ else ("0.00 s" if same else f"{diff:+.2f} s"), delta_color="off" if same else "inverse",
               help="Referenz für alle Vergleiche." if o.key == E_ else "Differenz: dieses Verfahren minus Nächstes freies (weniger Kranwartezeit ist besser).")

free_share = " · ".join(f"{SHORT[k]} {stats[k].zero_share * 100:.0f} %" for k in C.STRATEGY_KEYS if stats[k].available)
clip_note = " (mindestens ein Fahrzeug)" if K != kmin + fleet_delta else ""
st.info(
    f"ℹ️ Mindestflotte (exakt): **{kmin}** Fahrzeuge. Eingestellt: **{K}** (= {delta_txt}){clip_note}. "
    + ("Ohne Rauschen gibt es eine einzige, exakte Ziehung. " if noise_pct == 0 else
       f"Anteil der {focus[0].n_draws} Ziehungen ganz ohne Kranwartezeit: {free_share}. ")
    + ("Die Optimalpläne gibt es erst ab der Mindestflotte." if K < kmin else "")
)

st.markdown("#### 🔍 Blick aufs Terminal")
right_key = st.radio("Rechts vergleichen mit", list(C.RIGHT_VIEW_KEYS), format_func=LABEL.get, key="view_radio", horizontal=True,
                     help="Links steht immer Nächstes freies.")
right = E.outcome_of(outcomes, right_key)
left_col, right_col = st.columns(2)
for col, o, side in ((left_col, ref, "left"), (right_col, right, "right")):
    with col:
        st.markdown(f"**{o.label}**")
        if o.available:
            st.plotly_chart(V.vehicle_gantt(inst, o.run, t_range, legend=False), width="stretch", key=f"terminal_chart_{side}")
        else:
            st.info(o.reason)
crane_colors = ", ".join(f"{q + 1} {C.CRANE_COLOR_NAMES[q]}" for q in range(inst.n_cranes))
draw_txt = "ohne Rauschen" if noise_pct == 0 else f"eine Ziehung des Rauschens (Seed {int(noise_seed)})"
pdf_slot = st.container()          # der Download steht in der Hauptansicht, wird aber erst gefüllt, wenn Kante und Reservebedarf berechnet sind

st.caption(
    f"Gezeigt ist {draw_txt}. Eine Zeile je Fahrzeug: Farbige Balken = Beladenfahrt (Zahl = Auftrag, Farbe = Brücke: {crane_colors}), grau = Leerfahrt zur Brücke, hellgrau = das "
    "Fahrzeug steht schon an der Brücke, **rot = die Brücke wartet auf das Fahrzeug**. Beide Diagramme haben dieselbe Zeitachse. Was im Mittel gilt und wie stark ein "
    "Einzelfall davon abweicht, zeigt der Kernabschnitt darunter; Details zu allen Verfahren und das Optimum stehen im Methodenvergleich."
)

st.markdown("---")

# ---------------------------------------------------------------------------------------------------
# Kernabschnitt
# ---------------------------------------------------------------------------------------------------
st.subheader("📐 Wie viele Fahrzeuge braucht eine Brücke?")
st.markdown(
    """
Kernfrage dieser Demo: Reicht die exakte Mindestflotte, und was kostet es, **knapper** zu planen oder **Reserve** zu halten? Die Mindestflotte ist der Punkt, an dem
ohne Störung keine Brücke mehr wartet. Darunter steigt die Kranwartezeit erst kaum, dann steil (**die Kante**). Und schon wenige Prozent längere Fahrzeiten machen den
Optimalplan schlechter als die schlichte Regel. Hier live für Ihre Einstellungen gerechnet, **mit der Verteilung dazu**, denn Mittelwerte täuschen:
"""
)

with st.spinner("Rechne die Kurven über die Flottengröße und das Rauschen..."):
    sweep_f = _compute_fleet_sweep(terminal, noise_pct)
    sweep_n = _compute_noise_sweep(terminal, eff_delta)
    hit = _compute_hit_rates(terminal)
i_f = sweep_f.index_of(eff_delta)
have_sample = sweep_f.available(E_, i_f)
edge = E.edge_figures(sweep_f)

st.markdown("**Die Kante: Kranwartezeit von Nächstes freies gegen die Mindestflotte** (Mittel je Auftrag beim eingestellten Rauschen)")
e1, e2, e3 = st.columns(3)
for col, d, label in ((e1, 0, "Bei Minimum"), (e2, -1, "Minimum − 1"), (e3, -2, "Minimum − 2")):
    col.metric(label, "–" if edge[d] is None else f"{edge[d]:.2f} s",
               help="Kranwartezeit je Auftrag von Nächstes freies mit dieser Flotte, Mittel über die Stichprobe." if edge[d] is not None else
               "Bei diesem Terminal verträgt keine Auftragsfolge der Stichprobe so viele Fahrzeuge weniger (weniger als ein Fahrzeug).")
st.caption(
    f"Bestfit trifft die Mindestflotte in diesem Terminal {'**genau**' if bestfit_min == kmin else f'**nicht** (braucht {bestfit_min}, also {bestfit_min - kmin} mehr)'}, "
    f"in der Stichprobe von {hit.n_instances} Auftragsfolgen in {hit.bestfit_hits} ({hit.bestfit_hits / hit.n_instances * 100:.0f} %). Über alle untersuchten Größen liegt "
    "der Erfahrungswert bei über 99 %, nie mehr als ein Fahrzeug daneben; ein Beweis ist das nicht."
)

reserve = {k: E.reserve_need(sweep_f, k) for k in C.STRATEGY_KEYS}
st.markdown("**Reservebedarf**: kleinster Abstand zum Minimum, bei dem ein Verfahren in mindestens 95 % der Szenarien nie wartet")
rows = [st.columns(2), st.columns(2)]
for col, k in zip(rows[0] + rows[1], C.STRATEGY_KEYS):
    col.metric(LABEL[k], "–" if reserve[k] is None else f"{reserve[k]:+d}" if reserve[k] else "0",
               help="Nie im untersuchten Bereich (bis +4 Fahrzeuge) - Reserve allein hilft diesem Verfahren nicht." if reserve[k] is None else
               "Fahrzeuge über dem exakten Minimum.")

with pdf_slot:
    st.download_button(
        "📄 Ergebnis als PDF herunterladen",
        data=generate_fz_pdf(inst, kmin, K, outcomes, focus,
                             dict(n_cranes=terminal[0], jobs_per_crane=terminal[1], cycle=terminal[2], jitter=terminal[3], blocks=terminal[4], seed=int(seed),
                                  fleet_delta=fleet_delta, noise_pct=noise_pct, noise_seed=int(noise_seed)), edge=edge, reserve=reserve),
        file_name="fahrzeugflotte_ergebnis.pdf", mime="application/pdf", key="primary_pdf_download")

st.markdown("**Kranwartezeit je Auftrag über der Flottengröße** (logarithmische Achse, 0 s am unteren Rand)")
st.plotly_chart(V.fleet_curve_figure(sweep_f, eff_delta, reserve[E_]), width="stretch", key="fleet_curve_chart")
st.markdown("**Kranwartezeit je Auftrag über dem Rauschen** (bei der eingestellten Flotte)")
st.plotly_chart(V.noise_curve_figure(sweep_n, noise_pct), width="stretch", key="noise_curve_chart")
n_seq = sweep_f.n_scenarios(sweep_f.index_of(0)) // (C.SWEEP_DRAWS if noise_pct else 1)
st.caption(
    f"Basis: {n_seq} Auftragsfolgen mit den Seeds 0-{n_seq - 1} (nicht Ihr Seed) x {C.SWEEP_DRAWS} Rausch-Ziehungen je Punkt, Ihre Terminal- und Rauscheinstellungen; "
    "Band = ± 1 Standardfehler. Die Optimalpläne beginnen erst bei der Mindestflotte."
)


def _show_verdict(label, key):
    if not have_sample:
        return
    if not sweep_f.available(key, i_f):
        st.caption(f"{label}: unter der Mindestflotte nicht definiert.")
        return
    v = E.verdict(sweep_f, key, i_f)
    d = E.distribution(sweep_f, key, i_f)
    if v.kind == "better":
        amount = (f"**{abs(v.pct):.0f} % weniger** Kranwartezeit ({-v.diff:.2f} s je Auftrag" if v.pct is not None
                  else f"**{-v.diff:.2f} s weniger** Kranwartezeit je Auftrag (")
        st.success(f"✅ **{label}** ist hier robuster als Nächstes freies: im Mittel {amount}{', ' if v.pct is not None else ''}Standardfehler {v.se:.2f}). "
                   f"In **{d.worse * 100:.0f} %** der Szenarien ist es umgekehrt.")
    elif v.kind == "worse":
        amount = (f"**{v.pct:.0f} % mehr** Kranwartezeit ({v.diff:.2f} s je Auftrag" if v.pct is not None
                  else f"**{v.diff:.2f} s mehr** Kranwartezeit je Auftrag, wo Nächstes freies nie wartet (")
        st.warning(f"⚠️ **{label}** kostet hier Kranwartezeit gegenüber Nächstes freies: im Mittel {amount}{', ' if v.pct is not None else ''}Standardfehler {v.se:.2f}). "
                   f"In **{d.better * 100:.0f} %** der Szenarien ist es besser.")
    else:
        st.info(f"ℹ️ Kein klarer Unterschied zwischen **{label}** und Nächstes freies: die Differenz ({v.diff:+.2f} s je Auftrag) liegt innerhalb des Rauschens "
                f"(Standardfehler {v.se:.2f}). Besser in {d.better * 100:.0f} %, schlechter in {d.worse * 100:.0f} % der Szenarien.")


if have_sample:
    st.markdown("**Urteil gegen Nächstes freies** (gepaarte Differenz, klar ab mehr als zwei Standardfehlern)")
    _show_verdict("Der starre Optimalplan", P_)
    _show_verdict("Der Optimalplan mit Umdisposition", R_)
    _show_verdict("Bestfit", B_)
    avail = [k for k in (B_, P_, R_) if sweep_f.available(k, i_f)]
    dists = [E.distribution(sweep_f, k, i_f) for k in avail]
    dcol1, dcol2 = st.columns(2)
    with dcol1:
        st.markdown("**Wie sich die Gewinne verteilen** (Anteil der Szenarien)")
        st.plotly_chart(V.distribution_figure(dists), width="stretch", key="distribution_chart")
    with dcol2:
        st.markdown("**Typisches Szenario gegen Mittelwert**")
        st.plotly_chart(V.gain_figure(dists), width="stretch", key="gain_chart")
    st.caption(
        f"Basis: {sweep_f.n_scenarios(i_f)} Szenarien beim eingestellten Abstand ({eff_delta:+d}) und Rauschen. Gleich heißt: Unterschied höchstens eine halbe Sekunde "
        "je Szenario. Liegt der Median weit unter dem Mittelwert, tragen wenige Szenarien den Gewinn; Gewinn positiv = weniger Kranwartezeit als Nächstes freies."
    )
else:
    st.info("ℹ️ Für so kleine Terminals und diesen Abstand gibt es keine Stichprobe: Keine Auftragsfolge verträgt so viele Fahrzeuge weniger. Den Abstand erhöhen.")

st.markdown("---")

# ---------------------------------------------------------------------------------------------------
# Methodenvergleich
# ---------------------------------------------------------------------------------------------------
with st.expander("🔧 Wie wir das erreichen – vollständiger Methodenvergleich"):
    tabs = st.tabs([o.label for o in outcomes] + ["🧮 Exakt", "📊 Vergleich"])
    for tab, outcome in zip(tabs[:len(outcomes)], outcomes):
        with tab:
            render_strategy_panel(f"strategy_{outcome.key}", outcome, outcomes, inst, t_range, stats[outcome.key])

    tab_exact, tab_compare = tabs[len(outcomes)], tabs[len(outcomes) + 1]
    exact_key = terminal + (int(seed), eff_delta)
    optimum = None
    with tab_exact:
        st.caption(
            "Die Mindestflotte kommt aus einem maximalen Matching und ist mit einer Knotenüberdeckung bewiesen (Satz von König), ohne jeden Löser. Bei Flottenmangel "
            "(unter dem Minimum) rechnet CP-SAT das Optimum der Kranwartezeit ohne Rauschen. "
            f"Auf {C.EXACT_TIME_LIMIT_SECONDS:g} s begrenzt; läuft das Zeitlimit ab, steht das dabei (nie ein unbewiesener Wert als Optimum). "
            "Beweisbar ist Minimum − 1 bis etwa 40 Aufträge, Minimum − 2 nur bis etwa 12."
        )
        proof = prove_min_fleet(inst)
        proof_check = verify_min_fleet_proof(inst, proof)
        if K >= kmin:
            optimum = _compute_exact(exact_key)
        else:
            if st.button("🧮 Optimum berechnen", key="fz_exact_btn"):
                st.session_state["fz_exact_scenario_key"] = exact_key
            if st.session_state.get("fz_exact_scenario_key") == exact_key:
                with st.spinner(f"Exakte Suche (bis zu {C.EXACT_TIME_LIMIT_SECONDS:g} s)..."):
                    optimum = _compute_exact(exact_key)
            elif "fz_exact_scenario_key" in st.session_state:
                st.info("ℹ️ Das zuletzt berechnete Optimum bezog sich auf ein anderes Szenario - Einstellungen geändert? Erneut auf '🧮 Optimum berechnen' klicken.")
            else:
                st.info("Noch nichts berechnet – auf den Button oben klicken.")
        gaps = E.gaps_to_optimum(inst, K, optimum, (kmin, assign)) if optimum is not None else ()
        render_exact_panel("exact", inst, K, kmin, proof, proof_check, optimum, gaps, None)

    with tab_compare:
        table = []
        for o in outcomes:
            s = stats[o.key]
            if s.available:
                extras = E.run_extras(o.run, inst)
                table.append({
                    "Verfahren": o.label, "Kranwartezeit je Auftrag (Ø, s)": round(s.mean_per_job, 2), "± Standardfehler": round(s.se_per_job, 2),
                    "Ziehungen ohne Kranwartezeit (%)": round(s.zero_share * 100), "Flottenauslastung (Ø, %)": round(s.mean_utilization * 100),
                    "Differenz zu Nächstes freies (s je Auftrag)": round(s.paired_diff[0], 2),
                    "gezeigte Ziehung: Aufträge mit Wartezeit": o.late_jobs, "Brückenwechsel der Fahrzeuge": extras.crane_changes,
                })
            else:
                table.append({"Verfahren": o.label})
        st.dataframe(pd.DataFrame(table), width="stretch", hide_index=True)
        st.plotly_chart(V.comparison_figure(focus), width="stretch", key="comparison_chart")
        if optimum is None or K >= kmin:
            st.caption("Bei Flottenmangel erscheint hier zusätzlich der Abstand zum Optimum, sobald es im Tab '🧮 Exakt' berechnet wurde.")
        else:
            st.caption("Abstand zum Optimum der Kranwartezeit (ohne Rauschen, nominale Fahrzeiten): " + ", ".join(
                f"{LABEL[g.key]} {g.excess:+d} s" for g in gaps) + ("" if optimum.proven else " (Optimum nicht bewiesen)"))

with st.expander("Wie funktioniert diese Demo?"):
    st.markdown(
        """
**Aufträge, Fahrzeuge, Kran-Kopplung.** Jede Containerbrücke ruft in ihrem Takt Container ab; ein Auftrag heißt: Zu einer Fahrplan-Zeit muss ein Fahrzeug unter der Brücke stehen,
den Container aufnehmen und zu einem Block fahren. Danach ist das Fahrzeug wieder frei und fährt leer zur nächsten Brücke. Eine Brücke nimmt höchstens alle 40 s einen Container auf.
Kommt ein Fahrzeug zu spät, **wartet die Brücke** (das ist die Kranwartezeit, die Zielgröße), und weil sie danach nicht schneller arbeiten kann, **verschiebt sich ihre ganze
Restfolge**: ein Fehler pflanzt sich fort. Die Fahrzeiten werden auf ganze Sekunden aufgerundet, nie gerundet.

**Die Mindestflotte** ist die kleinste Zahl von Fahrzeugen, mit der ohne Störung jeder Auftrag rechtzeitig bedient wird. Sie folgt aus einem Matching (siehe Formulierung), ist
also exakt und in Millisekunden berechnet, auch für 240 Aufträge; ein Beweis mit Knotenüberdeckung liegt dabei (Tab "Exakt"). Die Regler stellen die Flotte als **Abstand zum Minimum**
ein: 0 = exakt das Minimum, -1 = ein Fahrzeug weniger, +2 = zwei als Reserve.

**Vier Verfahren**, alle mit denselben Fahrzeiten:

- **Nächstes freies**: jeder Auftrag geht an das Fahrzeug, das am frühesten unter der Brücke stehen kann. Keine Planung. Für jede Flottengröße definiert und die Referenz aller Vergleiche.
- **Bestfit**: unter den Fahrzeugen, die rechtzeitig kommen, das mit der spätesten Ankunft (das knappste); kommt keines rechtzeitig, das früheste. Findet die Mindestflotte
  in über 99 % der untersuchten Fälle, nie mehr als ein Fahrzeug daneben (gemessen, nicht bewiesen).
- **Optimalplan starr**: die Fahrzeugketten des Matchings, nominal ohne jede Wartezeit. Im Ablauf wird die Zuordnung starr befolgt, auch wenn ein Fahrzeug sich verspätet; die
  Verspätung läuft die Kette entlang. Gibt es erst ab der Mindestflotte, denn darunter existiert kein solcher Plan.
- **Plan + Umdisposition**: wie der Optimalplan, aber ist das geplante Fahrzeug voraussichtlich zu spät, geht der Auftrag an das früheste freie. Trennt die Wirkung von Reserve
  und von Reaktion.

**Das Bild lesen.** Eine Zeile je Fahrzeug, die Zeit läuft nach rechts. Ein farbiger Balken ist eine Beladenfahrt (Farbe = Brücke, Zahl = Auftrag), grau die Leerfahrt zur nächsten
Brücke, hellgrau das Warten des Fahrzeugs an der Brücke. Ein **roter Strich mit ✕** über der Zeile heißt: Hier hat die Brücke auf das Fahrzeug gewartet, von der frühesten möglichen
Aufnahme bis zur tatsächlichen.

**Warum ein Fahrzeug weniger fast gratis ist und zwei weniger nicht (die Kante).** Mit einem Fahrzeug weniger als dem Minimum fehlt es nur an wenigen Stellen, an denen die Abrufe
besonders dicht liegen; die Brücke wartet kurz, und die Verschiebung ist klein. Mit jedem weiteren fehlenden Fahrzeug häufen sich diese Stellen, und die Kopplung verstärkt jede
Wartezeit auf die ganze Restfolge. Die Kurve im Kernabschnitt zeigt das für Ihr Terminal. Für die Flottengröße heißt das: Knapp zu planen kostet zunächst wenig, aber der Abstand
zum Steilhang ist dünn.

**Warum der Optimalplan bei Streuung verliert.** Er kennt nur nominale Zeiten und wird im Betrieb nicht angepasst; ist er auf das Minimum zugeschnitten, hat jede Kette null Puffer, und
jede Verspätung reicht bis ans Kettenende. „Nächstes freies“ dagegen passt sich bei jedem Auftrag an, was tatsächlich passiert ist. Der Optimalplan mit Umdisposition zeigt, dass die
**Reaktion** den größten Teil des Unterschieds erklärt und nicht eine zusätzliche Reserve. Zwei Reservefahrzeuge machen „Nächstes freies“ in den meisten Szenarien wartefrei; den starren Plan
kaufen sie nicht frei, weil er die zusätzlichen Fahrzeuge gar nicht benutzt.

**Warum ein Einzelfall vom Mittelwert abweicht.** Die Gewinne sind schief verteilt: In vielen Szenarien ändert sich wenig, in wenigen sehr viel. Deshalb zeigt der Kernabschnitt die
Verteilung (besser, gleich, schlechter) und den Median, und nennt einen Unterschied nur dann klar, wenn er mehr als zwei Standardfehler beträgt. Kurven und Kernabschnitt rechnen für Ihr Terminal
über 10 bis 20 Auftragsfolgen (Seeds 0, 1, 2, ...) und je 10 Ziehungen, nicht mit Ihrem aktuellen Seed.

**Grenzen dieses Modells** (bewusst so gewählt, damit die Aussage ehrlich bleibt):

- Das Rauschen ist **gleichverteilt und nur verspätend** (jede Fahrt bis zu x % länger, nie kürzer). Die Rangfolge der Verfahren blieb in der Messreihe bei beidseitigem und log-normalem
  Rauschen gleich, es sind aber Annahmen, keine Messungen an einem echten Terminal.
- Es gibt **keine Fahrspur-, Kreuzungs- und Staukonflikte**, keine Blockkapazität und kein Laden am Kran; Fahrzeuge starten "irgendwo" und sind ab Beginn bereit.
- Der **starre Plan ist bewusst einfach** (er wird nicht angepasst); der Plan mit Umdisposition ist die klügere Ausführung.
- Fahrzeiten, Takt und Blockverteilung sind **Annahmen ohne Kalibrierung** an echten Daten.
- Alle Zahlen sind **Größenordnungen aus einer Simulation, keine Messung an Echtdaten.**
        """
    )

with st.expander("📐 Mathematische Formulierung"):
    st.markdown(
        r"""
**Mindestflotte für einen Auftragsstrom** (minimale Wegeüberdeckung, polynomiell lösbar).

Aufträge $j = 1, \dots, n$ mit Fahrplan-Aufnahmezeit $r_j$, Brücke $q_j$ und Block $b_j$; $t(q, b)$ die (aufgerundete) Fahrzeit zwischen Brücke $q$ und Block $b$, $s$ die Absetzzeit.
Ein Fahrzeug kann nach $j$ noch rechtzeitig für $k$ da sein, wenn
$$
r_j + t(q_j, b_j) + s + t(q_k, b_j) \le r_k .
$$
Das ist eine Kante $j \to k$ eines azyklischen Graphen; jede Fahrzeugkette ist ein Weg darin. Die kleinste Zahl von Wegen, die alle Knoten überdecken, ist
$$
K_{\min} = n - \nu,
$$
mit $\nu$ der Größe eines maximalen Matchings im zweigeteilten Graphen (Vorgänger gegen Nachfolger; Satz von Dilworth/Fulkerson). Eine Knotenüberdeckung derselben Größe
(Satz von König) belegt, dass kein größeres Matching existiert.

**Kran-Kopplung.** Aufnahmezeit $p_j$ und Kranwartezeit $w_j$ mit dem Mindestabstand $\tau = 40$ s zwischen zwei Aufnahmen derselben Brücke ($\mathrm{pre}(j)$ = Vorgänger derselben Brücke):
$$
\beta_j = \max\big(r_j,\; p_{\mathrm{pre}(j)} + \tau\big), \qquad p_j = \max\big(\beta_j,\; \alpha_j\big), \qquad w_j = p_j - \beta_j ,
$$
wobei $\alpha_j$ die Ankunft des gewählten Fahrzeugs unter der Brücke ist. Zielgröße: $\sum_j w_j$ (Kranwartezeit). Eine Verspätung erhöht $p_j$ und über $\beta$ alle späteren Aufnahmen derselben Brücke.

**Regeln.** Sei $\alpha_j(v)$ die geschätzte Ankunft von Fahrzeug $v$: Nächstes freies wählt $\arg\min_v \alpha_j(v)$; Bestfit wählt unter den rechtzeitigen ($\alpha_j(v) \le r_j$)
$\arg\max_v \alpha_j(v)$, sonst $\arg\min_v \alpha_j(v)$; der Optimalplan ordnet $j$ dem Fahrzeug seiner Matching-Kette zu; mit Umdisposition nur, solange dieses Fahrzeug nicht
voraussichtlich zu spät kommt, sonst wie Nächstes freies.

**Rauschen.** Jede Leerfahrt zur Brücke und jede Beladenfahrt dauert $\lceil t \cdot (1 + \sigma U) \rceil$ mit $U \sim \mathcal{U}[0, 1)$ und dem eingestellten $\sigma$. Die Faktoren werden je Auftrag
vorab gezogen und sind für alle Verfahren identisch (gemeinsame Zufallszahlen), die Vergleiche also gepaart.

**Optimum bei Flottenmangel** ($K < K_{\min}$, nominale Zeiten): CP-SAT mit einem Kreis je Fahrzeug (`AddCircuit`), der Kopplung als Maximum-Gleichung
$\beta_j = \max(r_j, p_{\mathrm{pre}(j)} + \tau)$, Zielfunktion $\min \sum_j (p_j - \beta_j)$, Symmetriebruch zwischen gleichen Fahrzeugen und der besten Regel als Startlösung.
Ohne Beweis im Zeitlimit steht ein Intervall aus unterer Schranke und bester bekannter Lösung, nie ein unbewiesener Wert als Optimum.

**Vergleich über Szenarien.** Für Verfahren $A$ gegen die Referenz $B$ auf denselben Szenarien $k = 1, \dots, S$ (gleiche Fahrzeiten) ist $\Delta_k = c_B^{(k)} - c_A^{(k)}$ der Gewinn;
berichtet werden Mittel, Median und der Anteil der Szenarien mit $\Delta_k > 0{,}5$ s (besser) bzw. $< -0{,}5$ s (schlechter). Ein Unterschied gilt als klar, wenn
$|\bar\Delta| > 2\,\mathrm{SE}(\Delta)$ mit dem Standardfehler der gepaarten Differenz. Der **Reservebedarf** ist der kleinste Abstand zum Minimum, bei dem in mindestens 95 % der Szenarien $\sum_j w_j = 0$ gilt.

Implementiert in `fz_dispatch.py` (Matching, Regeln, Simulation), `fz_exact.py` (Beweis und Optimum), `fz_evaluation.py` (Vergleiche).
        """
    )

st.markdown("---")

st.caption(
    "Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – "
    "Operations Research und Machine Learning. Interesse an einer maßgeschneiderten Lösung für "
    "Ihr Unternehmen? [Kontakt aufnehmen](https://sebastianhanisch.net/kontakt.html)"
)
