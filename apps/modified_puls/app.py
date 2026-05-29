import base64
import io
from dataclasses import dataclass
from typing import Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dcc, html, dash_table


# -----------------------------
# Helpers
# -----------------------------

def normalize_name(name: str) -> str:
    """Normalize a column header like 'Inflow (cfs)' -> 'inflow'."""
    name = str(name).strip().lower()
    for ch in ["(", ")", "[", "]", "{", "}"]:
        name = name.replace(ch, " ")
    parts = name.replace("_", " ").split()
    return parts[0] if parts else name


def find_required_columns(df: pd.DataFrame, required: Tuple[str, ...]) -> dict:
    mapping = {}
    normalized = {col: normalize_name(col) for col in df.columns}
    for req in required:
        matches = [col for col, norm in normalized.items() if norm == req]
        if not matches:
            raise ValueError(
                f"Required column '{req}' was not found. "
                f"Expected headers with names like '{req} (...)'."
            )
        mapping[req] = matches[0]
    return mapping


@dataclass
class RoutingResult:
    time_min: np.ndarray
    inflow_cfs: np.ndarray
    outflow_cfs: np.ndarray
    storage_acft: np.ndarray
    modified_outflow_cfs: np.ndarray
    modified_storage_acft: np.ndarray


# -----------------------------
# Data loading and validation
# -----------------------------

def load_hydrograph_from_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = find_required_columns(df, ("time", "inflow"))
    out = df[[cols["time"], cols["inflow"]]].copy()
    out.columns = ["time", "inflow"]

    out["time"] = pd.to_numeric(out["time"], errors="coerce")
    out["inflow"] = pd.to_numeric(out["inflow"], errors="coerce")
    out = out.dropna().reset_index(drop=True)

    if len(out) < 2:
        raise ValueError("Hydrograph must contain at least two valid rows.")

    dt = np.diff(out["time"].values)
    if np.any(dt <= 0):
        raise ValueError("Hydrograph time values must be strictly increasing.")

    if not np.allclose(dt, dt[0], rtol=0.0, atol=1e-9):
        raise ValueError("Hydrograph time step must be constant for this app.")

    return out


def load_storage_discharge_from_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = find_required_columns(df, ("storage", "discharge"))
    out = df[[cols["storage"], cols["discharge"]]].copy()
    out.columns = ["storage", "discharge"]

    out["storage"] = pd.to_numeric(out["storage"], errors="coerce")
    out["discharge"] = pd.to_numeric(out["discharge"], errors="coerce")
    out = out.dropna().reset_index(drop=True)

    if len(out) < 2:
        raise ValueError("Storage-discharge curve must contain at least two valid rows.")

    s = out["storage"].values
    q = out["discharge"].values

    if np.any(np.diff(s) <= 0):
        raise ValueError("Storage values must be strictly increasing.")

    if np.any(np.diff(q) < 0):
        raise ValueError("Discharge values must be monotonic nondecreasing.")

    return out


def parse_uploaded_csv(contents: str, label: str) -> pd.DataFrame:
    if contents is None:
        raise ValueError(f"No file was uploaded for {label}.")
    _, content_string = contents.split(",", 1)
    decoded = base64.b64decode(content_string)
    return pd.read_csv(io.StringIO(decoded.decode("utf-8")))


# -----------------------------
# Modified Puls routing
# -----------------------------

def build_indication_curve(storage_acft: np.ndarray, discharge_cfs: np.ndarray, dt_min: float):
    acreft_to_ft3 = 43560.0
    dt_seconds = dt_min * 60.0
    storage_ft3 = storage_acft * acreft_to_ft3
    indication = discharge_cfs + (2.0 * storage_ft3 / dt_seconds)
    return indication


