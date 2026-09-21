"""AppTest: Skelett und Footer, jedes Preset, Permalink, alle Regler an Min und Max, Kennzahlen im 2 x 2-Raster mit kurzen Namen, Urteil in allen drei Zuständen,
Exakt-Tab (Beweis, Optimum, veraltete Berechnung), eindeutige Diagramm-Schlüssel."""

import pathlib

import pytest
from streamlit.testing.v1 import AppTest

import fz_constants as C
import fz_evaluation as E
from fz_evaluation import Verdict
from fz_presets import SETTING_SPECS

E_, B_, P_, R_ = C.STRAT_EARLIEST, C.STRAT_BESTFIT, C.STRAT_PLAN, C.STRAT_REDISPATCH

APP = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")
FOOTER = ("Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – "
          "Operations Research und Machine Learning. Interesse an einer maßgeschneiderten Lösung für "
          "Ihr Unternehmen? [Kontakt aufnehmen](https://sebastianhanisch.net/kontakt.html)")


def fresh(**query):
    at = AppTest.from_file(APP, default_timeout=180)
    for k, v in query.items():
        at.query_params[k] = v
    at.run()
    assert not at.exception, at.exception
    return at


def set_and_run(at, **values):
    for key, value in values.items():
        (at.number_input if key.endswith("_input") else at.slider)(key=key).set_value(value)
    at.run()
    assert not at.exception, at.exception
    return at


def metric_map(at):
    return [(m.label, m.value) for m in at.metric]


# ---------------------------------------------------------------------------------------------------
# Skelett
# ---------------------------------------------------------------------------------------------------
def test_skeleton_and_footer():
    at = fresh()
    assert [h.value for h in at.sidebar.header] == ["⚙️ Einstellungen"]                # genau EIN Header
    assert len(at.title) == 1 and "Containerbrücke" in at.title[0].value
    assert any(v.value.startswith("## 🎯") for v in at.markdown)
    assert [s.value for s in at.subheader] == ["📐 Wie viele Fahrzeuge braucht eine Brücke?"]
    assert [e.label for e in at.expander] == ["🔧 Wie wir das erreichen – vollständiger Methodenvergleich", "Wie funktioniert diese Demo?", "📐 Mathematische Formulierung"]
    assert at.caption[-1].value == FOOTER or any(c.value == FOOTER for c in at.caption)
    presets = [b.label for b in at.button if b.label in C.PRESETS]
    assert presets == list(C.PRESETS) and len(presets) == 5
    assert all(len(name) <= 16 for name in presets)                                   # lange Namen werden in schmalen Fenstern abgeschnitten


def test_metrics_2x2_with_short_labels_and_all_charts_have_keys():
    at = fresh()
    main = [m for m in at.metric][:4]
    assert [m.label for m in main] == [C.STRATEGY_LABELS[k] for k in C.STRATEGY_KEYS]
    assert all(len(m.label) <= 24 for m in main)
    assert len(at.get("plotly_chart")) >= 12                                           # Terminal x 2, Kurven, Verteilung, Vergleich, je Verfahren ein Gantt


def test_default_reference_metric_has_no_delta_and_others_do():
    at = fresh()
    main = at.metric[:4]
    assert not main[0].delta
    assert all(m.delta for m in main[1:])


# ---------------------------------------------------------------------------------------------------
# Presets, Permalink
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", list(C.PRESETS))
def test_every_preset_loads_within_widget_bounds(name):
    at = fresh()
    next(b for b in at.button if b.label == name).click().run()
    assert not at.exception
    p = C.PRESETS[name]
    assert at.slider(key="fleet_delta_slider").value == p["fleet_delta"]
    assert at.slider(key="noise_pct_slider").value == p["noise_pct"]
    assert at.slider(key="n_cranes_slider").value == p["n_cranes"]
    assert at.number_input(key="seed_input").value == p["seed"]
    for state_key, spec in SETTING_SPECS.items():
        if spec.lo is not None:
            value = at.session_state[state_key]
            assert spec.lo <= value <= spec.hi
            if spec.step and spec.step > 1:
                assert (value - spec.lo) % spec.step == 0


