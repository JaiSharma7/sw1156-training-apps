"""
Muskingum-Cunge Reach Calibration Trainer

Learning objective:
Show why a single representative cross section can strongly control reach-routing results,
and how overbank geometry and roughness adjustments can be used to calibrate peak timing
and attenuation against a target hydrograph.

This is a teaching app, not a replacement for a detailed HEC-HMS or hydraulic model.
It uses a simplified variable-parameter Muskingum-Cunge-style routing calculation based on
Manning conveyance from an eight-point cross section.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dash_table, dcc, html

# -----------------------------
# Constants and brand colors
# -----------------------------

FNI_BLUE = "#015D91"
FNI_GREEN = "#A9C945"
FNI_NAVY = "#093D5E"
FNI_AQUA = "#45A6DD"
FNI_TURQUOISE = "#5BC1CF"
FNI_ORANGE = "#E05126"
FNI_YELLOW = "#DEB326"
DARK_GRAY = "#4D4D4F"
GRAY = "#B1B1B1"
NEUTRAL_BLUE = "#93AFB4"

FT3_PER_ACFT = 43560.0


# -----------------------------
# Data classes
# -----------------------------


@dataclass
class CrossSection:
    name: str
    station_ft: np.ndarray
    elevation_ft: np.ndarray
    left_overbank_station_ft: float
    right_overbank_station_ft: float
    bed_slope_ftft: float
    reach_length_ft: float
    description: str


@dataclass
class RatingTable:
    stage_ft: np.ndarray
    elevation_ft: np.ndarray
    area_sqft: np.ndarray
    top_width_ft: np.ndarray
    hydraulic_radius_ft: np.ndarray
    conveyance: np.ndarray
    discharge_cfs: np.ndarray
    storage_acft: np.ndarray


@dataclass
class RoutingResult:
    time_min: np.ndarray
    inflow_cfs: np.ndarray
    pure_lag_cfs: np.ndarray
    routed_cfs: np.ndarray
    stage_ft: np.ndarray
    storage_acft: np.ndarray
    k_hr: np.ndarray
    x: np.ndarray
    rating: RatingTable


# -----------------------------
# Helper utilities
# -----------------------------


def normalize_name(name: str) -> str:
    name = str(name).strip().lower()
    for ch in ["(", ")", "[", "]", "{", "}"]:
        name = name.replace(ch, " ")
    return name.replace("_", " ").split()[0] if name else name


def find_required_columns(df: pd.DataFrame, required: Tuple[str, ...]) -> Dict[str, str]:
    normalized = {col: normalize_name(col) for col in df.columns}
    mapping = {}
    for req in required:
        matches = [col for col, norm in normalized.items() if norm == req]
        if not matches:
            raise ValueError(f"Required column '{req}' was not found.")
        mapping[req] = matches[0]
    return mapping


def parse_uploaded_csv(contents: str | None, label: str) -> pd.DataFrame:
    if contents is None:
        raise ValueError(f"No file was uploaded for {label}.")
    _, content_string = contents.split(",", 1)
    decoded = base64.b64decode(content_string)
    return pd.read_csv(io.StringIO(decoded.decode("utf-8")))


def load_hydrograph_from_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = find_required_columns(df, ("time", "inflow"))
    out = df[[cols["time"], cols["inflow"]]].copy()
    out.columns = ["time", "inflow"]
    out["time"] = pd.to_numeric(out["time"], errors="coerce")
    out["inflow"] = pd.to_numeric(out["inflow"], errors="coerce")
    out = out.dropna().reset_index(drop=True)

    if len(out) < 3:
        raise ValueError("Hydrograph must contain at least three valid rows.")
    if np.any(out["inflow"].to_numpy() < 0):
        raise ValueError("Inflow values must be nonnegative.")

    dt = np.diff(out["time"].to_numpy(dtype=float))
    if np.any(dt <= 0):
        raise ValueError("Hydrograph time values must be strictly increasing.")
    if not np.allclose(dt, dt[0], rtol=0.0, atol=1e-9):
        raise ValueError("Hydrograph time step must be constant for this app.")
    return out


def peak_stats(time_min: np.ndarray, values: np.ndarray) -> Tuple[float, float]:
    idx = int(np.argmax(values))
    return float(values[idx]), float(time_min[idx])


def safe_divide(a: np.ndarray, b: np.ndarray, fill: float = 0.0) -> np.ndarray:
    out = np.full_like(a, fill, dtype=float)
    mask = np.abs(b) > 1e-12
    out[mask] = a[mask] / b[mask]
    return out


# -----------------------------
# Sample data
# -----------------------------


def make_sample_hydrograph() -> pd.DataFrame:
    time = np.arange(0, 13 * 60 + 5, 5, dtype=float)
    q_base = 35.0
    q_peak = 2250.0
    center = 330.0
    rise_sigma = 90.0
    fall_sigma = 155.0
    q = np.where(
        time <= center,
        q_base + (q_peak - q_base) * np.exp(-0.5 * ((time - center) / rise_sigma) ** 2),
        q_base + (q_peak - q_base) * np.exp(-0.5 * ((time - center) / fall_sigma) ** 2),
    )
    q[0] = q_base
    return pd.DataFrame({"Time (min)": time, "Inflow (cfs)": q})


SAMPLE_HYDRO = make_sample_hydrograph()


PREDEFINED_REACHES: Dict[str, CrossSection] = {
    "Incised Urban Channel": CrossSection(
        name="Incised Urban Channel",
        station_ft=np.array([0, 25, 50, 72, 90, 108, 132, 165], dtype=float),
        elevation_ft=np.array([110, 106, 102, 99, 96, 99, 103, 108], dtype=float),
        left_overbank_station_ft=60,
        right_overbank_station_ft=122,
        bed_slope_ftft=0.0018,
        reach_length_ft=2800,
        description="Deep main channel with narrow overbanks; timing is sensitive to selected bank stations and main-channel roughness.",
    ),
    "Wide Floodplain Reach": CrossSection(
        name="Wide Floodplain Reach",
        station_ft=np.array([0, 80, 170, 245, 300, 355, 445, 540], dtype=float),
        elevation_ft=np.array([105, 103, 101, 98, 96, 98, 101, 104], dtype=float),
        left_overbank_station_ft=215,
        right_overbank_station_ft=385,
        bed_slope_ftft=0.00065,
        reach_length_ft=5200,
        description="Broad overbanks and mild slope; attenuation is dominated by floodplain storage and roughness assumptions.",
    ),
    "Composite Natural Valley": CrossSection(
        name="Composite Natural Valley",
        station_ft=np.array([0, 55, 130, 210, 270, 335, 430, 500], dtype=float),
        elevation_ft=np.array([108, 105, 101, 98, 95, 98, 102, 107], dtype=float),
        left_overbank_station_ft=185,
        right_overbank_station_ft=365,
        bed_slope_ftft=0.0011,
        reach_length_ft=4100,
        description="Mixed channel and floodplain geometry; useful for showing why one cross section may not represent the full reach.",
    ),
}


# -----------------------------
# Geometry and hydraulics
# -----------------------------


def scaled_cross_section(
    xs: CrossSection, overbank_width_factor: float, overbank_elev_adjust_ft: float
) -> CrossSection:
    station = xs.station_ft.copy()
    elev = xs.elevation_ft.copy()
    lob = xs.left_overbank_station_ft
    rob = xs.right_overbank_station_ft

    center = 0.5 * (lob + rob)
    left_mask = station < lob
    right_mask = station > rob
    station[left_mask] = lob - (lob - station[left_mask]) * overbank_width_factor
    station[right_mask] = rob + (station[right_mask] - rob) * overbank_width_factor
    station = center + (station - center)

    elev[left_mask | right_mask] += overbank_elev_adjust_ft

    sort_idx = np.argsort(station)
    return CrossSection(
        name=xs.name,
        station_ft=station[sort_idx],
        elevation_ft=elev[sort_idx],
        left_overbank_station_ft=lob,
        right_overbank_station_ft=rob,
        bed_slope_ftft=xs.bed_slope_ftft,
        reach_length_ft=xs.reach_length_ft,
        description=xs.description,
    )


def wetted_properties_at_elevation(
    station_ft: np.ndarray,
    elevation_ft: np.ndarray,
    water_elev_ft: float,
    lob_ft: float,
    rob_ft: float,
    n_main: float,
    n_overbank: float,
) -> Tuple[float, float, float, float]:
    """Return total area, top width, hydraulic radius, and composite conveyance.

    The area calculation uses np.trapezoid explicitly. No deprecated np.trapz call is used.
    """
    min_elev = float(np.min(elevation_ft))
    if water_elev_ft <= min_elev:
        return 0.0, 0.0, 0.0, 0.0

    dense_station = np.linspace(float(station_ft.min()), float(station_ft.max()), 900)
    dense_ground = np.interp(dense_station, station_ft, elevation_ft)
    depth = np.maximum(water_elev_ft - dense_ground, 0.0)
    wet = depth > 1e-8

    if not np.any(wet):
        return 0.0, 0.0, 0.0, 0.0

    total_area = float(np.trapezoid(depth, dense_station))
    top_width = float(dense_station[wet].max() - dense_station[wet].min())

    conveyance_total = 0.0
    weighted_radius_area = 0.0
    total_sub_area = 0.0

    subsections = [
        (dense_station <= lob_ft, n_overbank),
        ((dense_station >= lob_ft) & (dense_station <= rob_ft), n_main),
        (dense_station >= rob_ft, n_overbank),
    ]

    for mask, mann_n in subsections:
        sub_depth = np.where(mask, depth, 0.0)
        sub_wet = sub_depth > 1e-8
        if not np.any(sub_wet):
            continue

        sub_station = dense_station[sub_wet]
        sub_depth_values = sub_depth[sub_wet]
        sub_ground = dense_ground[sub_wet]

        sub_area = float(np.trapezoid(sub_depth_values, sub_station))
        if sub_area <= 0.0:
            continue

        ground_dx = np.diff(sub_station)
        ground_dz = np.diff(sub_ground)
        perimeter = float(np.sum(np.sqrt(ground_dx**2 + ground_dz**2)))
        if perimeter <= 0.0:
            continue

        radius = sub_area / perimeter
        conveyance_total += (1.486 / mann_n) * sub_area * radius ** (2.0 / 3.0)
        weighted_radius_area += radius * sub_area
        total_sub_area += sub_area

    hydraulic_radius = weighted_radius_area / total_sub_area if total_sub_area > 0.0 else 0.0
    return total_area, top_width, hydraulic_radius, conveyance_total


def build_rating_table(
    xs: CrossSection,
    n_main: float,
    n_overbank: float,
    slope_factor: float,
    length_factor: float,
) -> RatingTable:
    min_elev = float(np.min(xs.elevation_ft))
    max_elev = float(np.max(xs.elevation_ft)) + 4.0
    water_elev = np.linspace(min_elev, max_elev, 90)

    slope = max(xs.bed_slope_ftft * slope_factor, 1e-6)
    length = max(xs.reach_length_ft * length_factor, 1.0)

    area = []
    width = []
    radius = []
    conveyance = []
    discharge = []
    storage = []

    for elev in water_elev:
        a, tw, r, k = wetted_properties_at_elevation(
            xs.station_ft,
            xs.elevation_ft,
            elev,
            xs.left_overbank_station_ft,
            xs.right_overbank_station_ft,
            n_main,
            n_overbank,
        )
        q = k * np.sqrt(slope)
        area.append(a)
        width.append(tw)
        radius.append(r)
        conveyance.append(k)
        discharge.append(q)
        storage.append(a * length / FT3_PER_ACFT)

    discharge_arr = np.maximum.accumulate(np.asarray(discharge, dtype=float))
    storage_arr = np.asarray(storage, dtype=float)
    stage_arr = water_elev - min_elev

    return RatingTable(
        stage_ft=stage_arr,
        elevation_ft=water_elev,
        area_sqft=np.asarray(area, dtype=float),
        top_width_ft=np.asarray(width, dtype=float),
        hydraulic_radius_ft=np.asarray(radius, dtype=float),
        conveyance=np.asarray(conveyance, dtype=float),
        discharge_cfs=discharge_arr,
        storage_acft=storage_arr,
    )


# -----------------------------
# Routing models
# -----------------------------


def lag_hydrograph(time_min: np.ndarray, inflow: np.ndarray, lag_min: float) -> np.ndarray:
    source_time = time_min - lag_min
    return np.interp(source_time, time_min, inflow, left=inflow[0], right=inflow[-1])


def route_variable_muskingum_cunge(
    time_min: np.ndarray,
    inflow_cfs: np.ndarray,
    rating: RatingTable,
    reach_length_ft: float,
    bed_slope_ftft: float,
    x_factor: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    dt_sec = float(time_min[1] - time_min[0]) * 60.0
    n = len(time_min)

    q_rating = rating.discharge_cfs
    positive = q_rating > 1e-6
    if np.count_nonzero(positive) < 4:
        raise ValueError("Cross section does not produce enough positive flow values for routing.")

    max_rating_q = float(np.max(q_rating))
    if np.max(inflow_cfs) > max_rating_q * 1.25:
        raise ValueError(
            "Peak inflow substantially exceeds the generated rating curve. "
            "Raise overbank width, raise slope, or choose a larger predefined reach."
        )

    routed = np.zeros(n, dtype=float)
    stage = np.zeros(n, dtype=float)
    storage = np.zeros(n, dtype=float)
    k_hr_series = np.zeros(n, dtype=float)
    x_series = np.zeros(n, dtype=float)

    routed[0] = min(float(inflow_cfs[0]), max_rating_q)

    for i in range(1, n):
        trial_q = max(0.5 * (inflow_cfs[i - 1] + inflow_cfs[i]), 1.0)
        trial_q = min(trial_q, max_rating_q)

        area_i = float(np.interp(trial_q, q_rating, rating.area_sqft))
        width_i = float(np.interp(trial_q, q_rating, rating.top_width_ft))

        velocity = trial_q / max(area_i, 1.0)
        wave_celerity = max(1.2 * velocity, 0.25)
        k_sec = max(reach_length_ft / wave_celerity, dt_sec * 0.55)

        # Simplified Cunge weighting. Higher diffusion denominator lowers X.
        # This keeps X in the stable Muskingum range while still exposing sensitivity.
        diffusion_ratio = trial_q / max(width_i * bed_slope_ftft * wave_celerity * reach_length_ft, 1.0)
        x_base = 0.5 * (1.0 - diffusion_ratio)
        x = float(np.clip(x_base * x_factor, 0.02, 0.49))

        denominator = k_sec * (1.0 - x) + 0.5 * dt_sec
        c0 = (-k_sec * x + 0.5 * dt_sec) / denominator
        c1 = (k_sec * x + 0.5 * dt_sec) / denominator
        c2 = (k_sec * (1.0 - x) - 0.5 * dt_sec) / denominator

        # If the simplified coefficients drift outside normal bounds, blend with a stable lag response.
        if min(c0, c1, c2) < -0.05 or max(c0, c1, c2) > 1.10:
            alpha = dt_sec / (k_sec + dt_sec)
            routed[i] = routed[i - 1] + alpha * (inflow_cfs[i] - routed[i - 1])
        else:
            routed[i] = c0 * inflow_cfs[i] + c1 * inflow_cfs[i - 1] + c2 * routed[i - 1]

        routed[i] = max(0.0, min(routed[i], max_rating_q))
        stage[i] = float(np.interp(routed[i], q_rating, rating.stage_ft))
        storage[i] = float(np.interp(routed[i], q_rating, rating.storage_acft))
        k_hr_series[i] = k_sec / 3600.0
        x_series[i] = x

    return routed, stage, storage, k_hr_series, x_series


def run_model(
    hydro_df: pd.DataFrame,
    reach_name: str,
    overbank_width_factor: float,
    overbank_elev_adjust_ft: float,
    n_main: float,
    n_overbank: float,
    slope_factor: float,
    length_factor: float,
    x_factor: float,
    pure_lag_min: float,
) -> RoutingResult:
    base_xs = PREDEFINED_REACHES[reach_name]
    xs = scaled_cross_section(base_xs, overbank_width_factor, overbank_elev_adjust_ft)
    rating = build_rating_table(xs, n_main, n_overbank, slope_factor, length_factor)

    time_min = hydro_df["time"].to_numpy(dtype=float)
    inflow = hydro_df["inflow"].to_numpy(dtype=float)

    routed, stage, storage, k_hr, x = route_variable_muskingum_cunge(
        time_min,
        inflow,
        rating,
        reach_length_ft=xs.reach_length_ft * length_factor,
        bed_slope_ftft=xs.bed_slope_ftft * slope_factor,
        x_factor=x_factor,
    )
    pure_lag = lag_hydrograph(time_min, inflow, pure_lag_min)

    return RoutingResult(
        time_min=time_min,
        inflow_cfs=inflow,
        pure_lag_cfs=pure_lag,
        routed_cfs=routed,
        stage_ft=stage,
        storage_acft=storage,
        k_hr=k_hr,
        x=x,
        rating=rating,
    )


# -----------------------------
# Summaries and plots
# -----------------------------


def summarize_results(result: RoutingResult, target_peak_cfs: float, target_peak_time_min: float) -> pd.DataFrame:
    inflow_peak, inflow_time = peak_stats(result.time_min, result.inflow_cfs)
    lag_peak, lag_time = peak_stats(result.time_min, result.pure_lag_cfs)
    routed_peak, routed_time = peak_stats(result.time_min, result.routed_cfs)

    volume_in = np.trapezoid(result.inflow_cfs, result.time_min * 60.0) / FT3_PER_ACFT
    volume_out = np.trapezoid(result.routed_cfs, result.time_min * 60.0) / FT3_PER_ACFT

    rows = [
        ["Inflow", inflow_peak, inflow_time, "--", "--"],
        ["Pure Lag", lag_peak, lag_time, lag_peak - target_peak_cfs, lag_time - target_peak_time_min],
        [
            "Muskingum-Cunge-style",
            routed_peak,
            routed_time,
            routed_peak - target_peak_cfs,
            routed_time - target_peak_time_min,
        ],
        ["Volume In (ac-ft)", volume_in, "--", "--", "--"],
        ["Volume Out (ac-ft)", volume_out, "--", volume_out - volume_in, "--"],
        [
            "Max Stage (ft)",
            float(np.max(result.stage_ft)),
            float(result.time_min[int(np.argmax(result.stage_ft))]),
            "--",
            "--",
        ],
    ]
    return pd.DataFrame(rows, columns=["Metric", "Value", "Time (min)", "Peak Error", "Timing Error (min)"])


def make_hydrograph_figure(result: RoutingResult, target_peak_cfs: float, target_peak_time_min: float) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=result.time_min, y=result.inflow_cfs, mode="lines", name="Inflow", line={"color": FNI_BLUE, "width": 3}
        )
    )
    fig.add_trace(
        go.Scatter(
            x=result.time_min,
            y=result.pure_lag_cfs,
            mode="lines",
            name="Pure Lag",
            line={"color": FNI_AQUA, "width": 3, "dash": "dash"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=result.time_min,
            y=result.routed_cfs,
            mode="lines",
            name="Muskingum-Cunge-style Routed",
            line={"color": FNI_GREEN, "width": 3},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[target_peak_time_min],
            y=[target_peak_cfs],
            mode="markers",
            name="Target Peak",
            marker={"color": FNI_ORANGE, "size": 13, "symbol": "x"},
        )
    )
    fig.update_layout(
        title="Hydrograph Timing and Attenuation",
        xaxis_title="Time (minutes)",
        yaxis_title="Flow (cfs)",
        template="plotly_white",
        legend_title_text="Series",
        margin={"l": 55, "r": 20, "t": 60, "b": 50},
    )
    return fig


def make_cross_section_figure(xs: CrossSection, rating: RatingTable, stage_to_show: float) -> go.Figure:
    min_elev = float(np.min(xs.elevation_ft))
    water_elev = min_elev + stage_to_show
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=xs.station_ft,
            y=xs.elevation_ft,
            mode="lines+markers",
            name="Ground",
            line={"color": FNI_NAVY, "width": 3},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[xs.station_ft.min(), xs.station_ft.max()],
            y=[water_elev, water_elev],
            mode="lines",
            name="Max Routed Water Surface",
            line={"color": FNI_AQUA, "width": 3, "dash": "dot"},
        )
    )
    fig.add_vline(x=xs.left_overbank_station_ft, line_color=GRAY, line_dash="dash")
    fig.add_vline(x=xs.right_overbank_station_ft, line_color=GRAY, line_dash="dash")
    fig.update_layout(
        title="Representative Cross Section",
        xaxis_title="Station (ft)",
        yaxis_title="Elevation (ft)",
        template="plotly_white",
        margin={"l": 55, "r": 20, "t": 60, "b": 50},
    )
    return fig


def make_rating_figure(rating: RatingTable) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=rating.discharge_cfs,
            y=rating.stage_ft,
            mode="lines",
            name="Stage-Discharge",
            line={"color": FNI_BLUE, "width": 3},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=rating.discharge_cfs,
            y=rating.storage_acft,
            mode="lines",
            name="Storage-Discharge",
            yaxis="y2",
            line={"color": FNI_GREEN, "width": 3},
        )
    )
    fig.update_layout(
        title="Rating and Storage Implied by One Cross Section",
        xaxis_title="Discharge (cfs)",
        yaxis={"title": "Stage (ft)"},
        yaxis2={"title": "Storage (ac-ft)", "overlaying": "y", "side": "right"},
        template="plotly_white",
        legend_title_text="Curve",
        margin={"l": 55, "r": 60, "t": 60, "b": 50},
    )
    return fig


def make_parameter_figure(result: RoutingResult) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=result.time_min, y=result.k_hr, mode="lines", name="Estimated K", line={"color": FNI_BLUE, "width": 3}
        )
    )
    fig.add_trace(
        go.Scatter(
            x=result.time_min,
            y=result.x,
            mode="lines",
            name="Estimated X",
            yaxis="y2",
            line={"color": FNI_GREEN, "width": 3},
        )
    )
    fig.update_layout(
        title="Routing Parameters During the Event",
        xaxis_title="Time (minutes)",
        yaxis={"title": "K (hours)"},
        yaxis2={"title": "X", "overlaying": "y", "side": "right", "range": [0, 0.55]},
        template="plotly_white",
        legend_title_text="Parameter",
        margin={"l": 55, "r": 60, "t": 60, "b": 50},
    )
    return fig


def metric_card(title: str, value: str, subtitle: str) -> html.Div:
    return html.Div(
        [
            html.Div(
                title, style={"fontSize": "14px", "fontWeight": "bold", "color": DARK_GRAY, "marginBottom": "8px"}
            ),
            html.Div(value, style={"fontSize": "27px", "fontWeight": "bold", "color": FNI_BLUE, "marginBottom": "6px"}),
            html.Div(subtitle, style={"fontSize": "14px", "color": DARK_GRAY}),
        ]
    )


# -----------------------------
# App layout
# -----------------------------

app = Dash(__name__)
server = app.server

CARD_STYLE = {
    "backgroundColor": "white",
    "border": "1px solid #d9e2e8",
    "borderRadius": "16px",
    "padding": "16px",
    "boxShadow": "0 4px 12px rgba(9, 61, 94, 0.08)",
}

METRIC_CARD_STYLE = {
    **CARD_STYLE,
    "minHeight": "110px",
}

UPLOAD_STYLE = {
    "width": "100%",
    "height": "64px",
    "lineHeight": "64px",
    "borderWidth": "1px",
    "borderStyle": "dashed",
    "borderRadius": "12px",
    "textAlign": "center",
    "borderColor": NEUTRAL_BLUE,
    "backgroundColor": "#f8fbfc",
    "color": FNI_NAVY,
}

DOWNLOAD_BUTTON_STYLE = {
    "width": "100%",
    "marginBottom": "14px",
    "padding": "8px 12px",
    "borderRadius": "10px",
    "border": f"1px solid {FNI_BLUE}",
    "backgroundColor": "#f8fbfc",
    "color": FNI_BLUE,
    "fontWeight": "bold",
    "cursor": "pointer",
}

SLIDER_MARKS_01 = {0.5: "0.5", 1.0: "1.0", 1.5: "1.5", 2.0: "2.0"}

app.layout = html.Div(
    style={
        "fontFamily": "Arial, sans-serif",
        "backgroundColor": "#f5f8fa",
        "minHeight": "100vh",
        "padding": "24px",
        "color": FNI_NAVY,
    },
    children=[
        dcc.Download(id="download-hydro-sample"),
        html.Div(
            style={"maxWidth": "1500px", "margin": "0 auto"},
            children=[
                html.H1("Routing Reach Representation Trainer", style={"marginBottom": "8px", "color": FNI_BLUE}),
                html.P(
                    "This teaching app compares a pure lag response to a simplified Muskingum-Cunge-style reach routing response. The point is to show how a single representative cross section, overbank geometry, and roughness assumptions can strongly control calibration to target peak flow and timing.",
                    style={"marginBottom": "20px", "maxWidth": "1120px"},
                ),
                html.Div(
                    style={"display": "grid", "gridTemplateColumns": "380px 1fr", "gap": "20px", "alignItems": "start"},
                    children=[
                        html.Div(
                            style=CARD_STYLE,
                            children=[
                                html.H3("Inputs", style={"marginTop": 0, "color": FNI_BLUE}),
                                html.Label("Optional inflow hydrograph CSV", style={"fontWeight": "bold"}),
                                dcc.Upload(
                                    id="upload-hydro",
                                    children=html.Div("Drag and drop or click to select"),
                                    style=UPLOAD_STYLE,
                                    multiple=False,
                                ),
                                html.Div(id="hydro-file-name", style={"marginTop": "8px", "marginBottom": "8px"}),
                                html.Button(
                                    "Download sample hydrograph CSV",
                                    id="btn-download-hydro",
                                    style=DOWNLOAD_BUTTON_STYLE,
                                ),
                                html.Label("Predefined reach", style={"fontWeight": "bold"}),
                                dcc.Dropdown(
                                    id="reach-select",
                                    options=[{"label": k, "value": k} for k in PREDEFINED_REACHES.keys()],
                                    value="Wide Floodplain Reach",
                                    clearable=False,
                                    style={"marginBottom": "14px"},
                                ),
                                html.Label("Target peak flow (cfs)", style={"fontWeight": "bold"}),
                                dcc.Slider(
                                    id="target-peak",
                                    min=900,
                                    max=2300,
                                    step=25,
                                    value=1450,
                                    marks={1000: "1000", 1500: "1500", 2000: "2000"},
                                    tooltip={"placement": "bottom", "always_visible": True},
                                ),
                                html.Label("Target peak time (min)", style={"fontWeight": "bold"}),
                                dcc.Slider(
                                    id="target-time",
                                    min=300,
                                    max=620,
                                    step=5,
                                    value=450,
                                    marks={300: "300", 450: "450", 600: "600"},
                                    tooltip={"placement": "bottom", "always_visible": True},
                                ),
                                html.H4("Cross-section calibration controls", style={"color": FNI_BLUE}),
                                html.Label("Overbank width factor", style={"fontWeight": "bold"}),
                                dcc.Slider(
                                    id="overbank-width",
                                    min=0.5,
                                    max=2.5,
                                    step=0.05,
                                    value=1.0,
                                    marks={0.5: "0.5", 1.0: "1.0", 1.5: "1.5", 2.0: "2.0", 2.5: "2.5"},
                                    tooltip={"placement": "bottom", "always_visible": True},
                                ),
                                html.Label("Overbank elevation adjustment (ft)", style={"fontWeight": "bold"}),
                                dcc.Slider(
                                    id="overbank-elev",
                                    min=-2.0,
                                    max=2.0,
                                    step=0.1,
                                    value=0.0,
                                    marks={-2: "-2", 0: "0", 2: "2"},
                                    tooltip={"placement": "bottom", "always_visible": True},
                                ),
                                html.Label("Main channel Manning n", style={"fontWeight": "bold"}),
                                dcc.Slider(
                                    id="n-main",
                                    min=0.025,
                                    max=0.080,
                                    step=0.001,
                                    value=0.040,
                                    marks={0.03: "0.03", 0.05: "0.05", 0.08: "0.08"},
                                    tooltip={"placement": "bottom", "always_visible": True},
                                ),
                                html.Label("Overbank Manning n", style={"fontWeight": "bold"}),
                                dcc.Slider(
                                    id="n-overbank",
                                    min=0.045,
                                    max=0.180,
                                    step=0.005,
                                    value=0.095,
                                    marks={0.05: "0.05", 0.10: "0.10", 0.15: "0.15"},
                                    tooltip={"placement": "bottom", "always_visible": True},
                                ),
                                html.Label("Reach length factor", style={"fontWeight": "bold"}),
                                dcc.Slider(
                                    id="length-factor",
                                    min=0.5,
                                    max=2.0,
                                    step=0.05,
                                    value=1.0,
                                    marks=SLIDER_MARKS_01,
                                    tooltip={"placement": "bottom", "always_visible": True},
                                ),
                                html.Label("Slope factor", style={"fontWeight": "bold"}),
                                dcc.Slider(
                                    id="slope-factor",
                                    min=0.5,
                                    max=2.0,
                                    step=0.05,
                                    value=1.0,
                                    marks=SLIDER_MARKS_01,
                                    tooltip={"placement": "bottom", "always_visible": True},
                                ),
                                html.Label("Muskingum-Cunge X factor", style={"fontWeight": "bold"}),
                                dcc.Slider(
                                    id="x-factor",
                                    min=0.5,
                                    max=1.5,
                                    step=0.05,
                                    value=1.0,
                                    marks={0.5: "0.5", 1.0: "1.0", 1.5: "1.5"},
                                    tooltip={"placement": "bottom", "always_visible": True},
                                ),
                                html.Label("Pure lag comparison (min)", style={"fontWeight": "bold"}),
                                dcc.Slider(
                                    id="pure-lag",
                                    min=0,
                                    max=240,
                                    step=5,
                                    value=90,
                                    marks={0: "0", 60: "60", 120: "120", 180: "180", 240: "240"},
                                    tooltip={"placement": "bottom", "always_visible": True},
                                ),
                                html.H4("Assumptions", style={"color": FNI_BLUE}),
                                html.Ul(
                                    style={"paddingLeft": "20px", "marginBottom": 0},
                                    children=[
                                        html.Li("Uses one eight-point representative cross section."),
                                        html.Li("Manning conveyance generates stage-discharge behavior."),
                                        html.Li("Reach storage is cross-section area times reach length."),
                                        html.Li(
                                            "Routing is simplified for instruction; it is not a detailed HMS replica."
                                        ),
                                        html.Li("Hydrograph CSV columns: time, inflow."),
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
                                        html.Div(id="metric-peak", style=METRIC_CARD_STYLE),
                                        html.Div(id="metric-time", style=METRIC_CARD_STYLE),
                                        html.Div(id="metric-stage", style=METRIC_CARD_STYLE),
                                        html.Div(id="metric-volume", style=METRIC_CARD_STYLE),
                                    ],
                                ),
                                html.Div(
                                    style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "20px"},
                                    children=[
                                        html.Div(dcc.Graph(id="hydrograph-plot"), style=CARD_STYLE),
                                        html.Div(dcc.Graph(id="cross-section-plot"), style=CARD_STYLE),
                                        html.Div(dcc.Graph(id="rating-plot"), style=CARD_STYLE),
                                        html.Div(dcc.Graph(id="parameter-plot"), style=CARD_STYLE),
                                    ],
                                ),
                                html.Div(
                                    style=CARD_STYLE,
                                    children=[
                                        html.H3("Calibration Summary", style={"marginTop": 0, "color": FNI_BLUE}),
                                        dash_table.DataTable(
                                            id="summary-table",
                                            columns=[
                                                {"name": c, "id": c}
                                                for c in [
                                                    "Metric",
                                                    "Value",
                                                    "Time (min)",
                                                    "Peak Error",
                                                    "Timing Error (min)",
                                                ]
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
                                        ),
                                    ],
                                ),
                                html.Details(
                                    style=CARD_STYLE,
                                    children=[
                                        html.Summary(
                                            "Teaching notes",
                                            style={"cursor": "pointer", "fontWeight": "bold", "color": FNI_BLUE},
                                        ),
                                        html.Div(
                                            style={"marginTop": "12px"},
                                            children=[
                                                html.P(
                                                    "This app is designed to make the representative-cross-section problem visible. A Muskingum-Cunge setup can look precise because it asks for geometry, roughness, length, and slope, but the result can still be governed by whether that one section actually represents the reach."
                                                ),
                                                html.P(
                                                    "Suggested workshop prompt: ask participants to hit both target peak flow and target timing, then change only the predefined reach. The difficulty of preserving calibration across reaches is the lesson."
                                                ),
                                                html.P(
                                                    "The pure-lag curve is included as a baseline. It shifts timing but does not create physically meaningful attenuation from storage."
                                                ),
                                            ],
                                        ),
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


# -----------------------------
# Callbacks
# -----------------------------


@app.callback(Output("hydro-file-name", "children"), Input("upload-hydro", "filename"))
def show_hydro_filename(filename):
    if not filename:
        return "Using built-in sample hydrograph."
    return f"Selected: {filename}"


@app.callback(
    Output("download-hydro-sample", "data"),
    Input("btn-download-hydro", "n_clicks"),
    prevent_initial_call=True,
)
def download_hydro_sample(_n_clicks):
    return dcc.send_data_frame(SAMPLE_HYDRO.to_csv, "sample_hydrograph.csv", index=False)


@app.callback(
    Output("status-message", "children"),
    Output("metric-peak", "children"),
    Output("metric-time", "children"),
    Output("metric-stage", "children"),
    Output("metric-volume", "children"),
    Output("hydrograph-plot", "figure"),
    Output("cross-section-plot", "figure"),
    Output("rating-plot", "figure"),
    Output("parameter-plot", "figure"),
    Output("summary-table", "data"),
    Input("upload-hydro", "contents"),
    Input("reach-select", "value"),
    Input("target-peak", "value"),
    Input("target-time", "value"),
    Input("overbank-width", "value"),
    Input("overbank-elev", "value"),
    Input("n-main", "value"),
    Input("n-overbank", "value"),
    Input("length-factor", "value"),
    Input("slope-factor", "value"),
    Input("x-factor", "value"),
    Input("pure-lag", "value"),
    State("upload-hydro", "filename"),
)
def update_outputs(
    hydro_contents,
    reach_name,
    target_peak,
    target_time,
    overbank_width,
    overbank_elev,
    n_main,
    n_overbank,
    length_factor,
    slope_factor,
    x_factor,
    pure_lag,
    hydro_filename,
):
    empty_fig = go.Figure()
    empty_fig.update_layout(template="plotly_white")

    try:
        if hydro_contents:
            raw_hydro = parse_uploaded_csv(hydro_contents, hydro_filename or "hydrograph CSV")
            hydro_df = load_hydrograph_from_df(raw_hydro)
        else:
            hydro_df = load_hydrograph_from_df(SAMPLE_HYDRO)

        result = run_model(
            hydro_df=hydro_df,
            reach_name=reach_name,
            overbank_width_factor=float(overbank_width),
            overbank_elev_adjust_ft=float(overbank_elev),
            n_main=float(n_main),
            n_overbank=float(n_overbank),
            slope_factor=float(slope_factor),
            length_factor=float(length_factor),
            x_factor=float(x_factor),
            pure_lag_min=float(pure_lag),
        )

        base_xs = PREDEFINED_REACHES[reach_name]
        xs = scaled_cross_section(base_xs, float(overbank_width), float(overbank_elev))

        summary = summarize_results(result, float(target_peak), float(target_time))
        for col in ["Value", "Time (min)", "Peak Error", "Timing Error (min)"]:
            summary[col] = summary[col].map(
                lambda x: round(float(x), 3) if isinstance(x, (int, float, np.floating)) else x
            )

        routed_peak, routed_peak_time = peak_stats(result.time_min, result.routed_cfs)
        max_stage = float(np.max(result.stage_ft))
        vol_in = float(np.trapezoid(result.inflow_cfs, result.time_min * 60.0) / FT3_PER_ACFT)
        vol_out = float(np.trapezoid(result.routed_cfs, result.time_min * 60.0) / FT3_PER_ACFT)
        volume_error_pct = 100.0 * (vol_out - vol_in) / max(vol_in, 1e-9)

        status = html.Div(
            [
                html.H3("Model updated", style={"marginTop": 0, "color": FNI_BLUE}),
                html.P(base_xs.description),
                html.P(
                    f"Effective reach length: {base_xs.reach_length_ft * float(length_factor):,.0f} ft. Effective slope: {base_xs.bed_slope_ftft * float(slope_factor):.5f} ft/ft."
                ),
            ]
        )

        return (
            status,
            metric_card(
                "Routed Peak", f"{routed_peak:,.0f} cfs", f"target error {routed_peak - float(target_peak):+,.0f} cfs"
            ),
            metric_card(
                "Peak Time",
                f"{routed_peak_time:,.0f} min",
                f"target error {routed_peak_time - float(target_time):+,.0f} min",
            ),
            metric_card("Max Stage", f"{max_stage:,.2f} ft", "relative to thalweg"),
            metric_card(
                "Volume Error", f"{volume_error_pct:+.2f}%", f"out {vol_out:,.1f} ac-ft vs in {vol_in:,.1f} ac-ft"
            ),
            make_hydrograph_figure(result, float(target_peak), float(target_time)),
            make_cross_section_figure(xs, result.rating, max_stage),
            make_rating_figure(result.rating),
            make_parameter_figure(result),
            summary.to_dict("records"),
        )

    except Exception as exc:
        status = html.Div(
            [
                html.H3("Routing error", style={"marginTop": 0, "color": FNI_ORANGE}),
                html.P(str(exc)),
            ]
        )
        return (
            status,
            metric_card("Routed Peak", "--", "Check inputs"),
            metric_card("Peak Time", "--", "Check inputs"),
            metric_card("Max Stage", "--", "Check inputs"),
            metric_card("Volume Error", "--", "Check inputs"),
            empty_fig,
            empty_fig,
            empty_fig,
            empty_fig,
            [],
        )


if __name__ == "__main__":
    app.run(debug=True)
