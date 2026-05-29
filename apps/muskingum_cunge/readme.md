# Routing Reach Representation Trainer

## Learning objective

Show why a single representative cross section can strongly control reach-routing results, and how overbank geometry and roughness adjustments affect peak timing and attenuation.

## Run

```bash
python apps/muskingum_cunge/app.py
```

## Inputs

- Optional inflow hydrograph CSV with columns similar to `time` and `inflow`.
- Predefined reach selector.
- Target peak flow and target peak time.
- Overbank width and elevation controls.
- Main channel and overbank Manning n values.
- Reach length, slope, Muskingum-Cunge X, and pure lag controls.

## Assumptions

- Uses one eight-point representative cross section.
- Manning conveyance generates stage-discharge behavior.
- Reach storage is cross-section area times reach length.
- Routing is simplified for instruction; it is not a detailed HMS replacement.

## Primary outputs

- Hydrograph timing and attenuation comparison.
- Representative cross-section plot.
- Rating and storage curves.
- Estimated routing parameters through time.
- Calibration summary table.
