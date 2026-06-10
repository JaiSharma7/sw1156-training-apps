"""Export golden routing values from the Python reference core for the JS parity test.

Requires NumPy >= 2.0 (the core uses np.trapezoid).
Run from the repo root:  python scripts/export_golden.py
Writes: apps/modified_puls_web/test/golden.json
"""

import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps" / "modified_puls" / "app.py"
DATA = ROOT / "apps" / "modified_puls_web" / "data"
OUT = ROOT / "apps" / "modified_puls_web" / "test" / "golden.json"

spec = importlib.util.spec_from_file_location("mp_ref", APP)
mp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mp)


def case(case_id, hydro_df, curve_df, multiplier):
    hydro = mp.load_hydrograph_from_df(hydro_df)
    curve = mp.load_storage_discharge_from_df(curve_df)
    result = mp.route_both_cases(hydro, curve, multiplier)
    cont = mp.continuity_summary(result)
    atten_out, lag_out = mp.attenuation_and_lag(result.time_min, result.inflow_cfs, result.outflow_cfs)
    atten_mod, lag_mod = mp.attenuation_and_lag(result.time_min, result.inflow_cfs, result.modified_outflow_cfs)
    return {
        "id": case_id,
        "multiplier": multiplier,
        "hydro": {
            "timeMin": hydro["time"].tolist(),
            "inflowCfs": hydro["inflow"].tolist(),
        },
        "curve": {
            "storageAcft": curve["storage"].tolist(),
            "dischargeCfs": curve["discharge"].tolist(),
        },
        "expected": {
            "outflowCfs": result.outflow_cfs.tolist(),
            "storageAcft": result.storage_acft.tolist(),
            "modifiedOutflowCfs": result.modified_outflow_cfs.tolist(),
            "modifiedStorageAcft": result.modified_storage_acft.tolist(),
            "clampedBase": [bool(x) for x in result.clamped_base.tolist()],
            "clampedModified": [bool(x) for x in result.clamped_modified.tolist()],
            "firstClampTime": mp.first_clamp_time(result),
            "continuity": {
                "vIn": cont["v_in"],
                "vOut": cont["v_out"],
                "deltaS": cont["delta_s"],
                "residual": cont["residual"],
                "residualPct": cont["residual_pct"],
            },
            "attenuationOutPct": atten_out,
            "lagOutMin": lag_out,
            "attenuationModPct": atten_mod,
            "lagModMin": lag_mod,
        },
    }


def main():
    cases = []
    for mult in (0.5, 1.0, 2.0, 3.0):
        cases.append(case(f"sample-x{mult}", mp.sample_hydro, mp.sample_curve, mult))

    # Undersized curve relative to the sample peak (70 cfs) -> clamps.
    small_curve = pd.DataFrame(
        {
            "Storage (acre-ft)": [0.0, 0.5, 1.0, 1.5, 2.0],
            "Discharge (cfs)": [0.0, 2.0, 4.0, 6.0, 8.0],
        }
    )
    cases.append(case("undersized-clamp", mp.sample_hydro, small_curve, 1.0))

    # Silver Creek 100-yr (real instructor data).
    sc_hydro = pd.read_csv(DATA / "inflow_Silver_Ck_J020_blw_EX_100YR_2020.csv")
    sc_curve = pd.read_csv(DATA / "SVSQ_Silver_Ck_R020_EX.csv")
    cases.append(case("silver-creek-100yr", sc_hydro, sc_curve, 1.0))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"cases": cases}, indent=0), encoding="utf-8")
    print(f"wrote {OUT} with {len(cases)} cases")


if __name__ == "__main__":
    main()