def test_permalink_is_clamped_snapped_and_ignores_garbage():
    at = fresh(fd="99", np="27", vw="junk", cy="77", nc="abc")
    assert at.slider(key="fleet_delta_slider").value == C.FLEET_DELTA_RANGE[1]
    assert at.slider(key="noise_pct_slider").value in (25, 30)                          # auf die Schrittweite 5 eingerastet
    assert at.radio(key="view_radio").value == C.VIEW_DEFAULT
    assert at.slider(key="cycle_slider").value == 75
    assert at.slider(key="n_cranes_slider").value == C.N_CRANES_DEFAULT


def test_permalink_roundtrip_reflects_settings():
    at = fresh(fd="-2", np="25", nc="3", jc="12", seed="11", vw="bestfit")
    assert at.slider(key="fleet_delta_slider").value == -2
    assert at.radio(key="view_radio").value == "bestfit"
    assert at.query_params["fd"] == ["-2"] or at.query_params["fd"] == "-2"


def test_seed_buttons_change_only_their_own_seed():
    at = fresh()
    seed0, nseed0 = at.number_input(key="seed_input").value, at.number_input(key="noise_seed_input").value
    next(b for b in at.button if b.label == "🎲 Neues Rauschen").click().run()
    assert at.number_input(key="seed_input").value == seed0                            # Aufträge bleiben
    nseed1 = at.number_input(key="noise_seed_input").value
    next(b for b in at.button if b.label == "🎲 Neue Aufträge").click().run()
    assert at.number_input(key="noise_seed_input").value == nseed1                     # Rauschen bleibt
    assert not at.exception
    assert C.SEED_RANGE[0] <= at.number_input(key="seed_input").value <= C.SEED_RANGE[1]
    assert (seed0, nseed0) != (at.number_input(key="seed_input").value, nseed1)         # mindestens einer hat sich verändert


def _min_fleet_info(at):
    return [i.value for i in at.info if "Mindestflotte (exakt)" in i.value][0]


def test_noise_seed_changes_only_the_draw_not_the_jobs():
    """Neues Rauschen: dieselbe Mindestflotte (Aufträge unverändert), aber eine andere gezeigte Ziehung; neue Aufträge ändern die Mindestflotte-Meldung nicht zwingend,
    das Rauschen bleibt dabei dasselbe (Seed unverändert)."""
    a = fresh(np="25")
    b = set_and_run(fresh(np="25"), noise_seed_input=1234)
    assert _min_fleet_info(a).split("Eingestellt")[0] == _min_fleet_info(b).split("Eingestellt")[0]
    late = lambda at: [m.value for m in at.metric if m.label == "Aufträge mit Wartezeit"]
    assert late(a) != late(b) or [m.value for m in a.metric][:4] != [m.value for m in b.metric][:4]


# ---------------------------------------------------------------------------------------------------
# Regler an den Grenzen
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("key,value", [
    ("n_cranes_slider", 2), ("n_cranes_slider", 6), ("jobs_per_crane_slider", 10), ("jobs_per_crane_slider", 40), ("cycle_slider", 60), ("cycle_slider", 150),
    ("jitter_slider", 0), ("jitter_slider", 20), ("blocks_slider", 3), ("blocks_slider", 8), ("fleet_delta_slider", -4), ("fleet_delta_slider", 4),
    ("noise_pct_slider", 0), ("noise_pct_slider", 50), ("seed_input", 0), ("seed_input", 9999), ("noise_seed_input", 0), ("noise_seed_input", 9999),
])
def test_every_slider_at_min_and_max(key, value):
    at = set_and_run(fresh(), **{key: value})
    assert len(at.get("plotly_chart")) >= 2
    assert not at.exception


def test_extreme_terminals():
    big = set_and_run(fresh(), n_cranes_slider=6, jobs_per_crane_slider=40, cycle_slider=60)                # 240 Aufträge, dichter Takt
    assert [m.label for m in big.metric][:4] == [C.STRATEGY_LABELS[k] for k in C.STRATEGY_KEYS]
    tiny = set_and_run(fresh(), n_cranes_slider=2, jobs_per_crane_slider=10, cycle_slider=150, fleet_delta_slider=-4)
    assert any("mindestens ein Fahrzeug" in i.value for i in tiny.info)                # Flotte auf 1 begrenzt, benannt
    assert dict(metric_map(tiny)[:4])[C.STRATEGY_LABELS[C.STRAT_PLAN]] == "–"


