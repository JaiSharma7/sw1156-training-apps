# Modified Puls Routing Explorer

## Learning objective

Show how changing storage in a storage-discharge relationship affects routed peak flow, storage use, and hydrograph timing.

## Run

```bash
python apps/modified_puls/app.py
```

> **Web companion:** a static, browser-only version of this tool — built for GitHub Pages and a guided
> concept → mechanics → result walkthrough — lives in [`../modified_puls_web/`](../modified_puls_web/).
> This Dash app is its reference implementation: the web app's routing is a direct port, parity-tested
> against this code.

## Inputs

- Hydrograph CSV with columns similar to `time` and `inflow`.
- Storage-discharge CSV with columns similar to `storage` and `discharge`.
- Storage multiplier slider.

The app opens with built-in sample data, so it runs without any upload. Uploading a CSV replaces
either input independently. Buttons let you download the sample CSVs as templates.

## Assumptions

- Time units are minutes.
- Storage units are acre-feet.
- Flow units are cfs.
- Hydrograph timestep must be constant.
- Storage must be strictly increasing.
- Discharge must be monotonic nondecreasing.
- Linear interpolation is used on the storage-discharge curve.
- Beyond the curve, routing is clamped to its endpoints and the step is flagged (the run does not
  stop). A "curve exceeded" flag means the event outgrew the provided storage-discharge data.

## Primary outputs

- Inflow, original outflow, and modified outflow hydrographs (with a marker where the curve was exceeded).
- Original and modified storage-discharge curves.
- Peak flow, peak storage, and time-of-peak summary metrics.
- Peak **attenuation** (% reduction) and **lag** (time-of-peak shift) for each routed case.
- A **volume balance** metric: inflow vs outflow volume and the continuity residual, which stays near
  zero because storage-indication routing is derived from continuity.
