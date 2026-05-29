"""
Alternatives Analysis Explorer

Learning objective:
Teach that stormwater alternatives should be evaluated by problem type, scenario range,
incremental benefit, incremental cost, and practical constructability rather than by a
single black-and-white design storm answer.

Run:
    python AlternativesAnalysisTeacherv1.py

Dependencies:
    dash pandas numpy plotly
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html, dash_table


# -----------------------------
# Constants and styles
# -----------------------------

FNI_BLUE = "#015D91"
FNI_GREEN = "#A9C945"
FNI_NAVY = "#093D5E"
FNI_YELLOW = "#DEB326"
FNI_ORANGE = "#E05126"
FNI_TURQUOISE = "#5BC1CF"
FNI_NEUTRAL_BLUE = "#93AFB4"
FNI_DARK_GRAY = "#4D4D4F"
FNI_GRAY = "#B1B1B1"

DESIGN_STORMS = np.array([2, 5, 10, 25, 50, 100], dtype=float)
DESIGN_STORM_LABELS = ["2-yr", "5-yr", "10-yr", "25-yr", "50-yr", "100-yr"]
HOURS_TO_SECONDS = 3600.0
CFS_HOUR_TO_ACFT = HOURS_TO_SECONDS / 43560.0

CARD_STYLE = {
    "backgroundColor": "white",
    "border": "1px solid #d9e2e8",
    "borderRadius": "16px",
    "padding": "16px",
    "boxShadow": "0 4px 12px rgba(9, 61, 94, 0.08)",
}

METRIC_CARD_STYLE = {
    **CARD_STYLE,
    "minHeight": "112px",
}

CONTROL_STYLE = {
    "marginBottom": "20px",
}

SMALL_TEXT = {
    "fontSize": "13px",
    "color": FNI_DARK_GRAY,
}


# -----------------------------
# Data objects
# -----------------------------

@dataclass
class AlternativeResult:
    name: str
    kind: str
    design_event_yr: float
    capacity_cfs: float
    storage_acft: float
    annualized_benefit_units: float
    benefit_percent: float
    cost_million: float
    value_index: float
    practicality_score: float
    remaining_structures_100yr: float
    remaining_lane_miles_100yr: float
    note: str


# -----------------------------
# Helper utilities
# -----------------------------

def storm_index(return_period: float) -> int:
    matches = np.where(DESIGN_STORMS == float(return_period))[0]
    if len(matches) == 0:
        raise ValueError(f"Unsupported design storm: {return_period}")
    return int(matches[0])


def format_money(value_million: float) -> str:
    return f"${value_million:,.2f}M"


def make_empty_figure(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        title=title,
        template="plotly_white",
        margin={"l": 50, "r": 20, "t": 60, "b": 50},
    )
    return fig


# -----------------------------
# Engineering logic
# -----------------------------

def make_peak_flow_series(q_100yr_cfs: float, exponent: float = 0.45) -> pd.DataFrame:
    """Synthetic peak flow frequency curve anchored to the 100-year peak."""
    q = q_100yr_cfs * (DESIGN_STORMS / 100.0) ** exponent
    return pd.DataFrame({"Storm": DESIGN_STORM_LABELS, "Return Period": DESIGN_STORMS, "Peak Flow (cfs)": q})


def make_existing_impacts(
    peak_df: pd.DataFrame,
    existing_capacity_cfs: float,
    max_structures: float,
    max_lane_miles: float,
) -> pd.DataFrame:
    """Estimate problem symptoms from exceedance above existing capacity."""
    exceedance = np.maximum(peak_df["Peak Flow (cfs)"].to_numpy() / existing_capacity_cfs - 1.0, 0.0)
    severity = 1.0 - np.exp(-1.65 * exceedance)
    return pd.DataFrame(
        {
            "Storm": peak_df["Storm"],
            "Return Period": peak_df["Return Period"],
            "Peak Flow (cfs)": peak_df["Peak Flow (cfs)"],
            "Flooded Structures": max_structures * severity,
            "Flooded Lane-Miles": max_lane_miles * severity,
            "Severity Index": severity,
        }
    )


def channel_cost_million(
    design_capacity_cfs: float,
    existing_capacity_cfs: float,
    freeboard_factor: float,
    unit_cost_per_cfs_million: float,
    cost_exponent: float,
) -> float:
    """Conceptual incremental cost for increasing channel/culvert conveyance."""
    required_with_freeboard = design_capacity_cfs * freeboard_factor
    added_capacity = max(required_with_freeboard - existing_capacity_cfs, 0.0)
    normalized_added = added_capacity / 100.0
    return unit_cost_per_cfs_million * 100.0 * (normalized_added ** cost_exponent)


def compute_channel_remaining_impacts(impact_df: pd.DataFrame, design_capacity_cfs: float) -> Tuple[np.ndarray, np.ndarray]:
    """Remaining symptoms after a conveyance alternative.

    The curve intentionally allows partial benefit above the design capacity. This supports
    teaching that a 50-year-sized channel can still deliver most of the benefit of a
    100-year-sized channel when the avoided impacts are concentrated in smaller storms.
    """
    peak = impact_df["Peak Flow (cfs)"].to_numpy()
    original_structures = impact_df["Flooded Structures"].to_numpy()
    original_lanes = impact_df["Flooded Lane-Miles"].to_numpy()

    exceedance_after = np.maximum(peak / design_capacity_cfs - 1.0, 0.0)
    severity_after = 1.0 - np.exp(-1.65 * exceedance_after)
    severity_before = np.maximum(impact_df["Severity Index"].to_numpy(), 1e-9)
    fraction_remaining = np.clip(severity_after / severity_before, 0.0, 1.0)

    return original_structures * fraction_remaining, original_lanes * fraction_remaining


def recurrence_weights(return_periods: np.ndarray) -> np.ndarray:
    """Simple frequency weights based on approximate annual exceedance probability differences."""
    aep = 1.0 / return_periods
    weights = aep / aep.sum()
    return weights


def benefit_units(structures_removed: np.ndarray, lanes_removed: np.ndarray, return_periods: np.ndarray) -> float:
    weights = recurrence_weights(return_periods)
    structure_weight = 1.0
    lane_mile_weight = 12.0
    return float(np.sum(weights * (structure_weight * structures_removed + lane_mile_weight * lanes_removed)))


def synthetic_hydrograph(return_period: float, peak_cfs: float, duration_hr: float = 18.0) -> pd.DataFrame:
    """Create a smooth teaching hydrograph for volume sizing."""
    time_hr = np.linspace(0.0, duration_hr, 181)
    center = duration_hr * 0.42
    width = duration_hr * 0.16
    rising = np.exp(-0.5 * ((time_hr - center) / width) ** 2)
    recession = np.exp(-0.5 * ((time_hr - (center + duration_hr * 0.14)) / (width * 1.35)) ** 2)
    shape = 0.62 * rising + 0.38 * recession
    shape = shape / shape.max()
    return pd.DataFrame({"Time (hr)": time_hr, "Inflow (cfs)": peak_cfs * shape})


def required_storage_for_target(hydro_df: pd.DataFrame, target_outflow_cfs: float) -> Tuple[pd.DataFrame, float, float]:
    """Estimate storage needed to cap outflow at a target rate using cumulative excess volume."""
    time_hr = hydro_df["Time (hr)"].to_numpy()
    inflow = hydro_df["Inflow (cfs)"].to_numpy()
    outflow = np.minimum(inflow, target_outflow_cfs)
    dt_hr = np.diff(time_hr, prepend=time_hr[0])
    excess_acft = np.maximum(inflow - outflow, 0.0) * dt_hr * CFS_HOUR_TO_ACFT
    storage = np.cumsum(excess_acft)
    # Drawdown after peak is simplified by subtracting available capacity after inflow drops below target.
    recovery_acft = np.maximum(target_outflow_cfs - inflow, 0.0) * dt_hr * CFS_HOUR_TO_ACFT
    storage = np.maximum.accumulate(storage) - np.cumsum(recovery_acft)
    storage = np.maximum(storage, 0.0)
    required_storage = float(storage.max())
    # NumPy 2.0 removed np.trapz. np.trapezoid is the direct replacement.
    total_volume = float(np.trapezoid(inflow, time_hr) * CFS_HOUR_TO_ACFT)
    routed = hydro_df.copy()
    routed["Target Outflow (cfs)"] = outflow
    routed["Storage Needed (acre-ft)"] = storage
    return routed, required_storage, total_volume


def basin_footprint_acres(storage_acft: float, max_depth_ft: float, bottom_slope_percent: float) -> Tuple[float, float]:
    """Estimate land footprint and volume lost due to positive bottom slope.

    This intentionally uses a transparent teaching approximation. The average usable depth is
    reduced by a slope penalty, representing the volume lost when a basin bottom cannot be flat
    and must drain freely to the outlet.
    """
    slope_penalty_ft = max_depth_ft * min(bottom_slope_percent / 8.0, 0.55)
    average_usable_depth_ft = max(max_depth_ft - slope_penalty_ft, 0.5)
    footprint_acres = storage_acft / average_usable_depth_ft
    flat_bottom_footprint = storage_acft / max(max_depth_ft, 0.5)
    extra_footprint = max(footprint_acres - flat_bottom_footprint, 0.0)
    return float(footprint_acres), float(extra_footprint)


def practicality_score(cost_million: float, footprint_acres: float, footprint_limit_acres: float) -> float:
    cost_score = max(0.0, 100.0 - 5.0 * cost_million)
    footprint_score = 100.0 if footprint_acres <= footprint_limit_acres else max(0.0, 100.0 - 18.0 * (footprint_acres - footprint_limit_acres))
    return float(0.55 * cost_score + 0.45 * footprint_score)


def evaluate_alternatives(
    q_100yr_cfs: float,
    existing_capacity_event: float,
    max_structures: float,
    max_lane_miles: float,
    freeboard_factor: float,
    unit_channel_cost: float,
    channel_cost_exponent: float,
    detention_target_event: float,
    detention_event: float,
    basin_depth_ft: float,
    bottom_slope_percent: float,
    footprint_limit_acres: float,
    detention_unit_cost_million_per_acft: float,
) -> Dict[str, object]:
    peak_df = make_peak_flow_series(q_100yr_cfs)
    existing_capacity = float(peak_df.loc[storm_index(existing_capacity_event), "Peak Flow (cfs)"])
    impact_df = make_existing_impacts(peak_df, existing_capacity, max_structures, max_lane_miles)

    original_structures = impact_df["Flooded Structures"].to_numpy()
    original_lanes = impact_df["Flooded Lane-Miles"].to_numpy()
    return_periods = impact_df["Return Period"].to_numpy()
    max_possible_benefit = benefit_units(original_structures, original_lanes, return_periods)

    alternatives: List[AlternativeResult] = []
    alternatives.append(
        AlternativeResult(
            name="No Action",
            kind="Baseline",
            design_event_yr=0.0,
            capacity_cfs=existing_capacity,
            storage_acft=0.0,
            annualized_benefit_units=0.0,
            benefit_percent=0.0,
            cost_million=0.0,
            value_index=0.0,
            practicality_score=100.0,
            remaining_structures_100yr=float(original_structures[-1]),
            remaining_lane_miles_100yr=float(original_lanes[-1]),
            note="Documents the existing problem; does not reduce symptoms.",
        )
    )

    for event in [10.0, 25.0, 50.0, 100.0]:
        design_capacity = float(peak_df.loc[storm_index(event), "Peak Flow (cfs)"])
        remaining_structures, remaining_lanes = compute_channel_remaining_impacts(impact_df, design_capacity)
        removed_structures = original_structures - remaining_structures
        removed_lanes = original_lanes - remaining_lanes
        benefit = benefit_units(removed_structures, removed_lanes, return_periods)
        cost = channel_cost_million(design_capacity, existing_capacity, freeboard_factor, unit_channel_cost, channel_cost_exponent)
        benefit_pct = 100.0 * benefit / max(max_possible_benefit, 1e-9)
        value = benefit_pct / max(cost, 0.01)
        note = "Strong incremental value" if event < 100 and benefit_pct >= 80 else "Full design-event capacity, but higher marginal cost"
        alternatives.append(
            AlternativeResult(
                name=f"{int(event)}-yr Conveyance",
                kind="Conveyance",
                design_event_yr=event,
                capacity_cfs=design_capacity * freeboard_factor,
                storage_acft=0.0,
                annualized_benefit_units=benefit,
                benefit_percent=benefit_pct,
                cost_million=cost,
                value_index=value,
                practicality_score=practicality_score(cost, 0.0, footprint_limit_acres),
                remaining_structures_100yr=float(remaining_structures[-1]),
                remaining_lane_miles_100yr=float(remaining_lanes[-1]),
                note=note,
            )
        )

    # Detention alternative: target outflow equals the selected lower event peak.
    detention_peak = float(peak_df.loc[storm_index(detention_event), "Peak Flow (cfs)"])
    target_outflow = float(peak_df.loc[storm_index(detention_target_event), "Peak Flow (cfs)"])
    hydro_df = synthetic_hydrograph(detention_event, detention_peak)
    routed_df, required_storage, total_volume = required_storage_for_target(hydro_df, target_outflow)
    footprint, extra_footprint = basin_footprint_acres(required_storage, basin_depth_ft, bottom_slope_percent)
    detention_cost = required_storage * detention_unit_cost_million_per_acft + 0.35 * footprint

    detention_remaining_structures = original_structures.copy()
    detention_remaining_lanes = original_lanes.copy()
    detention_factor = np.ones_like(return_periods, dtype=float)
    event_idx = storm_index(detention_event)
    target_idx = storm_index(detention_target_event)
    detention_factor[target_idx : event_idx + 1] = 0.22
    detention_factor[event_idx + 1 :] = 0.55
    detention_remaining_structures *= detention_factor
    detention_remaining_lanes *= detention_factor
    detention_benefit = benefit_units(original_structures - detention_remaining_structures, original_lanes - detention_remaining_lanes, return_periods)
    detention_benefit_pct = 100.0 * detention_benefit / max(max_possible_benefit, 1e-9)
    alternatives.append(
        AlternativeResult(
            name=f"Detain {int(detention_event)}-yr to {int(detention_target_event)}-yr",
            kind="Storage",
            design_event_yr=detention_event,
            capacity_cfs=target_outflow,
            storage_acft=required_storage,
            annualized_benefit_units=detention_benefit,
            benefit_percent=detention_benefit_pct,
            cost_million=detention_cost,
            value_index=detention_benefit_pct / max(detention_cost, 0.01),
            practicality_score=practicality_score(detention_cost, footprint, footprint_limit_acres),
            remaining_structures_100yr=float(detention_remaining_structures[-1]),
            remaining_lane_miles_100yr=float(detention_remaining_lanes[-1]),
            note="Useful when downstream conveyance controls the problem; footprint may govern feasibility.",
        )
    )

    alt_df = pd.DataFrame([a.__dict__ for a in alternatives])
    alt_df["rank"] = alt_df["value_index"].rank(method="min", ascending=False).astype(int)

    return {
        "peak_df": peak_df,
        "impact_df": impact_df,
        "alternatives": alt_df,
        "hydrograph": routed_df,
        "required_storage": required_storage,
        "total_hydrograph_volume": total_volume,
        "basin_footprint": footprint,
        "extra_footprint": extra_footprint,
        "existing_capacity": existing_capacity,
        "max_possible_benefit": max_possible_benefit,
    }


# -----------------------------
# Summary metrics
# -----------------------------

def build_summary_cards(model: Dict[str, object]) -> Tuple[html.Div, html.Div, html.Div, html.Div]:
    alt_df = model["alternatives"].copy()
    candidate_df = alt_df[alt_df["name"] != "No Action"].sort_values("value_index", ascending=False)
    best = candidate_df.iloc[0]
    storage_alt = alt_df[alt_df["kind"] == "Storage"].iloc[0]

    return (
        metric_card("Existing Capacity", f"{model['existing_capacity']:,.0f} cfs", "Capacity where symptoms begin"),
        metric_card("Best Value Option", str(best["name"]), f"{best['benefit_percent']:.0f}% benefit at {format_money(best['cost_million'])}"),
        metric_card("Detention Volume", f"{model['required_storage']:,.1f} ac-ft", f"Footprint about {model['basin_footprint']:.1f} acres"),
        metric_card("Practicality Check", f"{storage_alt['practicality_score']:.0f}/100", "Storage practicality score"),
    )


def metric_card(title: str, value: str, subtitle: str) -> html.Div:
    return html.Div(
        [
            html.Div(title, style={"fontSize": "14px", "fontWeight": "bold", "color": FNI_DARK_GRAY, "marginBottom": "8px"}),
            html.Div(value, style={"fontSize": "24px", "fontWeight": "bold", "color": FNI_BLUE, "marginBottom": "6px"}),
            html.Div(subtitle, style={"fontSize": "13px", "color": FNI_DARK_GRAY}),
        ],
    )


def make_alt_table(model: Dict[str, object]) -> List[Dict[str, object]]:
    df = model["alternatives"].copy()
    df = df[[
        "name",
        "kind",
        "benefit_percent",
        "cost_million",
        "value_index",
        "practicality_score",
        "storage_acft",
        "remaining_structures_100yr",
        "remaining_lane_miles_100yr",
        "note",
    ]]
    df.columns = [
        "Alternative",
        "Type",
        "Benefit (%)",
        "Cost ($M)",
        "Value Index",
        "Practicality",
        "Storage (ac-ft)",
        "Remaining 100-yr Structures",
        "Remaining 100-yr Lane-Miles",
        "Interpretation",
    ]
    for col in ["Benefit (%)", "Cost ($M)", "Value Index", "Practicality", "Storage (ac-ft)", "Remaining 100-yr Structures", "Remaining 100-yr Lane-Miles"]:
        df[col] = df[col].astype(float).round(2)
    return df.to_dict("records")


# -----------------------------
# Plotting
# -----------------------------

def make_problem_identification_figure(model: Dict[str, object]) -> go.Figure:
    df = model["impact_df"]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["Storm"], y=df["Flooded Structures"], name="Flooded Structures", marker_color=FNI_BLUE))
    fig.add_trace(go.Scatter(x=df["Storm"], y=df["Flooded Lane-Miles"], name="Flooded Lane-Miles", yaxis="y2", mode="lines+markers", line={"color": FNI_GREEN, "width": 3}))
    fig.update_layout(
        title="Problem Identification Across Design Storms",
        xaxis_title="Design storm",
        yaxis_title="Flooded structures",
        yaxis2={"title": "Flooded lane-miles", "overlaying": "y", "side": "right"},
        template="plotly_white",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        margin={"l": 55, "r": 65, "t": 70, "b": 50},
    )
    return fig


def make_benefit_cost_figure(model: Dict[str, object]) -> go.Figure:
    df = model["alternatives"].copy()
    df = df[df["name"] != "No Action"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["cost_million"],
        y=df["benefit_percent"],
        mode="markers+text",
        text=df["name"],
        textposition="top center",
        marker={
            "size": np.clip(df["practicality_score"] / 3.0 + 12, 12, 42),
            "color": df["benefit_percent"],
            "colorscale": [[0, FNI_NEUTRAL_BLUE], [0.65, FNI_BLUE], [1, FNI_GREEN]],
            "showscale": True,
            "colorbar": {"title": "Benefit %"},
            "line": {"color": FNI_NAVY, "width": 1},
        },
        hovertemplate="<b>%{text}</b><br>Cost: $%{x:.2f}M<br>Benefit: %{y:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        title="Incremental Benefit vs. Incremental Cost",
        xaxis_title="Conceptual cost ($M)",
        yaxis_title="Share of avoidable weighted impact removed (%)",
        template="plotly_white",
        margin={"l": 60, "r": 30, "t": 70, "b": 55},
    )
    return fig


def make_channel_tier_figure(model: Dict[str, object]) -> go.Figure:
    df = model["alternatives"].copy()
    df = df[df["kind"] == "Conveyance"]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["name"], y=df["benefit_percent"], name="Benefit", marker_color=FNI_BLUE))
    fig.add_trace(go.Scatter(x=df["name"], y=df["cost_million"], name="Cost", yaxis="y2", mode="lines+markers", line={"color": FNI_ORANGE, "width": 3}))
    fig.update_layout(
        title="Why to Test Multiple Conveyance Tiers",
        xaxis_title="Alternative",
        yaxis_title="Benefit (%)",
        yaxis2={"title": "Cost ($M)", "overlaying": "y", "side": "right"},
        template="plotly_white",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        margin={"l": 55, "r": 65, "t": 70, "b": 70},
    )
    return fig


def make_storage_figure(model: Dict[str, object]) -> go.Figure:
    df = model["hydrograph"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["Time (hr)"], y=df["Inflow (cfs)"], mode="lines", name="Inflow Hydrograph", line={"color": FNI_BLUE, "width": 3}))
    fig.add_trace(go.Scatter(x=df["Time (hr)"], y=df["Target Outflow (cfs)"], mode="lines", name="Acceptable Outflow Target", line={"color": FNI_NAVY, "width": 3, "dash": "dash"}))
    fig.add_trace(go.Scatter(x=df["Time (hr)"], y=df["Storage Needed (acre-ft)"], mode="lines", name="Cumulative Storage Need", yaxis="y2", line={"color": FNI_GREEN, "width": 3}))
    fig.update_layout(
        title="Storage Volume from Hydrograph Analysis",
        xaxis_title="Time (hr)",
        yaxis_title="Flow (cfs)",
        yaxis2={"title": "Storage (acre-ft)", "overlaying": "y", "side": "right"},
        template="plotly_white",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        margin={"l": 55, "r": 70, "t": 70, "b": 50},
    )
    return fig


# -----------------------------
# Sample data for display
# -----------------------------

sample_problem_data = pd.DataFrame(
    {
        "Storm": DESIGN_STORM_LABELS,
        "What to map/count": [
            "Nuisance ponding locations",
            "First conveyance failures",
            "Recurring street flooding",
            "Structure access issues",
            "Broader structural flooding",
            "Design-level residual risk",
        ],
        "Typical metric": [
            "complaints / low points",
            "culvert or pipe exceedance",
            "lane-miles flooded",
            "access routes blocked",
            "flooded structure count",
            "remaining damages / risk",
        ],
    }
)


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
            style={"maxWidth": "1500px", "margin": "0 auto"},
            children=[
                html.H1("Alternatives Analysis Explorer", style={"marginBottom": "8px", "color": FNI_BLUE}),
                html.P(
                    "This teaching app helps trainees move from symptoms to problem type, then compare conveyance and storage alternatives by benefit, cost, and practicality. It is intentionally conceptual: the point is to teach the evaluation framework before detailed design.",
                    style={"marginBottom": "20px", "maxWidth": "1120px"},
                ),
                html.Div(
                    style={"display": "grid", "gridTemplateColumns": "360px 1fr", "gap": "20px", "alignItems": "start"},
                    children=[
                        html.Div(
                            style=CARD_STYLE,
                            children=[
                                html.H3("Inputs", style={"marginTop": "0", "color": FNI_BLUE}),
                                html.Div(
                                    style=CONTROL_STYLE,
                                    children=[
                                        html.Label("Problem frame", style={"fontWeight": "bold"}),
                                        dcc.Dropdown(
                                            id="problem-frame",
                                            value="mixed",
                                            clearable=False,
                                            options=[
                                                {"label": "Mixed: capacity and storage", "value": "mixed"},
                                                {"label": "Primarily conveyance capacity", "value": "capacity"},
                                                {"label": "Primarily storage volume", "value": "storage"},
                                            ],
                                        ),
                                        html.Div("Every problem is framed as either not enough capacity to move water away, not enough volume to store water, or both.", style=SMALL_TEXT),
                                    ],
                                ),
                                html.Div(
                                    style=CONTROL_STYLE,
                                    children=[
                                        html.Label("100-year peak flow used for scenario set (cfs)", style={"fontWeight": "bold"}),
                                        dcc.Slider(id="q100", min=400, max=4000, step=100, value=1800, marks={400: "400", 1800: "1800", 4000: "4000"}, tooltip={"placement": "bottom", "always_visible": True}),
                                    ],
                                ),
                                html.Div(
                                    style=CONTROL_STYLE,
                                    children=[
                                        html.Label("Existing downstream capacity first fails near", style={"fontWeight": "bold"}),
                                        dcc.Slider(id="existing-event", min=0, max=5, step=1, value=1, marks={i: label for i, label in enumerate(DESIGN_STORM_LABELS)}, tooltip={"placement": "bottom", "always_visible": False}),
                                    ],
                                ),
                                html.Div(
                                    style=CONTROL_STYLE,
                                    children=[
                                        html.Label("Maximum 100-year flooded structures", style={"fontWeight": "bold"}),
                                        dcc.Slider(id="max-structures", min=5, max=250, step=5, value=80, marks={5: "5", 80: "80", 250: "250"}, tooltip={"placement": "bottom", "always_visible": True}),
                                    ],
                                ),
                                html.Div(
                                    style=CONTROL_STYLE,
                                    children=[
                                        html.Label("Maximum 100-year flooded lane-miles", style={"fontWeight": "bold"}),
                                        dcc.Slider(id="max-lanes", min=0.5, max=20.0, step=0.5, value=6.0, marks={0.5: "0.5", 6: "6", 20: "20"}, tooltip={"placement": "bottom", "always_visible": True}),
                                    ],
                                ),
                                html.H4("Conveyance assumptions", style={"color": FNI_BLUE}),
                                html.Div(
                                    style=CONTROL_STYLE,
                                    children=[
                                        html.Label("Freeboard / design margin factor", style={"fontWeight": "bold"}),
                                        dcc.Slider(id="freeboard", min=1.00, max=1.50, step=0.05, value=1.20, marks={1.0: "1.0", 1.2: "1.2", 1.5: "1.5"}, tooltip={"placement": "bottom", "always_visible": True}),
                                    ],
                                ),
                                html.Div(
                                    style=CONTROL_STYLE,
                                    children=[
                                        html.Label("Channel cost nonlinearity", style={"fontWeight": "bold"}),
                                        dcc.Slider(id="channel-exp", min=1.0, max=2.5, step=0.1, value=1.55, marks={1.0: "linear", 1.5: "1.5", 2.5: "steep"}, tooltip={"placement": "bottom", "always_visible": True}),
                                    ],
                                ),
                                html.H4("Storage assumptions", style={"color": FNI_BLUE}),
                                html.Div(
                                    style=CONTROL_STYLE,
                                    children=[
                                        html.Label("Detention event", style={"fontWeight": "bold"}),
                                        dcc.Dropdown(id="detention-event", value=100, clearable=False, options=[{"label": label, "value": int(rp)} for label, rp in zip(DESIGN_STORM_LABELS[2:], DESIGN_STORMS[2:])]),
                                    ],
                                ),
                                html.Div(
                                    style=CONTROL_STYLE,
                                    children=[
                                        html.Label("Acceptable release target", style={"fontWeight": "bold"}),
                                        dcc.Dropdown(id="target-event", value=10, clearable=False, options=[{"label": label, "value": int(rp)} for label, rp in zip(DESIGN_STORM_LABELS[:5], DESIGN_STORMS[:5])]),
                                    ],
                                ),
                                html.Div(
                                    style=CONTROL_STYLE,
                                    children=[
                                        html.Label("Max basin depth (ft)", style={"fontWeight": "bold"}),
                                        dcc.Slider(id="basin-depth", min=2.0, max=12.0, step=0.5, value=5.0, marks={2: "2", 5: "5", 12: "12"}, tooltip={"placement": "bottom", "always_visible": True}),
                                    ],
                                ),
                                html.Div(
                                    style=CONTROL_STYLE,
                                    children=[
                                        html.Label("Positive bottom slope for drainage (%)", style={"fontWeight": "bold"}),
                                        dcc.Slider(id="bottom-slope", min=0.0, max=4.0, step=0.25, value=1.0, marks={0: "flat", 1: "1", 4: "4"}, tooltip={"placement": "bottom", "always_visible": True}),
                                        html.Div("A sloped bottom drains better but reduces low-end usable storage, increasing footprint.", style=SMALL_TEXT),
                                    ],
                                ),
                                html.Div(
                                    style=CONTROL_STYLE,
                                    children=[
                                        html.Label("Practical footprint limit (acres)", style={"fontWeight": "bold"}),
                                        dcc.Slider(id="footprint-limit", min=2, max=80, step=1, value=20, marks={2: "2", 20: "20", 80: "80"}, tooltip={"placement": "bottom", "always_visible": True}),
                                    ],
                                ),
                            ],
                        ),
                        html.Div(
                            style={"display": "grid", "gap": "20px"},
                            children=[
                                html.Div(id="status-message", style=CARD_STYLE),
                                html.Div(
                                    style={"display": "grid", "gridTemplateColumns": "repeat(4, minmax(0, 1fr))", "gap": "16px"},
                                    children=[
                                        html.Div(id="metric-1", style=METRIC_CARD_STYLE),
                                        html.Div(id="metric-2", style=METRIC_CARD_STYLE),
                                        html.Div(id="metric-3", style=METRIC_CARD_STYLE),
                                        html.Div(id="metric-4", style=METRIC_CARD_STYLE),
                                    ],
                                ),
                                html.Div(
                                    style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "20px"},
                                    children=[
                                        html.Div(dcc.Graph(id="problem-figure"), style=CARD_STYLE),
                                        html.Div(dcc.Graph(id="benefit-cost-figure"), style=CARD_STYLE),
                                    ],
                                ),
                                html.Div(
                                    style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "20px"},
                                    children=[
                                        html.Div(dcc.Graph(id="channel-tier-figure"), style=CARD_STYLE),
                                        html.Div(dcc.Graph(id="storage-figure"), style=CARD_STYLE),
                                    ],
                                ),
                                html.Div(
                                    style=CARD_STYLE,
                                    children=[
                                        html.H3("Alternatives Matrix", style={"marginTop": "0", "color": FNI_BLUE}),
                                        dash_table.DataTable(
                                            id="alt-table",
                                            columns=[
                                                {"name": "Alternative", "id": "Alternative"},
                                                {"name": "Type", "id": "Type"},
                                                {"name": "Benefit (%)", "id": "Benefit (%)", "type": "numeric"},
                                                {"name": "Cost ($M)", "id": "Cost ($M)", "type": "numeric"},
                                                {"name": "Value Index", "id": "Value Index", "type": "numeric"},
                                                {"name": "Practicality", "id": "Practicality", "type": "numeric"},
                                                {"name": "Storage (ac-ft)", "id": "Storage (ac-ft)", "type": "numeric"},
                                                {"name": "Remaining 100-yr Structures", "id": "Remaining 100-yr Structures", "type": "numeric"},
                                                {"name": "Remaining 100-yr Lane-Miles", "id": "Remaining 100-yr Lane-Miles", "type": "numeric"},
                                                {"name": "Interpretation", "id": "Interpretation"},
                                            ],
                                            data=[],
                                            style_table={"overflowX": "auto"},
                                            style_header={"backgroundColor": FNI_BLUE, "color": "white", "fontWeight": "bold"},
                                            style_cell={"textAlign": "left", "padding": "10px", "border": "1px solid #e3eaee", "whiteSpace": "normal", "height": "auto"},
                                            style_data_conditional=[
                                                {"if": {"filter_query": "{Type} = 'Storage'"}, "backgroundColor": "#f7faee"},
                                                {"if": {"filter_query": "{Type} = 'Conveyance'"}, "backgroundColor": "#f7fbfd"},
                                            ],
                                        ),
                                    ],
                                ),
                                html.Div(
                                    style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "20px"},
                                    children=[
                                        html.Details(
                                            style=CARD_STYLE,
                                            open=True,
                                            children=[
                                                html.Summary("Teaching sequence", style={"cursor": "pointer", "fontWeight": "bold", "color": FNI_BLUE}),
                                                html.Ol(
                                                    [
                                                        html.Li("Start with visible symptoms: flooded structures, roadway lane-miles, blocked access, and observed high-water locations."),
                                                        html.Li("Translate symptoms into a problem type: not enough capacity, not enough volume, or a mixed constraint."),
                                                        html.Li("Check the full storm range. A single design storm can hide the controlling insight."),
                                                        html.Li("Test multiple conveyance sizes instead of jumping straight to the 100-year channel."),
                                                        html.Li("Size storage from hydrograph volume and a release or water-surface target."),
                                                        html.Li("Close with practicality: cost, footprint, constructability, drainage, maintenance, and right-of-way."),
                                                    ],
                                                    style={"paddingLeft": "22px"},
                                                ),
                                            ],
                                        ),
                                        html.Details(
                                            style=CARD_STYLE,
                                            children=[
                                                html.Summary("Example problem-identification table", style={"cursor": "pointer", "fontWeight": "bold", "color": FNI_BLUE}),
                                                dash_table.DataTable(
                                                    columns=[{"name": c, "id": c} for c in sample_problem_data.columns],
                                                    data=sample_problem_data.to_dict("records"),
                                                    style_table={"overflowX": "auto", "marginTop": "12px"},
                                                    style_header={"backgroundColor": "#e9f3f8", "fontWeight": "bold"},
                                                    style_cell={"textAlign": "left", "padding": "8px", "whiteSpace": "normal", "height": "auto"},
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                                html.Details(
                                    style=CARD_STYLE,
                                    children=[
                                        html.Summary("Method notes and limitations", style={"cursor": "pointer", "fontWeight": "bold", "color": FNI_BLUE}),
                                        html.Div(
                                            style={"marginTop": "12px"},
                                            children=[
                                                html.P("This is a screening-level teaching tool. It does not replace H&H modeling, roadway overtopping analysis, hydraulic grade line review, or design-level cost estimating."),
                                                html.P("The conveyance alternatives use a conceptual peak-flow capacity curve and an intentionally nonlinear cost curve. The storage alternative uses a simplified hydrograph target-release calculation to estimate required volume."),
                                                html.P("The basin footprint calculation explicitly shows the training point that a positive-drainage basin bottom can reduce usable lower storage and increase the area needed to achieve the same volume."),
                                                html.P("Use tools such as FlowMaster or CulvertMaster for component conveyance checks, and use hydrograph-based methods for volume and detention evaluation."),
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
    Output("metric-1", "children"),
    Output("metric-2", "children"),
    Output("metric-3", "children"),
    Output("metric-4", "children"),
    Output("problem-figure", "figure"),
    Output("benefit-cost-figure", "figure"),
    Output("channel-tier-figure", "figure"),
    Output("storage-figure", "figure"),
    Output("alt-table", "data"),
    Input("problem-frame", "value"),
    Input("q100", "value"),
    Input("existing-event", "value"),
    Input("max-structures", "value"),
    Input("max-lanes", "value"),
    Input("freeboard", "value"),
    Input("channel-exp", "value"),
    Input("detention-event", "value"),
    Input("target-event", "value"),
    Input("basin-depth", "value"),
    Input("bottom-slope", "value"),
    Input("footprint-limit", "value"),
)
def update_outputs(
    problem_frame,
    q100,
    existing_event_index,
    max_structures,
    max_lanes,
    freeboard,
    channel_exp,
    detention_event,
    target_event,
    basin_depth,
    bottom_slope,
    footprint_limit,
):
    existing_event = DESIGN_STORMS[int(existing_event_index)]
    target_event = min(float(target_event), float(detention_event))

    try:
        model = evaluate_alternatives(
            q_100yr_cfs=float(q100),
            existing_capacity_event=float(existing_event),
            max_structures=float(max_structures),
            max_lane_miles=float(max_lanes),
            freeboard_factor=float(freeboard),
            unit_channel_cost=0.018,
            channel_cost_exponent=float(channel_exp),
            detention_target_event=float(target_event),
            detention_event=float(detention_event),
            basin_depth_ft=float(basin_depth),
            bottom_slope_percent=float(bottom_slope),
            footprint_limit_acres=float(footprint_limit),
            detention_unit_cost_million_per_acft=0.12,
        )

        frame_text = {
            "mixed": "Mixed problem: evaluate both capacity and storage. Do not assume one solution type until the storm-range pattern is visible.",
            "capacity": "Capacity problem: check whether downstream conveyance already fails in a smaller event before sizing a very large design-event channel.",
            "storage": "Storage problem: use hydrograph volume and an acceptable flow or water-surface target; do not treat detention as an afterthought.",
        }.get(problem_frame, "Mixed problem: evaluate both capacity and storage.")

        status = html.Div(
            [
                html.H3("Current interpretation", style={"marginTop": "0", "color": FNI_BLUE}),
                html.P(frame_text),
                html.P(
                    f"Existing capacity is approximated as the {int(existing_event)}-year peak. The app then tests the full design-storm range so the controlling insight is not hidden by one scenario."
                ),
            ]
        )

        cards = build_summary_cards(model)
        return (
            status,
            cards[0],
            cards[1],
            cards[2],
            cards[3],
            make_problem_identification_figure(model),
            make_benefit_cost_figure(model),
            make_channel_tier_figure(model),
            make_storage_figure(model),
            make_alt_table(model),
        )
    except Exception as exc:
        status = html.Div(
            [
                html.H3("Evaluation error", style={"marginTop": "0", "color": FNI_ORANGE}),
                html.P(str(exc)),
            ]
        )
        empty = make_empty_figure("No results")
        blank = metric_card("Result", "--", "Check input assumptions")
        return status, blank, blank, blank, blank, empty, empty, empty, empty, []


# -----------------------------
# Entry point
# -----------------------------

if __name__ == "__main__":
    app.run(debug=True)
