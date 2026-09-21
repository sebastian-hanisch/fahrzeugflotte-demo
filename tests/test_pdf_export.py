import re

import pytest

import fz_constants as C
import fz_evaluation as E
from fz_dispatch import draw_noise, min_fleet
from fz_pdf_export import generate_fz_pdf, pdf_text, short_name
from fz_presets import scenario_instance

E_, B_, P_, R_ = C.STRAT_EARLIEST, C.STRAT_BESTFIT, C.STRAT_PLAN, C.STRAT_REDISPATCH


def _settings(name="Rauschen 25 %", **override):
    p = dict(C.PRESETS[name])
    p.update(override)
    return p


def _pdf(name="Rauschen 25 %", compress=False, edge="auto", reserve="auto", **override):
    s = _settings(name, **override)
    inst = scenario_instance(s["n_cranes"], s["jobs_per_crane"], s["cycle"], s["jitter"], s["blocks"], s["seed"])
    mf = min_fleet(inst)
    K = E.fleet_size(mf[0], s["fleet_delta"])
    sigma = s["noise_pct"] / 100
    outs = E.run_strategies(inst, K, draw_noise(len(inst.jobs), sigma, E.noise_for(s["noise_seed"], 0)), mf)
    focus = E.focus_stats(inst, K, sigma, s["noise_seed"], n_draws=20, min_fleet_result=mf)
    edge = {0: 0.04, -1: 0.75, -2: None} if edge == "auto" else edge
    reserve = {E_: 1, B_: None, P_: None, R_: 0} if reserve == "auto" else reserve
    data = generate_fz_pdf(inst, mf[0], K, outs, focus, s, edge=edge, reserve=reserve, compress=compress)
    return data, inst, mf[0], K, outs, focus, s


