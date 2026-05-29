"""
Time of Concentration and Lag Assumption Explorer

Learning objective:
Show that transform modeling is not just a software setting: it turns runoff volume into a
runoff hydrograph by making assumptions about watershed response time, especially the
relationship between time of concentration and lag time.

This prototype intentionally fixes drainage area and rainfall-runoff volume so participants
focus on one unchecked assumption: lag time as a fraction of Tc.
"""

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html, dash_table


# -----------------------------
# Constants and style
# -----------------------------

FNI_BLUE = "#015D91"
FNI_GREEN = "#A9C945"
FNI_NAVY = "#093D5E"
FNI_ORANGE = "#E05126"
FNI_TURQUOISE = "#5BC1CF"
FNI_DARK_GRAY = "#4D4D4F"
FNI_NEUTRAL_BLUE = "#93AFB4"

CARD_STYLE = {
    "backgroundColor": "white",
    "border": "1px solid #d9e2e8",
    "borderRadius": "16px",
    "padding": "16px",
    "boxShadow": "0 4px 12px rgba(9, 61, 94, 0.08)",
}

METRIC_CARD_STYLE = {
    "backgroundColor": "white",
    "border": "1px solid #d9e2e8",
    "borderRadius": "16px",
    "padding": "14px 16px",
    "boxShadow": "0 4px 12px rgba(9, 61, 94, 0.08)",
    "minHeight": "112px",
}

CONTROL_LABEL_STYLE = {
    "fontWeight": "bold",
    "display": "block",
    "marginTop": "14px",
    "marginBottom": "6px",
}


# -----------------------------
# Data classes
# -----------------------------

@dataclass
class Scenario:
    name: str
    drainage_area_ac: float
    runoff_depth_in: float
    tc_hr: float
    lag_ratio: float
    peaking_factor: float


@dataclass
class HydrographResult:
    time_hr: np.ndarray
    target_cfs: np.ndarray
    modeled_cfs: np.ndarray
    direct_runoff_acft: float
    modeled_lag_hr: float
    target_lag_hr: float
    modeled_peak_cfs: float
    target_peak_cfs: float
    modeled_time_to_peak_hr: float
    target_time_to_peak_hr: float
    score: float


# -----------------------------
# Helper utilities
# -----------------------------

def safe_float(value, fallback: float) -> float:
    try:
        out = float(value)
        if np.isfinite(out):
            return out
    except Exception:
        pass
    return fallback


def build_metric_card(title: str, value: str, subtitle: str) -> html.Div:
    return html.Div(
        [
            html.Div(title, style={"fontSize": "14px", "fontWeight": "bold", "color": FNI_DARK_GRAY, "marginBottom": "8px"}),
            html.Div(value, style={"fontSize": "28px", "fontWeight": "bold", "color": FNI_BLUE, "marginBottom": "6px"}),
            html.Div(subtitle, style={"fontSize": "14px", "color": FNI_DARK_GRAY}),
        ]
    )



def integrate_trapezoid(y: np.ndarray, x: np.ndarray) -> float:
    """Trapezoidal integration using the NumPy 2.x-compatible function name."""
    return float(np.trapezoid(y, x))

# -----------------------------
# Model computation
# -----------------------------

def direct_runoff_volume_acft(area_ac: float, runoff_depth_in: float) -> float:
    """Convert excess rainfall depth over a drainage area to runoff volume."""
    return area_ac * runoff_depth_in / 12.0


def gamma_unit_shape(time_hr: np.ndarray, lag_hr: float) -> np.ndarray:
    """Dimensionless single-peaked unit hydrograph-like response shape.

    This is not intended to reproduce a specific HEC-HMS transform method. It is a teaching
    curve that makes the timing assumption visible while conserving volume after scaling.
    """
    lag_hr = max(float(lag_hr), 0.05)
    alpha = 3.3
    beta = lag_hr / (alpha - 1.0)
    t = np.maximum(time_hr, 0.0)
    shape = (t ** (alpha - 1.0)) * np.exp(-t / beta)
    shape[time_hr <= 0.0] = 0.0
    total = integrate_trapezoid(shape, time_hr)
    if total <= 0.0:
        return np.zeros_like(time_hr)
    return shape / total