def test_no_jobs_multiply_beyond_max():
    assert C.N_CRANES_RANGE[1] * C.JOBS_PER_CRANE_RANGE[1] <= C.MAX_JOBS


# ---------------------------------------------------------------------------------------------------
# Verfahren nicht definiert unter dem Minimum
# ---------------------------------------------------------------------------------------------------
def test_plan_metrics_dash_below_minimum_with_reason():
    at = set_and_run(fresh(), fleet_delta_slider=-1)
    labels = {m.label: m.value for m in at.metric[:4]}
    assert labels[C.STRATEGY_LABELS[C.STRAT_PLAN]] == "–" and labels[C.STRATEGY_LABELS[C.STRAT_REDISPATCH]] == "–"
    assert labels[C.STRATEGY_LABELS[C.STRAT_EARLIEST]] != "–"
    assert any("Optimalpläne gibt es erst ab der Mindestflotte" in i.value for i in at.info)
    right = fresh(vw="plan")
    set_and_run(right, fleet_delta_slider=-1)
    assert any("keinen Plan ohne Kranwartezeit" in i.value for i in right.info)             # Begründung statt leerem Diagramm


# ---------------------------------------------------------------------------------------------------
# Urteil in drei Zuständen
# ---------------------------------------------------------------------------------------------------
def _patch_verdict(monkeypatch, kind, pct):
    monkeypatch.setattr(E, "verdict", lambda sweep, key, i, reference=C.BASELINE: Verdict(kind, -0.1 if kind == "better" else 0.1, 0.01, pct, 0.2))


def test_verdict_better_success(monkeypatch):
    _patch_verdict(monkeypatch, "better", -20.0)
    at = fresh()
    assert len([s for s in at.success if "robuster" in s.value]) == 3
    text = [s.value for s in at.success if "robuster" in s.value][0]
    assert "20 % weniger" in text and "0.10 s" in text


def test_verdict_better_without_percent_when_reference_never_waits(monkeypatch):
    _patch_verdict(monkeypatch, "better", None)
    at = fresh()
    assert any("0.10 s weniger" in s.value for s in at.success)


def test_verdict_worse_warning(monkeypatch):
    _patch_verdict(monkeypatch, "worse", 35.0)
    at = fresh()
    ws = [w.value for w in at.warning if "kostet hier Kranwartezeit" in w.value]
    assert len(ws) == 3 and all("35 % mehr" in w for w in ws)
    _patch_verdict(monkeypatch, "worse", None)
    at2 = fresh()
    assert any("nie wartet" in w.value for w in at2.warning)


def test_verdict_unclear_info(monkeypatch):
    _patch_verdict(monkeypatch, "unclear", 1.0)
    at = fresh()
    us = [i.value for i in at.info if "Kein klarer Unterschied" in i.value]
    assert len(us) == 3 and all("Rauschens" in u for u in us)


def test_real_verdicts_default_scenario_is_worse_and_plan_undefined_below_minimum():
    at = fresh()
    assert len([w for w in at.warning if "kostet hier Kranwartezeit" in w.value]) == 3
    below = set_and_run(fresh(), fleet_delta_slider=-1)
    assert any("unter der Mindestflotte nicht definiert" in c.value for c in below.caption)
    assert len([w for w in below.warning if "kostet hier" in w.value or "kostet" in w.value]) <= 1        # nur Bestfit hat ein Urteil


def test_no_noise_no_reserve_gives_no_clear_difference_only_where_true():
    at = set_and_run(fresh(), noise_pct_slider=0, fleet_delta_slider=2)
    unclear = [i.value for i in at.info if "Kein klarer Unterschied" in i.value]
    assert len(unclear) >= 1


# ---------------------------------------------------------------------------------------------------
# Exakt-Tab
# ---------------------------------------------------------------------------------------------------
SMALL = dict(n_cranes_slider=2, jobs_per_crane_slider=10)


def test_exact_tab_at_minimum_shows_proof_without_button():
    at = fresh()
    assert not [b for b in at.button if "Optimum berechnen" in b.label]
    assert any("Prüfung ohne Löser" in s.value for s in at.success)


