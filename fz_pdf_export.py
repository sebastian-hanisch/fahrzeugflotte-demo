"""PDF-Export des Ergebnisses (fpdf2, Helvetica-Kernschrift, nur Text und Tabellen).

Die Kernschriften kennen nur Latin-1: Umlaute und "×" sind erlaubt, aber "–" (Gedankenstrich), "€", "σ", "≥", Emoji usw.
lassen fpdf2 abstürzen. Deshalb läuft jeder Text durch pdf_text(); Verfahren erscheinen mit ihren Kurznamen ohne Emoji.
"""

import time

import fz_constants as C

_REPLACEMENTS = {
    "–": "-", "—": "-", "‑": "-", "−": "-", "σ": "Sigma", "δ": "Delta", "≥": ">=", "≤": "<=", "→": "->", "≈": "ca.", "€": "EUR",
    "·": "-", "“": '"', "”": '"', "„": '"', "’": "'", "‘": "'", "▽": "v", "◆": "*", "±": "+-",
}


def pdf_text(text):
    """Text für die Helvetica-Kernschrift: bekannte Sonderzeichen ersetzen, den Rest Latin-1-sicher machen."""
    for old, new in _REPLACEMENTS.items():
        text = text.replace(old, new)
    return text.encode("latin-1", "replace").decode("latin-1")


def short_name(key):
    return C.STRATEGY_SHORT[key].replace("<br>", " ")


def _seconds(x):
    return f"{x:.2f}"


