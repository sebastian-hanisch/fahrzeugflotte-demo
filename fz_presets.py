"""Regler-Spezifikation, Permalink, Presets und Zufalls-Seed-Knöpfe (Standardmuster aus dem OR-Demo-Portfolio, siehe rb_presets.py).

Zwei getrennte Zufallsströme: der Seed der Aufträge und der Seed des Rauschens. So ändert "Neues Rauschen" die Aufträge nie und umgekehrt
(Seed-Kopplungs-Falle aus früheren Demos)."""

import math
import random
from dataclasses import dataclass
from typing import Callable, Optional

import streamlit as st

import fz_constants as C
from fz_scenario import make_instance


def _view(raw):
    if raw not in C.RIGHT_VIEW_KEYS:
        raise ValueError(raw)
    return raw


def _int_text(value):
    return str(int(value))


@dataclass(frozen=True)
class SettingSpec:
    url_param: str
    caster: Callable
    default: object
    lo: Optional[float] = None
    hi: Optional[float] = None
    step: Optional[int] = None
    encoder: Callable = _int_text


SETTING_SPECS = {
    "n_cranes_slider": SettingSpec("nc", int, C.N_CRANES_DEFAULT, *C.N_CRANES_RANGE, 1),
    "jobs_per_crane_slider": SettingSpec("jc", int, C.JOBS_PER_CRANE_DEFAULT, *C.JOBS_PER_CRANE_RANGE, 1),
    "cycle_slider": SettingSpec("cy", int, C.CYCLE_DEFAULT, *C.CYCLE_RANGE, C.CYCLE_STEP),
    "jitter_slider": SettingSpec("ji", int, C.JITTER_DEFAULT, *C.JITTER_RANGE, 1),
    "blocks_slider": SettingSpec("bl", int, C.BLOCKS_DEFAULT, *C.BLOCKS_RANGE, 1),
    "seed_input": SettingSpec("seed", int, C.SEED_DEFAULT, *C.SEED_RANGE, 1),
    "fleet_delta_slider": SettingSpec("fd", int, C.FLEET_DELTA_DEFAULT, *C.FLEET_DELTA_RANGE, 1),
    "noise_pct_slider": SettingSpec("np", int, C.NOISE_PCT_DEFAULT, *C.NOISE_PCT_RANGE, C.NOISE_PCT_STEP),
    "noise_seed_input": SettingSpec("nseed", int, C.NOISE_SEED_DEFAULT, *C.SEED_RANGE, 1),
    "view_radio": SettingSpec("vw", _view, C.VIEW_DEFAULT, encoder=str),
}

PRESET_STATE_KEYS = {
    "n_cranes": "n_cranes_slider", "jobs_per_crane": "jobs_per_crane_slider", "cycle": "cycle_slider", "jitter": "jitter_slider",
    "blocks": "blocks_slider", "seed": "seed_input", "fleet_delta": "fleet_delta_slider", "noise_pct": "noise_pct_slider",
    "noise_seed": "noise_seed_input",
}


def bounds(state_key):
    spec = SETTING_SPECS[state_key]
    return spec.lo, spec.hi


def parse_setting(spec, raw):
    """Wert aus der Adresszeile: umwandeln, auf den Bereich begrenzen, auf die Schrittweite runden. None, wenn er sich nicht auswerten lässt."""
    try:
        value = spec.caster(raw)
    except (ValueError, TypeError):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if spec.lo is not None:
        value = max(spec.lo, value)
    if spec.hi is not None:
        value = min(spec.hi, value)
    if spec.step and spec.step > 1 and spec.lo is not None:
        value = spec.lo + round((value - spec.lo) / spec.step) * spec.step
        value = min(spec.hi, value)
    return value


def init_session_state_defaults():
    for state_key, spec in SETTING_SPECS.items():
        if state_key not in st.session_state:
            st.session_state[state_key] = spec.default


def load_permalink_settings():
    if "permalink_loaded" in st.session_state:
        return
    qp = st.query_params
    for state_key, spec in SETTING_SPECS.items():
        if spec.url_param in qp:
            value = parse_setting(spec, qp[spec.url_param])
            if value is not None:
                st.session_state[state_key] = value
    st.session_state["permalink_loaded"] = True


def sync_query_params(values):
    """values: dict state_key -> aktueller Wert (aus den Widgets, damit dieselbe Änderung, die gerade gerendert wurde, sofort in der Adresszeile landet)."""
    try:
        for state_key, value in values.items():
            st.query_params[SETTING_SPECS[state_key].url_param] = SETTING_SPECS[state_key].encoder(value)
    except Exception:
        pass


def apply_preset(name):
    for field, state_key in PRESET_STATE_KEYS.items():
        st.session_state[state_key] = C.PRESETS[name][field]


# ---------------------------------------------------------------------------------------------------
# Instanz und Seeds
# ---------------------------------------------------------------------------------------------------
def scenario_instance(n_cranes, jobs_per_crane, cycle, jitter, blocks, seed):
    return make_instance(int(n_cranes), int(jobs_per_crane), int(seed), int(cycle), int(jitter), int(blocks))


def randomize_seed():
    """Würfelt einen neuen Auftrags-Seed (jede Auftragsfolge ist spielbar)."""
    st.session_state["seed_input"] = random.randint(*C.SEED_RANGE)


def randomize_noise_seed():
    st.session_state["noise_seed_input"] = random.randint(*C.SEED_RANGE)
