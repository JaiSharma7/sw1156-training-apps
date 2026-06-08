// Per-step routing detail for the Mechanics act: builds the storage-indication tableau and the
// marker coordinates on the indication curve, reusing the same math as routing.js.

import { buildIndication, interp, ACREFT_TO_FT3 } from "./routing.js";

/**
 * Build the step-by-step routing trace for a hydrograph + storage-discharge curve.
 * Returns the indication curve (for plotting) and one row per timestep.
 */
export function buildSteps(hydro, curve) {
  const timeMin = hydro.timeMin;
  const inflow = hydro.inflowCfs;
  const storage = curve.storageAcft;
  const discharge = curve.dischargeCfs;

  const dtMin = timeMin[1] - timeMin[0];
  const dtSeconds = dtMin * 60.0;
  const indication = buildIndication(storage, discharge, dtMin);

  let lo = indication[0];
  let hi = indication[indication.length - 1];

  const rows = [];
  const outflow = new Array(timeMin.length);
  const stor = new Array(timeMin.length);
  outflow[0] = discharge[0];
  stor[0] = storage[0];

  // Initial-condition row (step 0): no equation, marker at the curve's start.
  rows.push({
    idx: 0,
    tMin: timeMin[0],
    inflowSum: null,
    rhs: null,
    outflowCfs: outflow[0],
    storageAcft: stor[0],
    clamped: false,
    marker: { x: indication[0], y: discharge[0] },
  });

  for (let i = 1; i < timeMin.length; i++) {
    const s1Ft3 = stor[i - 1] * ACREFT_TO_FT3;
    const inflowSum = inflow[i - 1] + inflow[i];
    const rhs = inflowSum + (2.0 * s1Ft3) / dtSeconds - outflow[i - 1];
    const clamped = rhs < lo - 1e-9 || rhs > hi + 1e-9;
    outflow[i] = interp(rhs, indication, discharge);
    stor[i] = interp(rhs, indication, storage);
    const markerX = Math.min(Math.max(rhs, lo), hi);
    rows.push({
      idx: i,
      tMin: timeMin[i],
      i1: inflow[i - 1],
      i2: inflow[i],
      inflowSum,
      prevTermRhs: (2.0 * s1Ft3) / dtSeconds - outflow[i - 1], // (2S1/dt - O1)
      rhs,
      outflowCfs: outflow[i],
      storageAcft: stor[i],
      clamped,
      marker: { x: markerX, y: outflow[i] },
    });
  }

  return { indication, discharge, storage, dtMin, rows };
}