def generate_fz_pdf(inst, kmin, K, outcomes, focus, settings, edge=None, reserve=None, compress=True):
    """Ergebnis der aktuellen Einstellung als PDF: Szenario, Zusammenfassung, Verfahrensvergleich, gezeigte Ziehung, Kante und Reservebedarf, Hinweise.

    `outcomes`: die vier StrategyOutcome der gezeigten Ziehung; `focus`: FocusStats je Verfahren (Mittel über viele Rausch-Ziehungen); `settings`: dict mit den
    Reglerwerten (n_cranes, jobs_per_crane, cycle, jitter, blocks, seed, fleet_delta, noise_pct, noise_seed); `edge`: {0/-1/-2: s je Auftrag oder None};
    `reserve`: {Verfahren: kleinster Abstand oder None}."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    stats = {s.key: s for s in focus}
    base = stats[C.BASELINE]

    pdf = FPDF()
    pdf.set_compression(compress)
    pdf.add_page()

    def line(text, height=7, width=0):
        pdf.cell(width, height, pdf_text(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def heading(text):
        pdf.set_font("Helvetica", "B", 12)
        line(text, 8)
        pdf.set_font("Helvetica", "", 10)

    def pairs(rows):
        for label, value in rows:
            pdf.cell(70, 6, pdf_text(label), border=0)
            line(value, 6)

    def table(headers, widths, rows):
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(230, 230, 230)
        for header, width in zip(headers, widths):
            pdf.cell(width, 7, pdf_text(header), border=1, fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.ln(7)
        pdf.set_font("Helvetica", "", 9)
        for row in rows:
            for value, width in zip(row, widths):
                pdf.cell(width, 7, pdf_text(str(value)), border=1, new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.ln(7)

    def keep_together(height):
        """Beginnt einen Abschnitt auf einer neuen Seite, wenn er sonst über den Seitenumbruch liefe (keine halb abgeschnittenen Listen)."""
        if pdf.get_y() + height > pdf.h - pdf.b_margin:
            pdf.add_page()

    def note(text, size=8):
        pdf.set_font("Helvetica", "I", size)
        pdf.set_text_color(110, 110, 110)
        pdf.multi_cell(0, 5, pdf_text(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)

    pdf.set_font("Helvetica", "B", 16)
    line("Wie viele Fahrzeuge braucht eine Containerbrücke?", 10)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(120, 120, 120)
    line(f"Erstellt: {time.strftime('%d.%m.%Y %H:%M')}  -  sebastianhanisch.net", 6)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    s = settings
    delta = K - kmin
    heading("Szenario")
    pairs([
        ("Anzahl Brücken", str(s["n_cranes"])),
        ("Aufträge je Brücke", f"{s['jobs_per_crane']} ({len(inst.jobs)} insgesamt)"),
        ("Takt je Brücke", f"{s['cycle']} s (Streuung {s['jitter']} s)"),
        ("Anzahl Blöcke", str(s["blocks"])),
        ("Seed der Aufträge", str(s["seed"])),
        ("Mindestflotte (exakt)", f"{kmin} Fahrzeuge"),
        ("Eingestellte Flotte", f"{K} Fahrzeuge (Minimum {'+' if delta >= 0 else '-'} {abs(delta)})"),
        ("Fahrzeit-Rauschen", f"{s['noise_pct']} %" if s["noise_pct"] else "keines (nominale Fahrzeiten)"),
        ("Seed des Rauschens", str(s["noise_seed"])),
    ])
    pdf.ln(3)

    heading("Zusammenfassung")
    if base.available:
        pairs([("Nächstes freies (Referenz)", f"{_seconds(base.mean_per_job)} s Kranwartezeit je Auftrag")]
              + [(short_name(k), f"{_seconds(stats[k].mean_per_job)} s ({stats[k].paired_diff[0]:+.2f} s gegen Nächstes freies)")
                 for k in C.STRATEGY_KEYS if k != C.BASELINE and stats[k].available])
    n_draws = base.n_draws
    note(("Mittel über eine einzige, exakte Ziehung (ohne Rauschen). " if n_draws == 1 else f"Mittel über {n_draws} Rausch-Ziehungen ab dem Seed des Rauschens. ")
         + "Die Kranwartezeit ist die Zeit, die eine Brücke auf ihr Fahrzeug wartet; ein Einzelfall kann vom Mittel deutlich abweichen.", 9)
    pdf.ln(3)

    heading("Verfahrensvergleich")
    rows = []
    for k in C.STRATEGY_KEYS:
        st = stats[k]
        if st.available:
            rows.append([short_name(k), _seconds(st.mean_per_job), f"{st.zero_share * 100:.0f}", f"{st.mean_utilization * 100:.0f}",
                         "0.00" if k == C.BASELINE else f"{st.paired_diff[0]:+.2f}"])
        else:
            rows.append([short_name(k), "-", "-", "-", "-"])
    table(["Verfahren", "Kranwartezeit je Auftrag (s)", "Ziehungen ohne Wartezeit (%)", "Auslastung (%)", "Differenz (s)"], [46, 46, 46, 28, 24], rows)
    note("Differenz = Kranwartezeit je Auftrag dieses Verfahrens minus Nächstes freies (negativ = besser). Der Optimalplan (starr und mit Umdisposition) "
         "existiert erst ab der Mindestflotte.")
    pdf.ln(3)

    heading("Gezeigte Ziehung" + ("" if s["noise_pct"] else " (ohne Rauschen)"))
    rows = []
    for o in outcomes:
        if o.available:
            rows.append([short_name(o.key), o.wait_total, o.late_jobs, f"{o.utilization * 100:.0f}"])
        else:
            rows.append([short_name(o.key), "-", "-", "-"])
    table(["Verfahren", "Kranwartezeit gesamt (s)", "Aufträge mit Wartezeit", "Auslastung (%)"], [46, 56, 56, 32], rows)
    pdf.ln(3)

    if edge is not None or reserve is not None:
        keep_together(80)
        heading("Kante und Reservebedarf")
        if edge is not None:
            pairs([("Nächstes freies bei Minimum", _edge(edge.get(0))), ("bei Minimum - 1", _edge(edge.get(-1))), ("bei Minimum - 2", _edge(edge.get(-2)))])
        if reserve is not None:
            pdf.ln(2)
            pairs([(f"Reservebedarf {short_name(k)}", "nie im untersuchten Bereich" if reserve.get(k) is None else f"{reserve[k]:+d} Fahrzeuge" if reserve[k] else "0")
                   for k in C.STRATEGY_KEYS])
        note("Kante: mittlere Kranwartezeit je Auftrag bei der Mindestflotte und einem bzw. zwei Fahrzeugen weniger (Stichprobe aus 10 bis 20 Auftragsfolgen, eingestelltes "
             "Rauschen). Reservebedarf: kleinster Abstand zum Minimum, bei dem ein Verfahren in mindestens 95 % der Szenarien nie wartet.")
        pdf.ln(3)

    keep_together(70)
    heading("Hinweise zum Modell")
    pdf.set_font("Helvetica", "", 9)
    for text in [
        "Aufträge folgen dem Takt der Brücken; eine Brücke nimmt höchstens alle 40 s einen Container auf. Wartet sie auf ein Fahrzeug, verschiebt sich ihre ganze Restfolge.",
        "Das Rauschen ist gleichverteilt und nur verspätend (jede Fahrt bis zu x % länger), die Faktoren sind für alle Verfahren gleich. Keine Fahrspur-, Kreuzungs- und Staukonflikte, keine Blockkapazität.",
        "Die Mindestflotte ist exakt (maximales Matching, mit Knotenüberdeckung bewiesen); dass Bestfit sie in über 99 % der Fälle trifft, ist gemessen, nicht bewiesen.",
        "Fahrzeiten, Takt und Blockverteilung sind Annahmen ohne Kalibrierung an echten Daten. Alle Zahlen sind Größenordnungen aus einer Simulation, keine Messung an Echtdaten.",
    ]:
        pdf.multi_cell(0, 5, pdf_text("- " + text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    return bytes(pdf.output())


def _edge(value):
    return "nicht darstellbar (weniger als ein Fahrzeug)" if value is None else f"{_seconds(value)} s je Auftrag"
