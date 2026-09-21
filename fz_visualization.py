"""Plotly-Diagramme: Fahrzeug-Gantt mit Kranwartezeit-Markern, Kurven über Flotte und Rauschen, Vergleich, Verteilung der Gewinne.

Konventionen des Portfolios: Achsen `fixedrange` (Touch-Scrollen), Vorlage plotly_white, Markerlinien in mittlerem Grau (im dunklen Schema sonst unsichtbar),
Überschriften stehen als Markdown ÜBER dem Diagramm (eine umbrechende Legende überdeckt sonst den Plotly-Titel auf dem Handy). Alle Funktionen sind reine
Rechnung auf den Ergebnisobjekten; Streamlit kommt hier nicht vor."""

import fz_constants as C

LEGEND_TOP = dict(orientation="h", yanchor="bottom", y=1.02, x=0)
LEGEND_BOTTOM = dict(orientation="h", yanchor="top", y=-0.22, x=0)


def _lock_axes(fig):
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig


def time_axis_end(*runs):
    """Gemeinsames Zeitachsen-Ende (auf volle 100 s aufgerundet), damit nebeneinanderstehende Gantt-Diagramme vergleichbar sind."""
    end = max((t.done for run in runs for t in run.trips), default=1)
    return int(-(-end // 100)) * 100


# ---------------------------------------------------------------------------------------------------
# Fahrzeug-Gantt
# ---------------------------------------------------------------------------------------------------
def vehicle_gantt(inst, run, t_range=None, legend=True):
    """Eine Zeile je Fahrzeug. Blau/orange/... = Beladenfahrt (Farbe = Brücke), grau = Leerfahrt zur Brücke, hellgrau = das Fahrzeug steht schon an der Brücke und wartet,
    rot = die Brücke wartet auf das Fahrzeug (Kranwartezeit: von der frühesten möglichen Aufnahme bis zur tatsächlichen), rotes ✕ = Aufnahme nach Wartezeit.
    `legend=False` lässt die Legende weg (nebeneinanderstehende schmale Diagramme; die Farben erklärt dann die Bildunterschrift)."""
    import plotly.graph_objects as go

    K, n = run.fleet, len(run.trips)
    labels = n <= C.GANTT_LABEL_MAX_JOBS
    fig = go.Figure()

    empty = [t for t in run.trips if t.empty_time > 0]
    fig.add_trace(go.Bar(
        base=[t.empty_start for t in empty], x=[t.empty_time for t in empty], y=[t.vehicle + 1 for t in empty], orientation="h", width=0.34,
        marker=dict(color=C.EMPTY_COLOR, line=dict(width=0)), name="Leerfahrt zur Brücke", showlegend=bool(empty), textposition="none",
        text=[f"Auftrag {t.job + 1}: Leerfahrt {t.empty_time} s" for t in empty], hovertemplate="%{text}<extra></extra>"))
    idle = [t for t in run.trips if t.pick - (t.empty_start + t.empty_time) > 0 and t.empty_start != t.pick]
    fig.add_trace(go.Bar(
        base=[t.empty_start + t.empty_time for t in idle], x=[t.pick - t.empty_start - t.empty_time for t in idle], y=[t.vehicle + 1 for t in idle],
        orientation="h", width=0.34, marker=dict(color=C.IDLE_COLOR, line=dict(color=C.MARKER_LINE_COLOR, width=1)), name="Fahrzeug wartet an der Brücke",
        showlegend=bool(idle), textposition="none", text=[f"Auftrag {t.job + 1}: Fahrzeug steht {t.pick - t.empty_start - t.empty_time} s an der Brücke" for t in idle],
        hovertemplate="%{text}<extra></extra>"))

    for q in range(inst.n_cranes):
        trips = [t for t in run.trips if inst.jobs[t.job].crane == q]
        if not trips:
            continue
        texts = []
        for t in trips:
            job = inst.jobs[t.job]
            texts.append(f"<b>Auftrag {t.job + 1}</b> (Brücke {q + 1} → Block {job.block + 1})<br>Fahrplan-Aufnahme: {job.r} s"
                         f"<br>Aufnahme: {t.pick} s &nbsp;|&nbsp; abgesetzt: {t.done} s<br>Kranwartezeit: {t.wait} s")
        fig.add_trace(go.Bar(
            base=[t.pick for t in trips], x=[t.loaded_time for t in trips], y=[t.vehicle + 1 for t in trips], orientation="h", width=0.62,
            marker=dict(color=C.CRANE_COLORS[q % len(C.CRANE_COLORS)], line=dict(color="white", width=1)), name=f"Brücke {q + 1}", text=texts,
            hovertemplate="%{text}<extra></extra>",
            **(dict(customdata=[t.job + 1 for t in trips], texttemplate="%{customdata}", textposition="inside", insidetextanchor="middle",
                    textfont=dict(color="white", size=10)) if labels else dict(textposition="none"))))

    waits = [t for t in run.trips if t.wait > 0]
    if waits:
        fig.add_trace(go.Bar(
            base=[t.base for t in waits], x=[t.wait for t in waits], y=[t.vehicle + 1 - 0.44 for t in waits], orientation="h", width=0.12,
            marker=dict(color=C.CRANE_WAIT_COLOR, line=dict(width=0)), name="Brücke wartet (Kranwartezeit)", hoverinfo="skip"))
        fig.add_trace(go.Scatter(
            x=[t.pick for t in waits], y=[t.vehicle + 1 - 0.44 for t in waits], mode="markers", showlegend=False,
            marker=dict(symbol="x", size=7, color=C.CRANE_WAIT_COLOR, line=dict(width=1.5, color=C.CRANE_WAIT_COLOR)),
            text=[f"Auftrag {t.job + 1}: Brücke {inst.jobs[t.job].crane + 1} wartet {t.wait} s auf das Fahrzeug" for t in waits],
            hovertemplate="%{text}<extra></extra>"))

    fig.update_layout(template="plotly_white", height=max(C.CHART_HEIGHT - 120, 90 + 34 * K) + (80 if legend else 10), barmode="overlay", legend=LEGEND_TOP, showlegend=legend,
                      margin=dict(t=80 if legend else 10, b=50),
                      xaxis_title="Zeit (s)", yaxis_title="Fahrzeug", hovermode="closest", bargap=0)
    fig.update_xaxes(range=list(t_range) if t_range else [0, time_axis_end(run)])
    fig.update_yaxes(range=[K + 0.6, 0.4], tickmode="array", tickvals=list(range(1, K + 1)), ticktext=[f"F{v}" for v in range(1, K + 1)])
    return _lock_axes(fig)


# ---------------------------------------------------------------------------------------------------
# Kurven
# ---------------------------------------------------------------------------------------------------
LOG_TICKS = [C.LOG_FLOOR, 0.1, 1, 10, 100, 1000]
LOG_TICK_TEXT = ["0", "0.1", "1", "10", "100", "1000"]


def _floor(v):
    return max(v, C.LOG_FLOOR)


def _curve_traces(fig, sweep, log):
    import plotly.graph_objects as go

    xs = list(sweep.axis)
    for key in C.STRATEGY_KEYS:
        pts = [i for i in range(len(xs)) if sweep.available(key, i)]
        if not pts:
            continue
        color, label = C.STRATEGY_COLORS[key], C.STRATEGY_LABELS[key]
        x = [xs[i] for i in pts]
        mean = [sweep.mean(key, i) for i in pts]
        sem = [sweep.sem(key, i) for i in pts]
        y = [_floor(m) for m in mean] if log else mean
        upper = [_floor(m + e) for m, e in zip(mean, sem)] if log else [m + e for m, e in zip(mean, sem)]
        lower = [_floor(m - e) for m, e in zip(mean, sem)] if log else [max(0.0, m - e) for m, e in zip(mean, sem)]
        fig.add_trace(go.Scatter(x=x + x[::-1], y=upper + lower[::-1], fill="toself", fillcolor=color, opacity=0.15, line=dict(width=0), hoverinfo="skip",
                                 showlegend=False, name=f"{label} (Band)"))
        axis_txt = "Abstand zum Minimum %{x:+d}" if sweep.axis_name == "delta" else "Rauschen %{x} %"
        fig.add_trace(go.Scatter(
            x=x, y=y, mode="lines+markers", name=label, line=dict(color=color, width=2.5), marker=dict(size=6), customdata=[[m] for m in mean],
            hovertemplate=f"<b>{label}</b><br>{axis_txt}<br>%{{customdata[0]:.2f}} s Kranwartezeit je Auftrag<extra></extra>"))


def fleet_curve_figure(sweep, delta_current, reserve=None):
    """Kranwartezeit je Auftrag über den Abstand der Flotte zum exakten Minimum (logarithmische Achse, 0 s am unteren Rand). Band = ± 1 Standardfehler,
    gepunktet = eingestellt, grün gestrichelt = kleinster Abstand, ab dem Nächstes freies in mindestens 95 % der Szenarien nie wartet."""
    fig = _new_figure()
    _curve_traces(fig, sweep, log=True)
    fig.add_vline(x=delta_current, line=dict(color=C.MARKER_LINE_COLOR, width=2, dash="dot"), annotation_text="eingestellt", annotation_position="top",
                  annotation_font=dict(size=11))
    if reserve is not None:
        fig.add_vline(x=reserve, line=dict(color="#2e7d4f", width=2, dash="dash"), annotation_text=f"Nächstes freies wartefrei ab {reserve:+d}",
                      annotation_position="top right", annotation_font=dict(size=12, color="#2e7d4f"))
    fig.update_layout(template="plotly_white", height=C.CHART_HEIGHT + 40, legend=LEGEND_BOTTOM, margin=dict(t=30, b=120), hovermode="closest",
                      xaxis_title="Flotte gegenüber dem exakten Minimum (Fahrzeuge)", yaxis_title="Kranwartezeit je Auftrag (s, logarithmisch)")
    fig.update_xaxes(dtick=1, zeroline=False, range=[min(sweep.axis) - 0.5, max(sweep.axis) + 0.5])       # ohne Leerraum rechts von der letzten Flottengröße
    fig.update_yaxes(type="log", tickmode="array", tickvals=LOG_TICKS, ticktext=LOG_TICK_TEXT, range=[-2.1, _log_top(sweep)])
    return _lock_axes(fig)


def noise_curve_figure(sweep, sigma_current):
    """Kranwartezeit je Auftrag über das Fahrzeit-Rauschen (linear). Band = ± 1 Standardfehler, gepunktet = eingestellt."""
    fig = _new_figure()
    _curve_traces(fig, sweep, log=False)
    fig.add_vline(x=sigma_current, line=dict(color=C.MARKER_LINE_COLOR, width=2, dash="dot"), annotation_text="eingestellt", annotation_position="top",
                  annotation_font=dict(size=11))
    fig.update_layout(template="plotly_white", height=C.CHART_HEIGHT + 40, legend=LEGEND_BOTTOM, margin=dict(t=30, b=120), hovermode="closest",
                      xaxis_title="Fahrzeit-Rauschen (bis zu … % länger)", yaxis_title="Kranwartezeit je Auftrag (s)")
    fig.update_yaxes(rangemode="tozero")
    return _lock_axes(fig)


def _new_figure():
    import plotly.graph_objects as go

    return go.Figure()


def _log_top(sweep):
    """Obere Grenze der logarithmischen Achse (Exponent): etwas über dem größten Wert einer Kurve."""
    import math

    top = max((sweep.mean(k, i) for k in C.STRATEGY_KEYS for i in range(len(sweep.axis)) if sweep.available(k, i)), default=1.0)
    return math.log10(max(top, 1.0)) + 0.25


# ---------------------------------------------------------------------------------------------------
# Verteilung der Gewinne, Vergleich
# ---------------------------------------------------------------------------------------------------
def distribution_figure(dists):
    """Je Verfahren ein gestapelter Balken: Anteil der Szenarien, in denen es gegen Nächstes freies besser / gleich / schlechter abschneidet."""
    import plotly.graph_objects as go

    labels = [C.STRATEGY_SHORT[d.key].replace("<br>", " ") for d in dists]
    fig = go.Figure()
    for attr, name in (("better", "besser als Nächstes freies"), ("equal", "gleich"), ("worse", "schlechter als Nächstes freies")):
        shares = [getattr(d, attr) * 100 for d in dists]
        fig.add_trace(go.Bar(y=labels, x=shares, orientation="h", name=name, marker_color=C.OUTCOME_COLORS[attr],
                             text=[f"{v:.0f} %" if v >= 6 else "" for v in shares], textposition="inside", insidetextanchor="middle",
                             hovertemplate=f"<b>%{{y}}</b><br>{name}: %{{x:.0f}} % der Szenarien<extra></extra>"))
    fig.update_layout(barmode="stack", template="plotly_white", height=110 + 70 * len(dists), legend=dict(LEGEND_BOTTOM, traceorder="normal"),
                      margin=dict(t=20, b=90, l=10), xaxis_title="Anteil der Szenarien (%)")
    fig.update_xaxes(range=[0, 100])
    fig.update_yaxes(autorange="reversed")
    return _lock_axes(fig)


def gain_figure(dists):
    """Median-Gewinn neben Mittel-Gewinn je Verfahren (Summe der Kranwartezeit je Szenario, positiv = besser als Nächstes freies): ein Mittelwert weit vom Median
    heißt, dass wenige Szenarien das Ergebnis tragen."""
    import plotly.graph_objects as go

    labels = [C.STRATEGY_SHORT[d.key] for d in dists]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=labels, y=[d.median_gain for d in dists], name="Median (typisches Szenario)", marker_color="#2a6fb0",
                         hovertemplate="<b>%{x}</b><br>Median-Gewinn %{y:.1f} s<extra></extra>"))
    fig.add_trace(go.Bar(x=labels, y=[d.mean_gain for d in dists], name="Mittelwert", marker_color="#c77700",
                         hovertemplate="<b>%{x}</b><br>Mittel-Gewinn %{y:.1f} s<extra></extra>"))
    fig.add_hline(y=0, line=dict(color=C.MARKER_LINE_COLOR, width=1))
    fig.update_layout(barmode="group", template="plotly_white", height=C.CHART_HEIGHT - 60, legend=LEGEND_BOTTOM, margin=dict(t=20, b=100),
                      yaxis_title="Gewinn gegen Nächstes freies (s je Szenario)")
    return _lock_axes(fig)