def modified_puls_route(
    time_min: np.ndarray,
    inflow_cfs: np.ndarray,
    storage_acft: np.ndarray,
    discharge_cfs: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    dt_min = float(time_min[1] - time_min[0])
    indication = build_indication_curve(storage_acft, discharge_cfs, dt_min)

    if np.any(np.diff(indication) <= 0):
        raise ValueError(
            "The storage-indication curve is not strictly increasing. "
            "Check the storage-discharge data."
        )

    n = len(time_min)
    outflow = np.zeros(n, dtype=float)
    storage = np.zeros(n, dtype=float)

    outflow[0] = discharge_cfs[0]
    storage[0] = storage_acft[0]

    acreft_to_ft3 = 43560.0
    dt_seconds = dt_min * 60.0

    for i in range(1, n):
        s1_ft3 = storage[i - 1] * acreft_to_ft3
        rhs = inflow_cfs[i - 1] + inflow_cfs[i] + (2.0 * s1_ft3 / dt_seconds) - outflow[i - 1]

        if rhs < indication.min() - 1e-9 or rhs > indication.max() + 1e-9:
            raise ValueError(
                f"Routing exceeded the storage-discharge curve at step {i} "
                f"(time = {time_min[i]:.3f} minutes)."
            )

        outflow[i] = np.interp(rhs, indication, discharge_cfs)
        storage[i] = np.interp(rhs, indication, storage_acft)

    return outflow, storage


def route_both_cases(hydro_df: pd.DataFrame, curve_df: pd.DataFrame, multiplier: float) -> RoutingResult:
    time_min = hydro_df["time"].to_numpy(dtype=float)
    inflow_cfs = hydro_df["inflow"].to_numpy(dtype=float)

    storage_acft = curve_df["storage"].to_numpy(dtype=float)
    discharge_cfs = curve_df["discharge"].to_numpy(dtype=float)

    outflow_cfs, routed_storage_acft = modified_puls_route(
        time_min, inflow_cfs, storage_acft, discharge_cfs
    )

    modified_storage_curve = storage_acft * multiplier
    modified_outflow_cfs, modified_routed_storage_acft = modified_puls_route(
        time_min, inflow_cfs, modified_storage_curve, discharge_cfs
    )

    return RoutingResult(
        time_min=time_min,
        inflow_cfs=inflow_cfs,
        outflow_cfs=outflow_cfs,
        storage_acft=routed_storage_acft,
        modified_outflow_cfs=modified_outflow_cfs,
        modified_storage_acft=modified_routed_storage_acft,
    )


# -----------------------------
# Summary metrics
# -----------------------------

def peak_stats(time_min: np.ndarray, values: np.ndarray) -> Tuple[float, float]:
    idx = int(np.argmax(values))
    return float(values[idx]), float(time_min[idx])


def summarize_results(result: RoutingResult) -> pd.DataFrame:
    inflow_peak, inflow_peak_time = peak_stats(result.time_min, result.inflow_cfs)
    outflow_peak, outflow_peak_time = peak_stats(result.time_min, result.outflow_cfs)
    mod_outflow_peak, mod_outflow_peak_time = peak_stats(result.time_min, result.modified_outflow_cfs)
    storage_peak, storage_peak_time = peak_stats(result.time_min, result.storage_acft)
    mod_storage_peak, mod_storage_peak_time = peak_stats(result.time_min, result.modified_storage_acft)

    summary = pd.DataFrame(
        [
            ["Inflow", inflow_peak, inflow_peak_time],
            ["Outflow", outflow_peak, outflow_peak_time],
            ["Modified Outflow", mod_outflow_peak, mod_outflow_peak_time],
            ["Storage", storage_peak, storage_peak_time],
            ["Modified Storage", mod_storage_peak, mod_storage_peak_time],
        ],
        columns=["Series", "Peak Value", "Time of Peak (min)"],
    )
    return summary


# -----------------------------
# Plotting
# -----------------------------

def make_hydrograph_figure(result: RoutingResult) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=result.time_min,
            y=result.inflow_cfs,
            mode="lines",
            name="Inflow",
            line={"width": 3, "color": "#015D91"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=result.time_min,
            y=result.outflow_cfs,
            mode="lines",
            name="Outflow",
            line={"width": 3, "color": "#093D5E"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=result.time_min,
            y=result.modified_outflow_cfs,
            mode="lines",
            name="Modified Outflow",
            line={"width": 3, "color": "#A9C945"},
        )
    )
    fig.update_layout(
        title="Hydrographs",
        xaxis_title="Time (minutes)",
        yaxis_title="Flow (cfs)",
        template="plotly_white",
        legend_title_text="Series",
        margin={"l": 50, "r": 20, "t": 60, "b": 50},
    )
    return fig


def make_curve_figure(curve_df: pd.DataFrame, multiplier: float) -> go.Figure:
    s = curve_df["storage"].to_numpy(dtype=float)
    q = curve_df["discharge"].to_numpy(dtype=float)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=s,
            y=q,
            mode="lines+markers",
            name="Original Curve",
            line={"width": 3, "color": "#015D91"},
            marker={"size": 7},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=s * multiplier,
            y=q,
            mode="lines+markers",
            name=f"Modified Curve (storage x {multiplier:.2f})",
            line={"width": 3, "color": "#A9C945"},
            marker={"size": 7},
        )
    )
    fig.update_layout(
        title="Storage-Discharge Curves",
        xaxis_title="Storage (acre-ft)",
        yaxis_title="Discharge (cfs)",
        template="plotly_white",
        legend_title_text="Series",
        margin={"l": 50, "r": 20, "t": 60, "b": 50},
    )
    return fig


