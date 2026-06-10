"""Unit tests for the Modified Puls routing core.

Run from the repo root:  pytest apps/modified_puls/test_routing.py
"""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Load the single-file app module by path (the apps folder is not a package).
_spec = importlib.util.spec_from_file_location("modified_puls_app", Path(__file__).with_name("app.py"))
mp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mp)


def test_volume_acft_known_triangle():
    # Triangular hydrograph: 0 -> 10 -> 0 cfs over 120 minutes.
    time_min = np.array([0.0, 60.0, 120.0])
    flow_cfs = np.array([0.0, 10.0, 0.0])
    # Area = 0.5 * 7200 s * 10 cfs = 36000 cfs*s; / 43560 = 0.8264 ac-ft.
    assert mp.volume_acft(flow_cfs, time_min) == pytest.approx(36000.0 / 43560.0, rel=1e-9)


def test_attenuation_and_lag():
    time_min = np.array([0.0, 10.0, 20.0, 30.0])
    inflow = np.array([0.0, 100.0, 50.0, 0.0])
    outflow = np.array([0.0, 30.0, 60.0, 10.0])
    atten, lag = mp.attenuation_and_lag(time_min, inflow, outflow)
    assert atten == pytest.approx(40.0)  # (100 - 60) / 100 * 100
    assert lag == pytest.approx(10.0)  # peak shifts from t=10 to t=20


def test_continuity_residual_near_zero():
    hydro = mp.load_hydrograph_from_df(mp.sample_hydro)
    curve = mp.load_storage_discharge_from_df(mp.sample_curve)
    result = mp.route_both_cases(hydro, curve, 1.0)
    balance = mp.continuity_summary(result)
    # Storage-indication routing is derived from continuity: V_in - V_out - dS ~= 0.
    assert abs(balance["residual_pct"]) < 0.5


def test_more_storage_increases_attenuation():
    hydro = mp.load_hydrograph_from_df(mp.sample_hydro)
    curve = mp.load_storage_discharge_from_df(mp.sample_curve)
    attens = []
    for mult in (0.5, 1.0, 2.0, 3.0):
        result = mp.route_both_cases(hydro, curve, mult)
        atten, _ = mp.attenuation_and_lag(result.time_min, result.inflow_cfs, result.modified_outflow_cfs)
        attens.append(atten)
    assert attens == sorted(attens)  # monotonic nondecreasing


def test_curve_exceedance_clamps_without_raising():
    # Storage-discharge curve too small for the sample hydrograph's peak (70 cfs).
    small_curve = mp.load_storage_discharge_from_df(
        pd.DataFrame(
            {
                "Storage (acre-ft)": [0.0, 0.5, 1.0, 1.5, 2.0],
                "Discharge (cfs)": [0.0, 2.0, 4.0, 6.0, 8.0],
            }
        )
    )
    hydro = mp.load_hydrograph_from_df(mp.sample_hydro)
    result = mp.route_both_cases(hydro, small_curve, 1.0)  # must not raise
    assert result.clamped_base.any()
    assert mp.first_clamp_time(result) is not None