def comparison_figure(stats):
    """Zwei Blicke auf die eigene Auftragsfolge über viele Rausch-Ziehungen: Kranwartezeit je Auftrag (Mittel ± Standardfehler) und Anteil der Ziehungen,
    in denen die Brücken nie warten. Nicht definierte Verfahren (Optimalplan unter dem Minimum) fehlen und stehen als „–“ in der Achsenbeschriftung."""
    from plotly.subplots import make_subplots
    import plotly.graph_objects as go

    fig = make_subplots(rows=1, cols=2, subplot_titles=("Kranwartezeit je Auftrag (s)", "Ziehungen ohne Kranwartezeit (%)"), horizontal_spacing=0.14)
    av = [s for s in stats if s.available]
    lab_all = [C.STRATEGY_SHORT[s.key] + ("" if s.available else "<br>–") for s in stats]
    lab_av = [lab for lab, s in zip(lab_all, stats) if s.available]
    colors = [C.STRATEGY_COLORS[s.key] for s in av]
    fig.add_trace(go.Bar(x=lab_av, y=[s.mean_per_job for s in av], error_y=dict(type="data", array=[s.se_per_job for s in av], color=C.MARKER_LINE_COLOR),
                         marker_color=colors, showlegend=False, customdata=[[s.n_draws] for s in av],
                         hovertemplate="<b>%{x}</b><br>%{y:.2f} s je Auftrag (Mittel aus %{customdata[0]} Ziehungen)<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Bar(x=lab_av, y=[s.zero_share * 100 for s in av], marker_color=colors, showlegend=False,
                         hovertemplate="<b>%{x}</b><br>%{y:.0f} % der Ziehungen ohne Kranwartezeit<extra></extra>"), row=1, col=2)
    fig.update_layout(template="plotly_white", height=C.CHART_HEIGHT - 40, margin=dict(t=40, b=60))
    fig.update_xaxes(tickangle=0, tickfont=dict(size=10), categoryorder="array", categoryarray=lab_all)
    fig.update_yaxes(rangemode="tozero", row=1, col=1)
    fig.update_yaxes(range=[0, 100], row=1, col=2)
    if any(not s.available for s in stats):
        fig.add_annotation(text="Optimalplan-Verfahren gibt es erst ab der Mindestflotte", xref="paper", yref="paper", x=0, y=-0.28, showarrow=False,
                           xanchor="left", font=dict(size=11, color=C.MARKER_LINE_COLOR))
    return _lock_axes(fig)