# -----------------------------
# Sample data for display
# -----------------------------

sample_hydro = pd.DataFrame(
    {
        "Time (min)": [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        "Inflow (cfs)": [5, 10, 20, 35, 55, 70, 60, 40, 25, 12, 6],
    }
)

sample_curve = pd.DataFrame(
    {
        "Storage (acre-ft)": [0.0, 1.5, 4.0, 8.0, 13.0, 19.0, 26.0],
        "Discharge (cfs)": [0.0, 3.0, 8.0, 16.0, 28.0, 45.0, 68.0],
    }
)


# -----------------------------
# App
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
    "backgroundColor": "white",
    "border": "1px solid #d9e2e8",
    "borderRadius": "16px",
    "padding": "14px 16px",
    "boxShadow": "0 4px 12px rgba(9, 61, 94, 0.08)",
    "minHeight": "110px",
}

UPLOAD_STYLE = {
    "width": "100%",
    "height": "70px",
    "lineHeight": "70px",
    "borderWidth": "1px",
    "borderStyle": "dashed",
    "borderRadius": "12px",
    "textAlign": "center",
    "borderColor": "#93AFB4",
    "backgroundColor": "#f8fbfc",
    "color": "#093D5E",
}

app.layout = html.Div(
    style={
        "fontFamily": "Arial, sans-serif",
        "backgroundColor": "#f5f8fa",
        "minHeight": "100vh",
        "padding": "24px",
        "color": "#093D5E",
    },
    children=[
        html.Div(
            style={"maxWidth": "1400px", "margin": "0 auto"},
            children=[
                html.H1(
                    "Modified Puls Routing Explorer",
                    style={"marginBottom": "8px", "color": "#015D91"},
                ),
                html.P(
                    "This teaching app routes an inflow hydrograph through a storage-discharge curve using the standard Modified Puls method. The slider applies a multiplier to storage only, then recomputes the routed outflow using the modified curve.",
                    style={"marginBottom": "20px", "maxWidth": "1000px"},
                ),
                html.Div(
                    style={
                        "display": "grid",
                        "gridTemplateColumns": "340px 1fr",
                        "gap": "20px",
                        "alignItems": "start",
                    },
                    children=[
                        html.Div(
                            style=CARD_STYLE,
                            children=[
                                html.H3("Inputs", style={"marginTop": "0", "color": "#015D91"}),
                                html.Label("Upload hydrograph CSV", style={"fontWeight": "bold"}),
                                dcc.Upload(
                                    id="upload-hydro",
                                    children=html.Div("Drag and drop or click to select"),
                                    style=UPLOAD_STYLE,
                                    multiple=False,
                                ),
                                html.Div(id="hydro-file-name", style={"marginTop": "8px", "marginBottom": "16px"}),
                                html.Label("Upload storage-discharge CSV", style={"fontWeight": "bold"}),
                                dcc.Upload(
                                    id="upload-curve",
                                    children=html.Div("Drag and drop or click to select"),
                                    style=UPLOAD_STYLE,
                                    multiple=False,
                                ),
                                html.Div(id="curve-file-name", style={"marginTop": "8px", "marginBottom": "16px"}),
                                html.Label("Storage multiplier", style={"fontWeight": "bold"}),
                                dcc.Slider(
                                    id="multiplier-slider",
                                    min=0.5,
                                    max=3.0,
                                    step=0.05,
                                    value=1.0,
                                    marks={
                                        0.5: {"label": "0.5"},
                                        1.0: {"label": "1.0"},
                                        1.5: {"label": "1.5"},
                                        2.0: {"label": "2.0"},
                                        2.5: {"label": "2.5"},
                                        3.0: {"label": "3.0"},
                                    },
                                    tooltip={"placement": "bottom", "always_visible": True},
                                ),
                                html.Div(style={"height": "16px"}),
                                html.H4("Assumptions", style={"marginBottom": "8px", "color": "#015D91"}),
                                html.Ul(
                                    style={"paddingLeft": "20px", "marginBottom": "0"},
                                    children=[
                                        html.Li("Hydrograph columns: time, inflow"),
                                        html.Li("Time units: minutes"),
                                        html.Li("Storage units: acre-ft"),
                                        html.Li("Flow units: cfs"),
                                        html.Li("Constant time step inferred from the hydrograph"),
                                        html.Li("Linear interpolation on the storage-discharge curve"),
                                        html.Li("Stops if routing exceeds the provided curve"),
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
                                        "gridTemplateColumns": "repeat(3, minmax(0, 1fr))",
                                        "gap": "16px",
                                    },
                                    children=[
                                        html.Div(id="metric-inflow", style=METRIC_CARD_STYLE),
                                        html.Div(id="metric-outflow", style=METRIC_CARD_STYLE),
                                        html.Div(id="metric-modified", style=METRIC_CARD_STYLE),
                                    ],
                                ),
                                html.Div(
                                    style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "20px"},
                                    children=[
                                        html.Div(dcc.Graph(id="hydrograph-plot"), style=CARD_STYLE),
                                        html.Div(dcc.Graph(id="curve-plot"), style=CARD_STYLE),
                                    ],
                                ),
                                html.Div(
                                    style=CARD_STYLE,
                                    children=[
                                        html.H3("Hydrograph Summary", style={"marginTop": "0", "color": "#015D91"}),
                                        dash_table.DataTable(
                                            id="summary-table",
                                            columns=[
                                                {"name": "Series", "id": "Series"},
                                                {"name": "Peak Value", "id": "Peak Value"},
                                                {"name": "Time of Peak (min)", "id": "Time of Peak (min)"},
                                            ],
                                            data=[],
                                            style_table={"overflowX": "auto"},
                                            style_header={
                                                "backgroundColor": "#015D91",
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
                                        html.Summary("Method details", style={"cursor": "pointer", "fontWeight": "bold", "color": "#015D91"}),
                                        html.Div(
                                            style={"marginTop": "12px"},
                                            children=[
                                                html.Div("2S2 over delta t plus O2 equals I1 plus I2 plus 2S1 over delta t minus O1", style={"fontWeight": "bold"}),
                                                html.P(
                                                    "For each time step, the app computes the right-hand side of the Modified Puls equation and uses linear interpolation on the storage-indication relation O + 2S over delta t to solve for the next outflow and storage."
                                                ),
                                                html.P(
                                                    "The slider multiplies storage only on the input storage-discharge curve. Discharge remains unchanged at each point on the curve."
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                                html.Details(
                                    style=CARD_STYLE,
                                    children=[
                                        html.Summary("Show example CSV formats", style={"cursor": "pointer", "fontWeight": "bold", "color": "#015D91"}),
                                        html.Div(
                                            style={"marginTop": "12px", "display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "20px"},
                                            children=[
                                                html.Div(
                                                    children=[
                                                        html.H4("Hydrograph CSV", style={"color": "#015D91"}),
                                                        dash_table.DataTable(
                                                            columns=[{"name": c, "id": c} for c in sample_hydro.columns],
                                                            data=sample_hydro.to_dict("records"),
                                                            style_table={"overflowX": "auto"},
                                                            style_header={"backgroundColor": "#e9f3f8", "fontWeight": "bold"},
                                                            style_cell={"textAlign": "left", "padding": "8px"},
                                                        ),
                                                    ]
                                                ),
                                                html.Div(
                                                    children=[
                                                        html.H4("Storage-discharge CSV", style={"color": "#015D91"}),
                                                        dash_table.DataTable(
                                                            columns=[{"name": c, "id": c} for c in sample_curve.columns],
                                                            data=sample_curve.to_dict("records"),
                                                            style_table={"overflowX": "auto"},
                                                            style_header={"backgroundColor": "#e9f3f8", "fontWeight": "bold"},
                                                            style_cell={"textAlign": "left", "padding": "8px"},
                                                        ),
                                                    ]
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
    ],
)


def build_metric_card(title: str, value: str, subtitle: str) -> html.Div:
    return html.Div(
        [
            html.Div(title, style={"fontSize": "14px", "fontWeight": "bold", "color": "#4D4D4F", "marginBottom": "8px"}),
            html.Div(value, style={"fontSize": "28px", "fontWeight": "bold", "color": "#015D91", "marginBottom": "6px"}),
            html.Div(subtitle, style={"fontSize": "14px", "color": "#4D4D4F"}),
        ]
    )


@app.callback(
    Output("hydro-file-name", "children"),
    Input("upload-hydro", "filename"),
)
def show_hydro_filename(filename):
    if not filename:
        return "No hydrograph file selected."
    return f"Selected: {filename}"


@app.callback(
    Output("curve-file-name", "children"),
    Input("upload-curve", "filename"),
)
def show_curve_filename(filename):
    if not filename:
        return "No storage-discharge file selected."
    return f"Selected: {filename}"


@app.callback(
    Output("status-message", "children"),
    Output("metric-inflow", "children"),
    Output("metric-outflow", "children"),
    Output("metric-modified", "children"),
    Output("hydrograph-plot", "figure"),
    Output("curve-plot", "figure"),
    Output("summary-table", "data"),
    Input("upload-hydro", "contents"),
    Input("upload-curve", "contents"),
    Input("multiplier-slider", "value"),
    State("upload-hydro", "filename"),
    State("upload-curve", "filename"),
)
def update_outputs(hydro_contents, curve_contents, multiplier, hydro_filename, curve_filename):
    empty_fig = go.Figure()
    empty_fig.update_layout(template="plotly_white", margin={"l": 40, "r": 20, "t": 40, "b": 40})

    if hydro_contents is None or curve_contents is None:
        status = html.Div(
            [
                html.H3("Ready", style={"marginTop": "0", "color": "#015D91"}),
                html.P("Upload both CSV files to run the routing."),
            ]
        )
        return (
            status,
            build_metric_card("Peak Inflow", "--", "Awaiting input"),
            build_metric_card("Peak Outflow", "--", "Awaiting input"),
            build_metric_card("Peak Modified Outflow", "--", "Awaiting input"),
            empty_fig,
            empty_fig,
            [],
        )

    try:
        raw_hydro_df = parse_uploaded_csv(hydro_contents, hydro_filename or "hydrograph CSV")
        raw_curve_df = parse_uploaded_csv(curve_contents, curve_filename or "storage-discharge CSV")
        hydro_df = load_hydrograph_from_df(raw_hydro_df)
        curve_df = load_storage_discharge_from_df(raw_curve_df)

        dt_min = hydro_df["time"].iloc[1] - hydro_df["time"].iloc[0]
        result = route_both_cases(hydro_df, curve_df, float(multiplier))
        summary = summarize_results(result)
        summary["Peak Value"] = summary["Peak Value"].map(lambda x: round(float(x), 3))
        summary["Time of Peak (min)"] = summary["Time of Peak (min)"].map(lambda x: round(float(x), 3))

        peak_in, t_in = peak_stats(result.time_min, result.inflow_cfs)
        peak_out, t_out = peak_stats(result.time_min, result.outflow_cfs)
        peak_mod, t_mod = peak_stats(result.time_min, result.modified_outflow_cfs)

        status = html.Div(
            [
                html.H3("Loaded files successfully", style={"marginTop": "0", "color": "#015D91"}),
                html.P(f"Detected time step: {dt_min:g} minutes."),
                html.P(f"Current storage multiplier: {float(multiplier):.2f}."),
            ]
        )

        return (
            status,
            build_metric_card("Peak Inflow", f"{peak_in:,.2f} cfs", f"at {t_in:g} min"),
            build_metric_card("Peak Outflow", f"{peak_out:,.2f} cfs", f"at {t_out:g} min"),
            build_metric_card("Peak Modified Outflow", f"{peak_mod:,.2f} cfs", f"at {t_mod:g} min"),
            make_hydrograph_figure(result),
            make_curve_figure(curve_df, float(multiplier)),
            summary.to_dict("records"),
        )

    except Exception as exc:
        status = html.Div(
            [
                html.H3("Routing error", style={"marginTop": "0", "color": "#E05126"}),
                html.P(str(exc)),
            ]
        )
        return (
            status,
            build_metric_card("Peak Inflow", "--", "Check input files"),
            build_metric_card("Peak Outflow", "--", "Check input files"),
            build_metric_card("Peak Modified Outflow", "--", "Check input files"),
            empty_fig,
            empty_fig,
            [],
        )


if __name__ == "__main__":
    app.run(debug=True)