def test_exact_tab_below_minimum_needs_click_then_shows_optimum():
    at = set_and_run(fresh(), fleet_delta_slider=-1, **SMALL)
    btn = next(b for b in at.button if b.label == "🧮 Optimum berechnen")
    assert any("Noch nichts berechnet" in i.value for i in at.info)
    btn.click().run()
    assert not at.exception
    assert any(m.label.startswith("Optimum der Kranwartezeit") for m in at.metric)
    assert not any("Noch nichts berechnet" in i.value for i in at.info)


def test_exact_result_goes_stale_when_settings_change():
    at = set_and_run(fresh(), fleet_delta_slider=-1, **SMALL)
    next(b for b in at.button if b.label == "🧮 Optimum berechnen").click().run()
    set_and_run(at, seed_input=5)
    assert any("zuletzt berechnete Optimum" in i.value for i in at.info)
    assert not any(m.label.startswith("Optimum der Kranwartezeit") for m in at.metric)


def test_comparison_tab_lists_all_strategies_and_gap_after_exact():
    at = set_and_run(fresh(), fleet_delta_slider=-1, **SMALL)
    tables = at.dataframe
    assert len(tables) == 1
    df = tables[0].value
    assert list(df["Verfahren"]) == [C.STRATEGY_LABELS[k] for k in C.STRATEGY_KEYS]
    assert df.loc[2].drop("Verfahren").isna().all() and df.loc[3].drop("Verfahren").isna().all()          # Optimalpläne unter dem Minimum: leer
    assert df.loc[0].drop("Verfahren").notna().all()
    next(b for b in at.button if b.label == "🧮 Optimum berechnen").click().run()
    assert any("Abstand zum Optimum" in c.value for c in at.caption)


# ---------------------------------------------------------------------------------------------------
# Texte
# ---------------------------------------------------------------------------------------------------
def test_texts_mention_limits_and_no_dead_file_links():
    at = fresh()
    md = "\n".join(m.value for m in at.markdown)
    assert "Grenzen dieses Modells" in md and "Größenordnungen aus einer Simulation" in md
    assert "Kran-Kopplung" in md and "Satz von König" in md
    assert "](" not in md.replace("https://sebastianhanisch.net", "")                 # keine Dateilinks im Markdown der App
    for word in ("Aufträge", "Brücke", "Störung", "überdeckung"):
        assert word in md                                                             # echte Umlaute
    for ascii_form in ("Auftraege", "Bruecke", "Stoerung"):
        assert ascii_form not in md


# ---------------------------------------------------------------------------------------------------
# Nachgeschärft nach der Fehler-Einbau-Prüfung
# ---------------------------------------------------------------------------------------------------
def test_main_metric_deltas_are_mine_minus_reference_with_inverse_colours():
    from streamlit.proto.Metric_pb2 import Metric as MetricProto

    at = fresh()
    main = at.metric[:4]
    ref_value = float(main[0].value.split()[0])
    seen = set()
    for m in main[1:]:
        delta = float(m.delta.split()[0])
        assert abs(delta - (float(m.value.split()[0]) - ref_value)) <= 0.011              # Delta = dieses Verfahren minus Referenz
        expected = MetricProto.GRAY if round(delta, 2) == 0 else (MetricProto.RED if delta > 0 else MetricProto.GREEN)    # weniger Kranwartezeit ist besser
        assert m.proto.color == expected
        seen.add(expected)
    assert MetricProto.RED in seen