def scale_shape_to_flow(time_hr: np.ndarray, shape_per_hr: np.ndarray, runoff_volume_acft: float, peaking_factor: float) -> np.ndarray:
    """Scale a normalized shape to cfs while preserving total runoff volume."""
    volume_ft3 = runoff_volume_acft * 43560.0
    flow_cfs = shape_per_hr * volume_ft3 / 3600.0

    # Peaking factor is a teaching control. It changes shape sharpness while keeping volume fixed.
    # Values above 1 concentrate the hydrograph around its peak; values below 1 spread it out.
    pf = max(float(peaking_factor), 0.25)
    if abs(pf - 1.0) > 1e-9 and flow_cfs.max() > 0.0:
        peak_idx = int(np.argmax(flow_cfs))
        peak_time = time_hr[peak_idx]
        width = max(np.sqrt(integrate_trapezoid((time_hr - peak_time) ** 2 * shape_per_hr, time_hr)), 0.1)
        modifier = np.exp(-0.5 * ((time_hr - peak_time) / width) ** 2)
        adjusted = flow_cfs * ((1.0 - 0.45) + 0.45 * pf * modifier)
        adjusted_volume = integrate_trapezoid(adjusted, time_hr) * 3600.0
        if adjusted_volume > 0.0:
            adjusted *= volume_ft3 / adjusted_volume
        flow_cfs = adjusted

    return flow_cfs


def compute_hydrographs(scenario: Scenario) -> HydrographResult:
    direct_volume = direct_runoff_volume_acft(scenario.drainage_area_ac, scenario.runoff_depth_in)

    modeled_lag_hr = scenario.tc_hr * scenario.lag_ratio
    target_lag_hr = scenario.tc_hr * 0.62
    duration_hr = max(8.0 * scenario.tc_hr, 12.0)
    time_hr = np.linspace(0.0, duration_hr, 361)

    modeled_shape = gamma_unit_shape(time_hr, modeled_lag_hr)
    target_shape = gamma_unit_shape(time_hr, target_lag_hr)

    modeled_flow = scale_shape_to_flow(time_hr, modeled_shape, direct_volume, scenario.peaking_factor)
    target_flow = scale_shape_to_flow(time_hr, target_shape, direct_volume, 1.0)

    modeled_peak = float(modeled_flow.max())
    target_peak = float(target_flow.max())
    modeled_tpeak = float(time_hr[int(np.argmax(modeled_flow))])
    target_tpeak = float(time_hr[int(np.argmax(target_flow))])

    # Score: 100 is perfect. Penalize both timing and shape error using normalized RMSE.
    denom = max(target_peak, 1.0)
    nrmse = float(np.sqrt(np.mean((modeled_flow - target_flow) ** 2)) / denom)
    timing_penalty = abs(modeled_tpeak - target_tpeak) / max(target_tpeak, 0.1)
    score = max(0.0, 100.0 * (1.0 - 0.85 * nrmse - 0.15 * timing_penalty))

    return HydrographResult(
        time_hr=time_hr,
        target_cfs=target_flow,
        modeled_cfs=modeled_flow,
        direct_runoff_acft=direct_volume,
        modeled_lag_hr=modeled_lag_hr,
        target_lag_hr=target_lag_hr,
        modeled_peak_cfs=modeled_peak,
        target_peak_cfs=target_peak,
        modeled_time_to_peak_hr=modeled_tpeak,
        target_time_to_peak_hr=target_tpeak,
        score=score,
    )


def summarize_results(scenario: Scenario, result: HydrographResult) -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["Drainage area", scenario.drainage_area_ac, "ac", "Fixed for this exercise"],
            ["Runoff depth after losses", scenario.runoff_depth_in, "in", "Fixed input to transform step"],
            ["Direct runoff volume", result.direct_runoff_acft, "acre-ft", "Area times excess rainfall"],
            ["Time of concentration", scenario.tc_hr, "hr", "Fixed result of flow path calculation"],
            ["Modeled lag time", result.modeled_lag_hr, "hr", "Tc times selected lag ratio"],
            ["Target lag time", result.target_lag_hr, "hr", "Hidden target for comparison"],
            ["Modeled peak", result.modeled_peak_cfs, "cfs", "Participant hydrograph"],
            ["Target peak", result.target_peak_cfs, "cfs", "Reference hydrograph"],
            ["Modeled time to peak", result.modeled_time_to_peak_hr, "hr", "Participant hydrograph"],
            ["Target time to peak", result.target_time_to_peak_hr, "hr", "Reference hydrograph"],
        ],
        columns=["Metric", "Value", "Unit", "Interpretation"],
    )


