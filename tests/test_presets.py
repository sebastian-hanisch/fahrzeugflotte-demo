"""Tests der Regler-Spezifikation: Permalink-Auswertung (begrenzen, einrasten, Müll ignorieren), Presets innerhalb der Reglergrenzen, Konsistenz mit den Konstanten."""

import math

import pytest

import fz_constants as C
import fz_presets as P
from fz_scenario import make_instance

S = P.SETTING_SPECS


def test_parse_clamps_to_range():
    spec = S["n_cranes_slider"]
    assert P.parse_setting(spec, "99") == C.N_CRANES_RANGE[1]
    assert P.parse_setting(spec, "-5") == C.N_CRANES_RANGE[0]
    assert P.parse_setting(spec, "3") == 3
    fd = S["fleet_delta_slider"]
    assert P.parse_setting(fd, "-99") == -4 and P.parse_setting(fd, "99") == 4 and P.parse_setting(fd, "-2") == -2


def test_parse_snaps_to_step_from_lower_bound():
    np_ = S["noise_pct_slider"]
    assert P.parse_setting(np_, "27") == 25 and P.parse_setting(np_, "28") == 30 and P.parse_setting(np_, "50") == 50
    assert P.parse_setting(np_, "49") == 50                                # nie über der oberen Grenze
    cy = S["cycle_slider"]
    assert P.parse_setting(cy, "77") == 75 and P.parse_setting(cy, "78") == 80 and P.parse_setting(cy, "150") == 150
    assert P.parse_setting(cy, "149") == 150


def test_parse_ignores_garbage():
    for key in ("n_cranes_slider", "seed_input", "noise_pct_slider"):
        assert P.parse_setting(S[key], "abc") is None
        assert P.parse_setting(S[key], None) is None
        assert P.parse_setting(S[key], "") is None
    assert P.parse_setting(S["view_radio"], "junk") is None
    assert P.parse_setting(S["view_radio"], "earliest") is None            # die Referenz steht immer links, ist keine Wahl rechts
    assert P.parse_setting(S["view_radio"], "plan") == "plan"
    assert P.parse_setting(S["n_cranes_slider"], "3.7") is None or P.parse_setting(S["n_cranes_slider"], "3.7") == 3


def test_parse_non_finite_float_is_rejected():
    spec = P.SettingSpec("x", float, 1.0, 0.0, 10.0)
    assert P.parse_setting(spec, "nan") is None and P.parse_setting(spec, "inf") is None
    assert P.parse_setting(spec, "4.5") == 4.5 and P.parse_setting(spec, "99") == 10.0


def test_specs_match_constants_and_defaults_inside_bounds():
    assert S["n_cranes_slider"].default == C.N_CRANES_DEFAULT and S["fleet_delta_slider"].default == C.FLEET_DELTA_DEFAULT
    for key, spec in S.items():
        assert P.bounds(key) == (spec.lo, spec.hi)
        if spec.lo is not None:
            assert spec.lo <= spec.default <= spec.hi
            if spec.step and spec.step > 1:
                assert (spec.default - spec.lo) % spec.step == 0
    assert len({spec.url_param for spec in S.values()}) == len(S)              # keine doppelten Adresszeilen-Namen
    assert S["view_radio"].default in C.RIGHT_VIEW_KEYS


def test_every_preset_is_inside_bounds_and_on_the_step_and_within_max_jobs():
    assert len(C.PRESETS) == 5 and list(C.PRESETS)[:3] == ["Knapp geplant", "Eins zu wenig", "Zwei zu wenig"]
    for name, p in C.PRESETS.items():
        assert set(p) == set(P.PRESET_STATE_KEYS)
        for field, state_key in P.PRESET_STATE_KEYS.items():
            spec = S[state_key]
            assert spec.lo <= p[field] <= spec.hi, (name, field)
            if spec.step and spec.step > 1:
                assert (p[field] - spec.lo) % spec.step == 0, (name, field)
        assert p["n_cranes"] * p["jobs_per_crane"] <= C.MAX_JOBS


def test_scenario_instance_matches_make_instance_and_casts():
    a = P.scenario_instance(3.0, 10.0, 75.0, 10.0, 6.0, 4.0)
    assert a == make_instance(3, 10, 4, 75, 10, 6)


def test_encoders_roundtrip_through_parse():
    for key, spec in S.items():
        raw = spec.encoder(spec.default)
        assert P.parse_setting(spec, raw) == spec.default
    assert S["fleet_delta_slider"].encoder(-3) == "-3"


def test_seed_and_noise_seed_ranges_are_shared_and_draw_streams_do_not_collide():
    assert S["seed_input"].lo == S["noise_seed_input"].lo == C.SEED_RANGE[0] and S["seed_input"].hi == S["noise_seed_input"].hi == C.SEED_RANGE[1]
    import fz_evaluation as E
    draws = {E.noise_for(s, j) for s in (0, 1, 9999) for j in range(C.FOCUS_DRAWS)}
    assert len(draws) == 3 * C.FOCUS_DRAWS and C.FOCUS_DRAWS <= 1000            # Ziehungen verschiedener Seeds überlappen nicht
    assert math.isfinite(C.NOISE_PCT_DEFAULT)


def test_step_grid_starts_at_the_lower_bound_not_at_zero():
    spec = P.SettingSpec("x", int, 1, 1, 21, 5)                               # Raster 1, 6, 11, 16, 21
    assert [P.parse_setting(spec, str(v)) for v in (1, 3, 4, 7, 9, 14, 19, 21)] == [1, 1, 6, 6, 11, 16, 21, 21]


def test_integer_encoder_drops_float_suffix():
    assert S["seed_input"].encoder(4.0) == "4" and S["noise_pct_slider"].encoder(25.0) == "25"
