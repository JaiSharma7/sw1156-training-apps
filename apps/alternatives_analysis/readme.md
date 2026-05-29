# Alternatives Analysis Explorer

## Learning objective

Teach that stormwater alternatives should be evaluated by problem type, scenario range, incremental benefit, incremental cost, and practical constructability rather than by one design-storm answer.

## Run

```bash
python apps/alternatives_analysis/app.py
```

## Inputs

- Problem frame selector.
- 100-year peak flow scenario anchor.
- Existing capacity event.
- Maximum flooded structures and lane-miles.
- Conveyance freeboard and cost assumptions.
- Detention target event, basin depth, bottom slope, and footprint limit.

## Assumptions

- Uses synthetic peak-flow frequency and hydrograph relationships for instruction.
- Uses conceptual costs, not design-level estimates.
- Storage footprint includes a simplified penalty for positive bottom drainage slope.

## Primary outputs

- Problem symptoms across storm events.
- Benefit-cost comparison.
- Conveyance tier comparison.
- Storage hydrograph and required storage.
- Alternatives matrix.
