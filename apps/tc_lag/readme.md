# TC and Lag Assumption Explorer

## Learning objective

Show that transform modeling converts runoff volume into a hydrograph through timing assumptions, especially the relationship between time of concentration and lag time.

## Run

```bash
python apps/tc_lag/app.py
```

## Inputs

- Training basin selector.
- Lag ratio slider.
- Hydrograph peaking factor slider.

## Assumptions

- Drainage area is fixed for the exercise.
- Runoff depth is fixed after losses.
- Time of concentration is fixed.
- The app isolates lag and transform-shape assumptions.

## Primary outputs

- Target and modeled hydrograph comparison.
- Timing-assumption comparison.
- Conceptual rainfall-to-hydrograph workflow.
- Match score and summary table.
