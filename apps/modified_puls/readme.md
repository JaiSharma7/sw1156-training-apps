# Modified Puls Routing Explorer

## Learning objective

Show how changing storage in a storage-discharge relationship affects routed peak flow, storage use, and hydrograph timing.

## Run

```bash
python apps/modified_puls/app.py
```

## Inputs

- Hydrograph CSV with columns similar to `time` and `inflow`.
- Storage-discharge CSV with columns similar to `storage` and `discharge`.
- Storage multiplier slider.

## Assumptions

- Time units are minutes.
- Storage units are acre-feet.
- Flow units are cfs.
- Hydrograph timestep must be constant.
- Storage must be strictly increasing.
- Discharge must be monotonic nondecreasing.
- Linear interpolation is used on the storage-discharge curve.
- Routing stops if the calculation exceeds the provided curve.

## Primary outputs

- Inflow, original outflow, and modified outflow hydrographs.
- Original and modified storage-discharge curves.
- Peak flow, peak storage, and time-of-peak summary metrics.