# -----------------------------
# Plotting
# -----------------------------

def make_hydrograph_figure(result: HydrographResult) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=result.time_hr,
            y=result.target_cfs,
            mode="lines",
            name="Target runoff hydrograph",
            line={"width": 4, "color": FNI_NAVY},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=result.time_hr,
            y=result.modeled_cfs,
            mode="lines",
            name="Modeled runoff hydrograph",
            line={"width": 4, "color": FNI_GREEN},
        )
    )
    fig.update_layout(
        title="Runoff Hydrograph Match",
        xaxis_title="Time (hours)",
        yaxis_title="Flow (cfs)",
        template="plotly_white",
        legend_title_text="Series",
        margin={"l": 55, "r": 20, "t": 60, "b": 50},
    )
    return fig


def make_assumption_figure(scenario: Scenario, result: HydrographResult) -> go.Figure:
    x = ["Tc", "Assumed lag", "Target lag"]
    y = [scenario.tc_hr, result.modeled_lag_hr, result.target_lag_hr]
    colors = [FNI_BLUE, FNI_GREEN, FNI_NAVY]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=x,
            y=y,
            marker={"color": colors},
            text=[f"{v:.2f} hr" for v in y],
            textposition="auto",
            name="Timing assumption",
        )
    )
    fig.update_layout(
        title="What the Transform Step Is Assuming",
        xaxis_title="Timing term",
        yaxis_title="Hours",
        template="plotly_white",
        showlegend=False,
        margin={"l": 55, "r": 20, "t": 60, "b": 50},
    )
    return fig


def make_workflow_figure() -> go.Figure:
    labels = ["Rainfall", "Losses", "Runoff volume", "Transform", "Runoff hydrograph"]
    y = [1, 1, 1, 1, 1]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=list(range(len(labels))),
            y=y,
            mode="markers+text+lines",
            text=labels,
            textposition="bottom center",
            marker={"size": [26, 26, 30, 30, 34], "color": [FNI_NEUTRAL_BLUE, FNI_ORANGE, FNI_BLUE, FNI_GREEN, FNI_NAVY]},
            line={"width": 4, "color": FNI_NEUTRAL_BLUE},
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        title="Conceptual Workflow",
        xaxis={"visible": False, "range": [-0.4, 4.4]},
        yaxis={"visible": False, "range": [0.65, 1.25]},
        template="plotly_white",
        margin={"l": 20, "r": 20, "t": 60, "b": 70},
        height=240,
    )
    return fig


# -----------------------------
# Sample scenarios
# -----------------------------

SCENARIOS: Dict[str, Scenario] = {
    "Training Basin A - moderate response": Scenario(
        name="Training Basin A - moderate response",
        drainage_area_ac=640.0,
        runoff_depth_in=1.35,
        tc_hr=2.4,
        lag_ratio=0.60,
        peaking_factor=1.0,
    ),
    "Training Basin B - shorter Tc": Scenario(
        name="Training Basin B - shorter Tc",
        drainage_area_ac=420.0,
        runoff_depth_in=1.60,
        tc_hr=1.35,
        lag_ratio=0.60,
        peaking_factor=1.0,
    ),
    "Training Basin C - larger watershed": Scenario(
        name="Training Basin C - larger watershed",
        drainage_area_ac=1280.0,
        runoff_depth_in=1.10,
        tc_hr=3.8,
        lag_ratio=0.60,
        peaking_factor=1.0,
    ),
}


# -----------------------------
# App layout
# -----------------------------

app = Dash(__name__)
server = app.server