def _texts(data):
    """Alle Textstücke des (unkomprimierten) PDFs als Liste, Latin-1 gelesen, PDF-Escapes aufgelöst."""
    raw = re.findall(rb"\((.*?)\)\s*Tj", data)
    return [t.decode("latin-1").replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\") for t in raw]


def _after(text, label):
    return text[text.index(label) + 1]


# ---------- Sonderzeichen: mit den GENAUEN Zeichen testen (fpdf2 stürzt bei "–" und "€" ab) ----------
EXPECTED = {"–": "-", "—": "-", "−": "-", "€": "EUR", "σ": "Sigma", "δ": "Delta", "≥": ">=", "≤": "<=", "→": "->", "≈": "ca.", "„": '"', "“": '"', "’": "'",
            "·": "-", "▽": "v", "◆": "*", "±": "+-"}


@pytest.mark.parametrize("char,replacement", list(EXPECTED.items()))
def test_pdf_text_replaces_every_known_troublemaker_with_a_readable_equivalent(char, replacement):
    out = pdf_text(f"a{char}b")
    out.encode("latin-1")
    assert out == f"a{replacement}b"


def test_pdf_text_keeps_umlauts_and_times_sign_and_replaces_unknown():
    assert pdf_text("Füllgrad äöüß ÄÖÜ × 3") == "Füllgrad äöüß ÄÖÜ × 3"
    assert pdf_text("日本語").encode("latin-1") == b"???"
    assert "?" in pdf_text("⏭️ Nächstes freies")


def test_short_names_have_no_line_breaks_and_no_emoji():
    for key in C.STRATEGY_KEYS:
        name = short_name(key)
        assert "<br>" not in name and pdf_text(name) == name
    assert short_name(C.STRAT_REDISPATCH) == "Plan + Umdisposition"


# ---------- Inhalt ----------
def test_pdf_is_a_valid_document_with_all_sections():
    data, *_ = _pdf()
    assert data.startswith(b"%PDF") and data.endswith(b"%%EOF\n") and len(data) > 2000
    text = _texts(data)
    for needle in ["Wie viele Fahrzeuge braucht eine Containerbrücke?", "Szenario", "Zusammenfassung", "Verfahrensvergleich", "Gezeigte Ziehung", "Kante und Reservebedarf",
                   "Hinweise zum Modell"]:
        assert needle in text, needle


def test_pdf_scenario_block_pairs_every_label_with_its_own_value():
    data, inst, kmin, K, outs, focus, s = _pdf()
    text = _texts(data)
    assert _after(text, "Anzahl Brücken") == "4" and _after(text, "Aufträge je Brücke") == "30 (120 insgesamt)"
    assert _after(text, "Takt je Brücke") == "75 s (Streuung 10 s)" and _after(text, "Anzahl Blöcke") == "6"
    assert _after(text, "Seed der Aufträge") == str(s["seed"]) and _after(text, "Seed des Rauschens") == str(s["noise_seed"])
    assert _after(text, "Mindestflotte (exakt)") == f"{kmin} Fahrzeuge"
    assert _after(text, "Eingestellte Flotte") == f"{K} Fahrzeuge (Minimum + 0)"
    assert _after(text, "Fahrzeit-Rauschen") == "25 %"


def test_pdf_scenario_follows_settings_and_signs_the_fleet_offset():
    data, inst, kmin, K, *_ = _pdf("Eins zu wenig")
    text = _texts(data)
    assert _after(text, "Eingestellte Flotte") == f"{K} Fahrzeuge (Minimum - 1)" and K == kmin - 1
    assert _after(text, "Fahrzeit-Rauschen") == "keines (nominale Fahrzeiten)"
    data2, _, kmin2, K2, *_ = _pdf("Mit Reserve", n_cranes=3, jobs_per_crane=12, cycle=90, seed=5)
    text2 = _texts(data2)
    assert _after(text2, "Anzahl Brücken") == "3" and _after(text2, "Aufträge je Brücke") == "12 (36 insgesamt)" and _after(text2, "Takt je Brücke") == "90 s (Streuung 10 s)"
    assert _after(text2, "Eingestellte Flotte") == f"{K2} Fahrzeuge (Minimum + 2)"


def test_pdf_summary_quotes_the_signed_paired_differences():
    data, inst, kmin, K, outs, focus, s = _pdf()
    text = _texts(data)
    st = {f.key: f for f in focus}
    assert _after(text, "Nächstes freies (Referenz)") == f"{st[E_].mean_per_job:.2f} s Kranwartezeit je Auftrag"
    for k in (B_, P_, R_):
        assert _after(text, short_name(k)) == f"{st[k].mean_per_job:.2f} s ({st[k].paired_diff[0]:+.2f} s gegen Nächstes freies)"
    assert "Mittel über 20 Rausch-Ziehungen ab dem Seed des Rauschens." in " ".join(text)
    assert text.count("Nächstes freies") == 2                                          # nur in den beiden Tabellen; in der Zusammenfassung steht es einmal als "(Referenz)"


def test_pdf_states_a_single_exact_draw_without_noise():
    text = " ".join(_texts(_pdf("Knapp geplant")[0]))
    assert "Mittel über eine einzige, exakte Ziehung" in text and "Rausch-Ziehungen ab" not in text
    assert "Gezeigte Ziehung (ohne Rauschen)" in text


def test_pdf_strategy_table_rows_are_complete_and_in_column_order():
    data, inst, kmin, K, outs, focus, s = _pdf()
    text = _texts(data)
    start = text.index("Differenz (s)") + 1
    st = {f.key: f for f in focus}
    for i, k in enumerate(C.STRATEGY_KEYS):
        row = text[start + 5 * i: start + 5 * i + 5]
        diff = "0.00" if k == E_ else f"{st[k].paired_diff[0]:+.2f}"
        assert row == [short_name(k), f"{st[k].mean_per_job:.2f}", f"{st[k].zero_share * 100:.0f}", f"{st[k].mean_utilization * 100:.0f}", diff], (k, row)


def test_pdf_marks_undefined_strategies_with_a_plain_dash_below_the_minimum():
    data, *_ = _pdf("Eins zu wenig")
    text = _texts(data)
    start = text.index("Differenz (s)") + 1
    assert text[start + 5 * 2: start + 5 * 2 + 5] == [short_name(P_), "-", "-", "-", "-"]
    assert text[start + 5 * 3: start + 5 * 3 + 5] == [short_name(R_), "-", "-", "-", "-"]
    dstart = text.index("Aufträge mit Wartezeit") + 2
    assert text[dstart + 4 * 2: dstart + 4 * 2 + 4] == [short_name(P_), "-", "-", "-"]
    assert "–" not in " ".join(text)


def test_pdf_shown_draw_table_lists_total_waits_and_late_jobs():
    data, inst, kmin, K, outs, focus, s = _pdf()
    text = _texts(data)
    start = text.index("Aufträge mit Wartezeit") + 2
    for i, o in enumerate(outs):
        assert text[start + 4 * i: start + 4 * i + 4] == [short_name(o.key), str(o.wait_total), str(o.late_jobs), f"{o.utilization * 100:.0f}"]


def test_pdf_edge_and_reserve_block():
    data, *_ = _pdf()
    text = _texts(data)
    assert _after(text, "Nächstes freies bei Minimum") == "0.04 s je Auftrag"
    assert _after(text, "bei Minimum - 1") == "0.75 s je Auftrag"
    assert _after(text, "bei Minimum - 2") == "nicht darstellbar (weniger als ein Fahrzeug)"
    assert _after(text, "Reservebedarf Nächstes freies") == "+1 Fahrzeuge"
    assert _after(text, "Reservebedarf Bestfit") == "nie im untersuchten Bereich"
    assert _after(text, "Reservebedarf Plan + Umdisposition") == "0"


def test_pdf_can_omit_edge_and_reserve():
    data, *_ = _pdf(edge=None, reserve=None)
    assert "Kante und Reservebedarf" not in _texts(data)
    only_edge = _texts(_pdf(reserve=None)[0])
    assert "Kante und Reservebedarf" in only_edge and not any(t.startswith("Reservebedarf") for t in only_edge)


@pytest.mark.parametrize("name", list(C.PRESETS))
def test_pdf_is_generated_for_every_preset_compressed_and_uncompressed(name):
    for compress in (True, False):
        data = _pdf(name, compress=compress)[0]
        assert data.startswith(b"%PDF") and len(data) > 1500


def test_pdf_at_the_limits_stays_valid():
    tiny = _pdf(n_cranes=2, jobs_per_crane=10, fleet_delta=-4)[0]
    big = _pdf(n_cranes=6, jobs_per_crane=40, cycle=60, noise_pct=50)[0]
    assert tiny.startswith(b"%PDF") and big.startswith(b"%PDF")


def _pages(data):
    """Textstücke je Seite (unkomprimiertes PDF: ein Inhaltsstrom je Seite)."""
    streams = re.findall(rb"stream\r?\n(.*?)endstream", data, re.S)
    return [[t.decode("latin-1") for t in re.findall(rb"\((.*?)\)\s*Tj", s)] for s in streams]


def test_pdf_sections_are_not_split_across_pages():
    """Die Listen von Kante/Reservebedarf und die Modellhinweise stehen vollständig auf einer Seite (keine halb abgeschnittenen Abschnitte)."""
    for name in ("Rauschen 25 %", "Eins zu wenig", "Knapp geplant"):
        pages = _pages(_pdf(name)[0])
        assert len(pages) <= 2
        page = next(p for p in pages if "Kante und Reservebedarf" in p)
        assert "Reservebedarf Plan + Umdisposition" in page and "bei Minimum - 2" in page, name
        page = next(p for p in pages if "Hinweise zum Modell" in p)
        assert page[-1].endswith("Messung an Echtdaten.") and page.index("Hinweise zum Modell") < len(page) - 4, name       # Überschrift und alle vier Hinweise zusammen