def test_noise_curve_is_computed_for_the_effective_fleet(monkeypatch):
    calls = []
    original = E.noise_sweep

    def spy(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(E, "noise_sweep", spy)
    fresh(nc="3", jc="13", cy="95", fd="1")                                                # eigene Terminalgröße: nicht aus dem Cache
    assert calls and calls[-1][-1] == 1                                                     # Abstand der eingestellten Flotte, nicht ein anderer Wert
    calls.clear()
    fresh(nc="3", jc="14", cy="95", fd="-1")
    assert calls and calls[-1][-1] == -1


def test_reserve_metrics_show_each_strategys_own_value(monkeypatch):
    values = {C.STRAT_EARLIEST: 1, C.STRAT_BESTFIT: 2, C.STRAT_PLAN: None, C.STRAT_REDISPATCH: 0}
    monkeypatch.setattr(E, "reserve_need", lambda sweep, key, share=C.ZERO_WAIT_SHARE: values[key])
    at = fresh()
    labels = [C.STRATEGY_LABELS[k] for k in C.STRATEGY_KEYS]
    group = [m for m in at.metric if m.label in labels][4:8]                                # zweite Gruppe: Reservebedarf (erste: Hauptansicht)
    assert [m.value for m in group] == ["+1", "+2", "–", "0"]


# ---------------------------------------------------------------------------------------------------
# Jedes Preset zeigt in der App seine Geschichte (Hauptansicht)
# ---------------------------------------------------------------------------------------------------
def _main_values(at):
    out = {}
    for m in at.metric[:4]:
        out[m.label] = None if m.value == "–" else float(m.value.split()[0])
    return out


def _load_preset(name):
    at = fresh()
    next(b for b in at.button if b.label == name).click().run()
    assert not at.exception
    return at


def test_default_page_uses_the_preset_instance_seed():
    at = fresh()
    assert at.number_input(key="seed_input").value == C.PRESETS["Knapp geplant"]["seed"]


def test_preset_knapp_geplant_shows_no_crane_wait_for_the_plan():
    v = _main_values(_load_preset("Knapp geplant"))
    assert v[C.STRATEGY_LABELS[P_]] == 0 and v[C.STRATEGY_LABELS[R_]] == 0 and v[C.STRATEGY_LABELS[B_]] == 0 and v[C.STRATEGY_LABELS[E_]] <= 0.5


def test_preset_eins_zu_wenig_is_almost_free_and_zwei_zu_wenig_is_not():
    one = _main_values(_load_preset("Eins zu wenig"))
    two = _main_values(_load_preset("Zwei zu wenig"))
    assert one[C.STRATEGY_LABELS[E_]] <= 1.0 and one[C.STRATEGY_LABELS[P_]] is None
    assert two[C.STRATEGY_LABELS[E_]] >= 2.0 and two[C.STRATEGY_LABELS[E_]] >= 10 * one[C.STRATEGY_LABELS[E_]]


def test_preset_rauschen_shows_the_plan_worst():
    v = _main_values(_load_preset("Rauschen 25 %"))
    e, b, p, r = (v[C.STRATEGY_LABELS[k]] for k in (E_, B_, P_, R_))
    assert p >= 5 * e and e < r < p and e < b < p


def test_preset_mit_reserve_makes_the_simple_rule_wait_free_and_not_the_plan():
    at = _load_preset("Mit Reserve")
    v = _main_values(at)
    assert v[C.STRATEGY_LABELS[E_]] == 0 and all(v[C.STRATEGY_LABELS[k]] > 0 for k in (B_, P_, R_))
    assert any("Nächstes freies 100 %" in i.value for i in at.info)


def test_pdf_download_button_is_in_the_main_view_and_survives_all_scenarios():
    at = fresh()
    buttons = at.get("download_button")
    assert len(buttons) == 1 and "PDF" in buttons[0].proto.label and buttons[0].proto.url.endswith(".pdf")
    for delta in (-4, 4):
        assert len(set_and_run(at, fleet_delta_slider=delta).get("download_button")) == 1                 # auch unter dem Minimum (Optimalpläne fehlen)
    assert len(set_and_run(at, noise_pct_slider=0).get("download_button")) == 1


def test_verdict_sentences_are_well_formed_in_all_four_variants(monkeypatch):
    cases = [("better", -20.0, "im Mittel **20 % weniger** Kranwartezeit (0.10 s je Auftrag, Standardfehler 0.01). "),
             ("better", None, "im Mittel **0.10 s weniger** Kranwartezeit je Auftrag (Standardfehler 0.01). "),
             ("worse", 35.0, "im Mittel **35 % mehr** Kranwartezeit (0.10 s je Auftrag, Standardfehler 0.01). "),
             ("worse", None, "im Mittel **0.10 s mehr** Kranwartezeit je Auftrag, wo Nächstes freies nie wartet (Standardfehler 0.01). ")]
    for kind, pct, expected in cases:
        _patch_verdict(monkeypatch, kind, pct)
        at = fresh()
        texts = [x.value for x in (at.success if kind == "better" else at.warning) if "Nächstes freies" in x.value and "im Mittel" in x.value]
        assert len(texts) == 3 and all(expected in t for t in texts), (kind, pct, texts[0])
        assert all(t.count("(") == t.count(")") for t in texts)