app.layout = html.Div(
    style={
        "fontFamily": "Arial, sans-serif",
        "backgroundColor": "#f5f8fa",
        "minHeight": "100vh",
        "padding": "24px",
        "color": FNI_NAVY,
    },
    children=[
        html.Div(
            style={"maxWidth": "1450px", "margin": "0 auto"},
            children=[
                html.H1("TC and Lag Assumption Explorer", style={"marginBottom": "8px", "color": FNI_BLUE}),
                html.P(
                    "This teaching app fixes drainage area and runoff volume, then lets the participant adjust the transform timing assumption. The point is not to optimize a dozen parameters; it is to see how much the runoff hydrograph depends on the assumed lag relationship.",
                    style={"marginBottom": "20px", "maxWidth": "1050px"},
                ),
                html.Div(
                    style={
                        "display": "grid",
                        "gridTemplateColumns": "360px 1fr",
                        "gap": "20px",
                        "alignItems": "start",
                    },
                    children=[
                        html.Div(
                            style=CARD_STYLE,
                            children=[
                                html.H3("Inputs", style={"marginTop": "0", "color": FNI_BLUE}),
                                html.Label("Training basin", style=CONTROL_LABEL_STYLE),
                                dcc.Dropdown(
                                    id="scenario-dropdown",
                                    options=[{"label": key, "value": key} for key in SCENARIOS.keys()],
                                    value="Training Basin A - moderate response",
                                    clearable=False,
                                ),
                                html.Label("Lag ratio: lag time / Tc", style=CONTROL_LABEL_STYLE),
                                dcc.Slider(
                                    id="lag-ratio-slider",
                                    min=0.30,
                                    max=0.90,
                                    step=0.01,
                                    value=0.60,
                                    marks={0.30: "0.30", 0.50: "0.50", 0.60: "0.60", 0.70: "0.70", 0.90: "0.90"},
                                    tooltip={"placement": "bottom", "always_visible": True},
                                ),
                                html.Label("Hydrograph peaking factor", style=CONTROL_LABEL_STYLE),
                                dcc.Slider(
                                    id="peaking-factor-slider",
                                    min=0.75,
                                    max=1.35,
                                    step=0.01,
                                    value=1.00,
                                    marks={0.75: "broad", 1.00: "neutral", 1.35: "peaked"},
                                    tooltip={"placement": "bottom", "always_visible": True},
                                ),
                                html.Div(style={"height": "14px"}),
                                html.H4("Fixed for this exercise", style={"marginBottom": "8px", "color": FNI_BLUE}),
                                html.Ul(
                                    style={"paddingLeft": "20px", "marginBottom": "0"},
                                    children=[
                                        html.Li("Drainage area is already delineated correctly."),
                                        html.Li("Runoff depth has already been produced by the loss method."),
                                        html.Li("Time of concentration has already been calculated."),
                                        html.Li("The participant tests the lag assumption, not the basin area."),
                                    ],
                                ),
                            ],
                        ),
                        html.Div(
                            style={"display": "grid", "gap": "20px"},
                            children=[
                                html.Div(id="status-message", style=CARD_STYLE),
                                html.Div(
                                    style={
                                        "display": "grid",
                                        "gridTemplateColumns": "repeat(4, minmax(0, 1fr))",
                                        "gap": "16px",
                                    },
                                    children=[
                                        html.Div(id="metric-score", style=METRIC_CARD_STYLE),
                                        html.Div(id="metric-volume", style=METRIC_CARD_STYLE),
                                        html.Div(id="metric-lag", style=METRIC_CARD_STYLE),
                                        html.Div(id="metric-peak", style=METRIC_CARD_STYLE),
                                    ],
                                ),
                                html.Div(
                                    style={"display": "grid", "gridTemplateColumns": "1.35fr 1fr", "gap": "20px"},
                                    children=[
                                        html.Div(dcc.Graph(id="hydrograph-plot"), style=CARD_STYLE),
                                        html.Div(dcc.Graph(id="assumption-plot"), style=CARD_STYLE),
                                    ],
                                ),
                                html.Div(dcc.Graph(id="workflow-plot"), style=CARD_STYLE),
                                html.Div(
                                    style=CARD_STYLE,
                                    children=[
                                        html.H3("Summary", style={"marginTop": "0", "color": FNI_BLUE}),
                                        dash_table.DataTable(
                                            id="summary-table",
                                            columns=[
                                                {"name": "Metric", "id": "Metric"},
                                                {"name": "Value", "id": "Value"},
                                                {"name": "Unit", "id": "Unit"},
                                                {"name": "Interpretation", "id": "Interpretation"},
                                            ],
                                            data=[],
                                            style_table={"overflowX": "auto"},
                                            style_header={
                                                "backgroundColor": FNI_BLUE,
                                                "color": "white",
                                                "fontWeight": "bold",
                                            },
                                            style_cell={
                                                "textAlign": "left",
                                                "padding": "10px",
                                                "border": "1px solid #e3eaee",
                                            },
                                            style_data_conditional=[
                                                {"if": {"row_index": "odd"}, "backgroundColor": "#f8fbfc"},
                                            ],
                                        ),
                                    ],
                                ),
                                html.Details(
                                    style=CARD_STYLE,
                                    children=[
                                        html.Summary("Teaching notes", style={"cursor": "pointer", "fontWeight": "bold", "color": FNI_BLUE}),
                                        html.Div(
                                            style={"marginTop": "12px"},
                                            children=[
                                                html.P("Losses answer: how much rainfall becomes direct runoff. Transform answers: when that runoff reaches the outlet and what shape the runoff hydrograph has."),
                                                html.P("This app deliberately does not let the participant change drainage area. In this module, the basin is assumed to be delineated correctly. Changing area would mostly scale volume and peak, which distracts from the lag-time assumption."),
                                                html.P("The hidden target uses a lag ratio of 0.62. The participant can discover how sensitive the hydrograph is to using 0.50, 0.60, 0.67, or another rule-of-thumb value without validation."),
                                            ],
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )
    ],
)


# -----------------------------
# Callbacks
# -----------------------------

@app.callback(
    Output("status-message", "children"),
    Output("metric-score", "children"),
    Output("metric-volume", "children"),
    Output("metric-lag", "children"),
    Output("metric-peak", "children"),
    Output("hydrograph-plot", "figure"),
    Output("assumption-plot", "figure"),
    Output("workflow-plot", "figure"),
    Output("summary-table", "data"),
    Input("scenario-dropdown", "value"),
    Input("lag-ratio-slider", "value"),
    Input("peaking-factor-slider", "value"),
)
def update_outputs(scenario_name, lag_ratio, peaking_factor):
    base = SCENARIOS.get(scenario_name, SCENARIOS["Training Basin A - moderate response"])
    scenario = Scenario(
        name=base.name,
        drainage_area_ac=base.drainage_area_ac,
        runoff_depth_in=base.runoff_depth_in,
        tc_hr=base.tc_hr,
        lag_ratio=safe_float(lag_ratio, base.lag_ratio),
        peaking_factor=safe_float(peaking_factor, base.peaking_factor),
    )

    result = compute_hydrographs(scenario)
    summary = summarize_results(scenario, result)
    summary["Value"] = summary["Value"].map(lambda x: round(float(x), 3) if isinstance(x, (float, int, np.floating, np.integer)) else x)

    status = html.Div(
        [
            html.H3("Scenario loaded", style={"marginTop": "0", "color": FNI_BLUE}),
            html.P(f"{scenario.name}: {scenario.drainage_area_ac:,.0f} acres, {scenario.runoff_depth_in:.2f} inches of direct runoff, Tc = {scenario.tc_hr:.2f} hr."),
            html.P("The exercise isolates the transform assumption: lag time is being estimated as a fraction of Tc."),
        ]
    )

    return (
        status,
        build_metric_card("Match Score", f"{result.score:.0f} / 100", "Higher means closer to target"),
        build_metric_card("Runoff Volume", f"{result.direct_runoff_acft:,.1f} ac-ft", "Fixed after losses"),
        build_metric_card("Lag Time", f"{result.modeled_lag_hr:.2f} hr", f"{scenario.lag_ratio:.2f} x Tc"),
        build_metric_card("Modeled Peak", f"{result.modeled_peak_cfs:,.0f} cfs", f"target {result.target_peak_cfs:,.0f} cfs"),
        make_hydrograph_figure(result),
        make_assumption_figure(scenario, result),
        make_workflow_figure(),
        summary.to_dict("records"),
    )


# -----------------------------
# Entry point
# -----------------------------

if __name__ == "__main__":
    app.run(debug=True)
